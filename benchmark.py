import argparse
import collections
import math
import string
import sys
import timeit
from functools import partial

import pymongo
import numpy as np
from bson import BSON, CodecOptions, Int64, ObjectId
from bson.raw_bson import RawBSONDocument

try:
    import bsonnumpy
except (ImportError, OSError) as exc:
    print(exc)
    bsonnumpy = None

try:
    import monary
except (ImportError, OSError) as exc:
    monary = None

assert pymongo.has_c()

# Use large document in tests? If SMALL, no, if LARGE, then yes.
SMALL = False
LARGE = True
db = None
raw_bson = None
large_doc_keys = None
collection_names = {LARGE: "large", SMALL: "small"}
dtypes = {}
raw_bsons = {}


def _setup():
    global db
    global raw_bson
    global large_doc_keys

    db = pymongo.MongoClient().bsonnumpy_test
    small = db[collection_names[SMALL]]
    small.drop()

    print("%d small docs, %d bytes each with 3 keys" % (
        N_SMALL_DOCS,
        len(BSON.encode({'_id': ObjectId(), 'x': 1, 'y': math.pi}))))

    small.insert_many([
        collections.OrderedDict([('x', 1), ('y', math.pi)])
        for _ in range(N_SMALL_DOCS)])

    dtypes[SMALL] = np.dtype([('x', np.int64), ('y', np.float64)])

    large = db[collection_names[LARGE]]
    large.drop()
    # 2600 keys: 'a', 'aa', 'aaa', .., 'zz..z'
    large_doc_keys = [c * i for c in string.ascii_lowercase
                      for i in range(1, 101)]
    large_doc = collections.OrderedDict([(k, math.pi) for k in large_doc_keys])
    print("%d large docs, %dk each with %d keys" % (
        N_LARGE_DOCS, len(BSON.encode(large_doc)) // 1024, len(large_doc_keys)))

    large.insert_many([large_doc.copy() for _ in range(N_LARGE_DOCS)])

    dtypes[LARGE] = np.dtype([(k, np.float64) for k in large_doc_keys])

    # Ignore for now that the first batch defaults to 101 documents.
    raw_bson_docs_small = [{'x': 1, 'y': math.pi} for _ in range(N_SMALL_DOCS)]
    raw_bson_small = BSON.encode({'ok': 1,
                                  'cursor': {
                                      'id': Int64(1234),
                                      'ns': 'db.collection',
                                      'firstBatch': raw_bson_docs_small}})

    raw_bson_docs_large = [large_doc.copy() for _ in range(N_LARGE_DOCS)]
    raw_bson_large = BSON.encode({'ok': 1,
                                  'cursor': {
                                      'id': Int64(1234),
                                      'ns': 'db.collection',
                                      'firstBatch': raw_bson_docs_large}})

    raw_bsons[SMALL] = raw_bson_small
    raw_bsons[LARGE] = raw_bson_large


def _teardown():
    db.collection.drop()


bench_fns = collections.OrderedDict()


def bench(name):
    def assign_name(fn):
        bench_fns[name] = fn
        return fn

    return assign_name


@bench('conventional-to-ndarray')
def conventional_func(use_large):
    collection = db[collection_names[use_large]]
    cursor = collection.find()
    dtype = dtypes[use_large]

    if use_large:
        np.array([tuple(doc[k] for k in large_doc_keys) for doc in cursor],
                 dtype=dtype)
    else:
        np.array([(doc['x'], doc['y']) for doc in cursor], dtype=dtype)


@bench('raw-bson-to-ndarray')
def bson_numpy_func(use_large):
    raw_coll = db.get_collection(
        collection_names[use_large],
        codec_options=CodecOptions(document_class=RawBSONDocument))

    cursor = raw_coll.find_raw_batches()
    dtype = dtypes[use_large]
    bsonnumpy.sequence_to_ndarray(cursor, dtype, raw_coll.count_documents({}))


@bench('raw-batches-to-ndarray')
def raw_bson_func(use_large):
    c = db[collection_names[use_large]]
    if not hasattr(c, 'find_raw_batches'):
        print("Wrong PyMongo: no 'find_raw_batches' feature")
        return

    dtype = dtypes[use_large]
    bsonnumpy.sequence_to_ndarray(c.find_raw_batches(), dtype,
                                  c.count_documents({}))


@bench('monary')
def monary_func(use_large):
    return
    # Monary doesn't allow > 1024 keys, and it's too slow to benchmark anyway.
    if use_large:
        return

    m = monary.Monary()
    dtype = dtypes[use_large]
    m.query(db.name, collection_names[use_large], {}, dtype.names,
            ["float64"] * len(dtype.names))


@bench('parse-dtype')
def raw_bson_func(use_large):
    dtype = dtypes[use_large]
    bsonnumpy.sequence_to_ndarray([], dtype, 0)


@bench('decoded-cmd-reply')
def bson_func(use_large):
    for _ in BSON(raw_bsons[use_large]).decode()['cursor']['firstBatch']:
        pass


@bench('raw-cmd-reply')
def raw_bson_func(use_large):
    options = CodecOptions(document_class=RawBSONDocument)
    for _ in BSON(raw_bsons[use_large]).decode(options)['cursor']['firstBatch']:
        pass


parser = argparse.ArgumentParser(formatter_class=argparse.RawTextHelpFormatter,
                                 epilog="""
Available benchmark functions:
   %s
""" % ("\n   ".join(bench_fns.keys()),))
parser.add_argument('--large', action='store_true',
                    help='only test with large documents')
parser.add_argument('--small', action='store_true',
                    help='only test with small documents')
parser.add_argument('--test', action='store_true',
                    help='quick test of benchmark.py')
parser.add_argument('funcs', nargs='*', default=bench_fns.keys())
options = parser.parse_args()

if options.test:
    N_LARGE_DOCS = 2
    N_SMALL_DOCS = 2
    N_TRIALS = 1
else:
    N_LARGE_DOCS = 1000
    N_SMALL_DOCS = 100000
    N_TRIALS = 5

# Run tests with both small and large documents.
sizes = [SMALL, LARGE]
if options.large and not options.small:
    sizes.remove(SMALL)
if options.small and not options.large:
    sizes.remove(LARGE)

for name in options.funcs:
    if name not in bench_fns:
        sys.stderr.write("Unknown function \"%s\"\n" % name)
        sys.stderr.write("Available functions:\n%s\n" % ("\n".join(bench_fns)))
        sys.exit(1)

_setup()

print()
print("%25s: %7s %7s" % ("BENCH", "SMALL", "LARGE"))

for name, fn in bench_fns.items():
    if name in options.funcs:
        sys.stdout.write("%25s: " % name)
        sys.stdout.flush()

        # Test with small and large documents.
        import faulthandler
        faulthandler.enable()
        for size in (SMALL, LARGE):
            if size not in sizes:
                sys.stdout.write("%7s" % "-")
            else:
                timer = timeit.Timer(partial(fn, size))
                duration = min(timer.repeat(3, N_TRIALS)) / float(N_TRIALS)
                sys.stdout.write("%7.2f " % duration)
            sys.stdout.flush()

        sys.stdout.write("\n")

_teardown()
