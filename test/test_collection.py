import random
import string

from bson.codec_options import CodecOptions
from bson.raw_bson import RawBSONDocument
from bson.py3compat import b
from bson import BSON
import numpy as np

import bsonnumpy
from test import unittest, client_context


class TestCollection2Ndarray(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.client = client_context.client

    def compare_elements(self, expected, actual):
        if isinstance(actual, np.ndarray):
            # print "comparing", actual, expected, "type act", type(actual)
            pass
            # self.assertTrue(isinstance(expected, list) or isinstance(expected, np.ndarray))
            # self.assertEqual(len(actual), len(expected))
            # for i in range(len(actual)):
            #     self.assertEqual(actual[i], expected[i])
        elif isinstance(actual, np.bytes_):
            expected = b(expected)
            self.assertEqual(expected, actual)
        elif isinstance(actual, np.void):
            doc = BSON(actual).decode()
            self.assertEqual(doc, expected)
        else:
            self.assertEqual(expected, actual)


    # TODO: deal with both name and title in dtype
    def compare_results(self, dtype, expected, actual):
        self.assertEqual(dtype, actual.dtype)
        self.assertEqual(expected.count(), len(actual))
        for act in actual:
            exp = next(expected)
            for desc in dtype.descr:
                name = desc[0]
                self.compare_elements(exp[name], act[name])

    @client_context.require_connected
    def test_collection_flexible_int32(self):
        self.client.drop_database("bsonnumpy_test")
        docs = [{"x": i, "y": 10-i} for i in range(10)]
        print("docs", docs)
        self.client.bsonnumpy_test.coll.insert_many(docs)
        raw_coll = self.client.get_database(
            'bsonnumpy_test',
            codec_options=CodecOptions(document_class=RawBSONDocument)).coll
        cursor = raw_coll.find()

        dtype = np.dtype([('x', np.int32), ('y', np.int32)])
        ndarray = bsonnumpy.collection_to_ndarray(
            (doc.raw for doc in cursor), dtype, raw_coll.count())
        self.compare_results(
            dtype, self.client.bsonnumpy_test.coll.find(), ndarray)

    @client_context.require_connected
    def test_collection_flexible_mixed_scalar(self):
        self.client.drop_database("bsonnumpy_test")
        docs = [{"x": i, "y": random.choice(string.ascii_lowercase)*11} for i in range(10)]
        self.client.bsonnumpy_test.coll.insert_many(docs)
        raw_coll = self.client.get_database(
            'bsonnumpy_test',
            codec_options=CodecOptions(document_class=RawBSONDocument)).coll
        cursor = raw_coll.find()

        dtype = np.dtype([('x', np.int32), ('y', 'S11')])
        ndarray = bsonnumpy.collection_to_ndarray(
            (doc.raw for doc in cursor), dtype, raw_coll.count())
        self.compare_results(dtype, self.client.bsonnumpy_test.coll.find(), ndarray)

    @client_context.require_connected
    def test_collection_flexible_mixed(self):
        self.client.drop_database("bsonnumpy_test")
        docs = [{"x": [i, 10-i], "y": random.choice(string.ascii_lowercase)*11, "z": {"a": i}} for i in range(10)]
        self.client.bsonnumpy_test.coll.insert_many(docs)
        raw_coll = self.client.get_database(
            'bsonnumpy_test',
            codec_options=CodecOptions(document_class=RawBSONDocument)).coll
        cursor = raw_coll.find()

        dtype = np.dtype([('x', '2int32'), ('y', 'S11'), ('z', 'V12')])
        ndarray = bsonnumpy.collection_to_ndarray(
            (doc.raw for doc in cursor), dtype, raw_coll.count())
        self.compare_results(dtype, self.client.bsonnumpy_test.coll.find(), ndarray)

    def test_dtype_depth(self):
        # simple dtypes
        dtype2 = np.dtype([('x', np.int32)])

        # dtypes with subarrays
        dtype3 = np.dtype([('x', '2int32'), ('y', 'S11'), ('z', 'V12')])
        dtype4 = np.dtype([('x', "(3,3)int32"), ('y', np.int32)])
        dtype10 = np.dtype([('x', "(1,2,3,4,5,6,7,8)int32"), ('y', np.int32)])

        # dtypes with sub*-dtypes
        dtype2_sub = np.dtype([('x', dtype2)])
        dtype3_sub = np.dtype([('x', dtype3)])
        dtype4_sub = np.dtype([('x', dtype4)])
        dtype10_sub = np.dtype([('x', dtype3), ('y', dtype10)])
        dtype10_sub_sub = np.dtype([('x', dtype10_sub), ('y', dtype10)])

        self.assertEqual(4, bsonnumpy.get_dtype_depth(dtype4))
        self.assertEqual(3, bsonnumpy.get_dtype_depth(dtype3))
        self.assertEqual(2, bsonnumpy.get_dtype_depth(dtype2))
        self.assertEqual(10, bsonnumpy.get_dtype_depth(dtype10))

        self.assertEqual(3, bsonnumpy.get_dtype_depth(dtype2_sub))
        self.assertEqual(4, bsonnumpy.get_dtype_depth(dtype3_sub))
        self.assertEqual(5, bsonnumpy.get_dtype_depth(dtype4_sub))
        self.assertEqual(11, bsonnumpy.get_dtype_depth(dtype10_sub))

        self.assertEqual(12, bsonnumpy.get_dtype_depth(dtype10_sub_sub))

    # @client_context.require_connected
    # def test_collection_standard(self):
    #     self.client.drop_database("bsonnumpy_test")
    #     self.client.bsonnumpy_test.coll.insert(
    #         [{"x": i} for i in range(1000)])
    #     raw_coll = self.client.get_database(
    #         'bsonnumpy_test',
    #         codec_options=CodecOptions(document_class=RawBSONDocument)).coll
    #     cursor = raw_coll.find()
    #
    #     dtype = np.dtype(np.int)
    #     ndarray = bsonnumpy.collection_to_ndarray(
    #         (doc.raw for doc in cursor), dtype, raw_coll.count())
