#!/usr/bin/env python

import unittest
from litterstore import *

class LitterUnit(unittest.TestCase):
    """Unit test for litter store in double user case"""

    def setUp(self):
        self.litter_a = LitterStore("usera", test=True)
        self.litter_b = LitterStore("userb", test=True)

    def tearDown(self):
        self.litter_a.close()
        self.litter_b.close()

    def test(self):
        request = {'m':'gen_pull'}
        result = self.litter_b.process(request)
        self.assertEqual(result['headers']['hto'], 'all')
        self.assertEqual(result['headers']['hfrom'], 'userb')
        self.assertEqual(result['headers']['htype'], 'req')
        self.assertEqual(result['headers']['httl'], 2)

        result = self.litter_a.process(result)

        request = {'posts':[]}
        request['posts'].append(('this is my first post',))
        request['posts'].append(('this is my second post',))
        result = self.litter_a.process(request)
        self.assertEqual(result, {'headers':None})

        request = {'m':'gen_push'}
        result = self.litter_a.process(request)
        self.assertEqual(len(result['posts']),1)

        request = {'m':'gen_pull'}
        result = self.litter_b.process(request)
        self.assertEqual(result['headers']['hto'], 'all')
        self.assertEqual(result['headers']['hfrom'], 'userb')
        self.assertEqual(result['headers']['htype'], 'req')
        self.assertEqual(result['headers']['httl'], 2)

        result = self.litter_a.process(result)
        self.assertEqual(result['headers']['hto'], 'userb')
        self.assertEqual(result['headers']['hfrom'], 'usera')
        self.assertEqual(result['headers']['htype'], 'rep')
        self.assertEqual(result['headers']['httl'], 4)

        result = self.litter_b.process(result)
        self.assertEqual(result, {'headers':None})

        request = {'m':'get','begin':0,'limit':10}
        result = self.litter_b.process(request)
        self.assertEqual(result['headers'], None)
        self.assertEqual(len(result['posts']),1)
        self.assertEqual(result['posts'][0][1],'usera')


if __name__ == '__main__':
    unittest.main()
