#!/usr/bin/env python

import unittest
import sqlite3 
import time
import sys
import random
import hashlib
import socket

class StoreError(Exception):
    pass

class LitterStore:
    """Handles storage and processes requests"""


    def __init__(self, uid = None, test = False):
        self.uid = uid if uid != None else socket.gethostname()
        self.con = sqlite3.connect(":memory:" if test else self.uid + ".db")
        self.nextid = 1
        self.__init_db()

    @staticmethod
    def cal_hash(uid, msg, txtime, postid):
        shash = hashlib.sha1()
        tohash = str(uid) + msg + str(txtime) + str(postid)
        #tohash is potentially unicode, if msg is, so we need to convert
        #back to bytes, to do this, we use utf-8:
        tohash = tohash.encode('utf-8')
        shash.update(tohash)
        return shash.hexdigest()

    def __db_call(self, action, params = None):
        print "dbcall -- %s %s" % (action, params)
        cur = self.con.cursor()

        if params != None:
            cur.execute(action, params) 
        else:
            cur.execute(action)

        result = cur.fetchall()
        self.con.commit()
        cur.close()
        return result

    def __init_db(self):
        self.__db_call("CREATE TABLE IF NOT EXISTS posts "
            "(uid TEXT, postid INTEGER, msg TEXT, txtime NUM, "
            "rxtime NUM, hashid TEXT, PRIMARY KEY(hashid ASC))")

        self.__db_call("CREATE TABLE IF NOT EXISTS friends "
            "(uid TEXT, fid TEXT, txtime NUM, "
            "PRIMARY KEY(uid, fid))")

        cid = self.__db_call("SELECT MAX(postid) FROM posts WHERE uid == ?",
            (self.uid, ))

        if cid[0][0] != None:
            self.nextid = cid[0][0] + 1

    def __update_time(self, uid, fid, txtime = 0):
        msg = "SELECT txtime FROM friends WHERE uid == ? and fid == ?"
        results = self.__db_call(msg,(uid, fid))

        if len(results) < 1:
            msg = "INSERT INTO friends (uid, fid, txtime) VALUES (?, ?, ?)"
            self.__db_call(msg, (uid, fid, txtime))
        elif results[0][0] < txtime:
            msg = "UPDATE friends SET txtime = ? WHERE uid == ? and fid == ?"
            self.__db_call(msg, (txtime, uid, fid))

    def __post(self, msg, uid=None, txtime = None, postid = -1, hashid=None):
        rxtime = 0

        if uid == None:
            uid = self.uid
            txtime = time.time()
            postid = self.nextid
            self.nextid += 1
            hashid = self.cal_hash(uid, msg, txtime, postid)

        if len(msg) > 140:
            raise Exception("message too long")

        if postid == -1:
            raise Exception("Invalid postid: " + str(postid))

        if hashid != self.cal_hash(uid, msg, txtime, postid):
            raise Exception("hashid doesn't match:"
                " uid: %s msg: %s time: %s postid: %s badhash: %s" \
                % (uid, msg, txtime, postid, hashid))

        try:
            self.__db_call("INSERT INTO posts (uid, postid, txtime, "
                "rxtime, msg, hashid) VALUES (?, ?, ?, ?, ?, ?)", 
                (uid, postid, txtime, rxtime, msg, hashid))
        except sqlite3.IntegrityError as ie:
            raise StoreError(str(ie))    

        self.__update_time(self.uid, uid, txtime)

        return [(uid, postid, txtime, msg, hashid)]

    def __get(self, uid = None, begin = 0, until = sys.maxint, limit = 10):
        pref = "SELECT uid, postid, txtime, msg, hashid FROM posts WHERE "
        msg = ()

        if uid == None:
            msg = pref + ("txtime > ? and txtime < ? ORDER BY "
                "txtime DESC LIMIT ?"), (begin, until, limit)
        else:
            msg = pref + ("uid == ? and txtime > ? and txtime < ? "
                "ORDER BY txtime DESC LIMIT ?"), (uid, begin, until, limit)

        return self.__db_call(msg[0], msg[1])

    def __pull_req(self):
        request = { 'm' : 'pull_rcv', 'uid' : self.uid }
        msg = "SELECT fid, txtime FROM friends WHERE uid == ?"
        request['friends'] = []
        request['friends'].extend(self.__db_call(msg, (self.uid,)))
        return request

    def __pull_rcv(self, uid, friends = None):
        results = []
        self.__update_time(self.uid, uid, 0)

        for fid, txtime in friends:
            self.__update_time(uid, fid, txtime)
            results.extend(self.__get(fid, txtime))

        return results

    # Code adapted from Ben Englard implemetation
    def __find_gaps_by_uid(self, uid):
        msg = ("SELECT postid, txtime FROM posts WHERE uid == ? " 
               "ORDER BY txtime DESC")
        results = self.__db_call(msg, (uid,))
        gaps = []
        last_item = None

        for postid, txtime in results:
            if last_item == None:
                last_item = (postid, txtime)
                continue

            diff = last_item[0] - postid

            if diff > 1:
                gaps.append((txtime, last_item[1]))

            last_item = (postid, txtime)

        # last item should be 1, if not we have a gap
        if last_item[0] != 1:
            gaps.append((0, last_item[1]))

        return gaps

    def __find_all_gaps(self):
        msg = "SELECT DISTINCT fid FROM friends WHERE uid ==?"
        fids = self.__db_call(msg, (self.uid,))
        results = {}

        for fid, in fids:
            results[fid] = self.__find_gaps_by_uid(fid)

        return results;

    def __gap_req(self):
        request = {'m': 'gap_rcv', 'uid' : self.uid }
        request['friends'] = self.__find_all_gaps()
        return request

    def __gap_rcv(self, uid = None, friends = None):
        results = []
        self.__update_time(self.uid, uid, 0)

        for fid, gaps in friends.iteritems():
            for start, end in gaps:
                self.__update_time(uid, fid, end)
                posts = self.__get(fid, start, end)
                results.extend(posts)

        return results

    def __process_results(self, response):
        results = []
        if isinstance(response, list):
            for post in response:
                kwargs = {}
                kwargs['uid'] = post[0]
                kwargs['postid'] = post[1]
                kwargs['txtime'] = post[2]
                kwargs['msg'] = post[3]
                kwargs['hashid'] = post[4]
                kwargs['m'] = 'post'
                results.append(kwargs)
        elif isinstance(response, dict):
            results.append(response)

        return results

    def process(self, request):
        results = []
        method = request['m']
        del request['m']

        if method == 'post':
            results = self.__post(**request)
        elif method == 'get':
            results = self.__get(**request)
        elif method == 'pull_req':
            results = self.__pull_req()
        elif method == 'pull_rcv':
            results = self.__pull_rcv(**request)
        elif method == 'gap_req':
            results = self.__gap_req()
        elif method == 'gap_rcv':
            results = self.__gap_rcv(**request)

        return self.__process_results(results)

    def close(self):
        self.con.close()


class LitterUnitSingle(unittest.TestCase):
    """Unit test for litter store in single user case"""

    def setUp(self):
        self.litter = LitterStore("Test", test = True)

    def tearDown(self):
        self.litter.close()
        self.litter = None

    def test_posts(self):
        msg = 'this is a test'

        request = {'m': 'post', 'msg' : msg }
        results = self.litter.process(request)
        self.assertEqual(results[0]['msg'], msg)

        request = {'m': 'post', 'msg' : msg }
        results = self.litter.process(request)
        self.assertEqual(results[0]['postid'], 2)

        request = {'m': 'get'}
        results = self.litter.process(request)
        self.assertEqual(len(results), 2)

        msg = 'message from luda'
        txtime = time.time()
        uid = 'luda'
        postid = 2
        hashid = self.litter.cal_hash(uid, msg, txtime, postid)
        request = {'m' : 'post', 'uid': uid, 'msg' : msg, 'postid' : postid,
                    'txtime' : txtime, 'hashid' : hashid}
        results = self.litter.process(request)
        self.assertEqual(results[0]['uid'], 'luda')

    def test_friends(self):
        msg = 'message from luda'
        txtime = time.time()
        uid = 'luda'
        postid = 2
        hashid = self.litter.cal_hash(uid, msg, txtime, postid)
        request = {'m' : 'post', 'uid': uid, 'msg' : msg, 'postid' : postid,
                    'txtime' : txtime, 'hashid' : hashid}
        results = self.litter.process(request)
        self.assertEqual(results[0]['uid'], 'luda')

        txtime = txtime + 500
        hashid = self.litter.cal_hash(uid, msg, txtime, postid)
        request = {'m' : 'post', 'uid': uid, 'msg' : msg, 'postid' : postid,
                    'txtime' : txtime, 'hashid' : hashid}
        results = self.litter.process(request)
        self.assertEqual(results[0]['uid'], 'luda')


        request = { 'm' : 'get_friends'}
        results = self.litter.process(request)
        print results


class LitterUnitDouble(unittest.TestCase):
    """Unit test for litter store in double user case"""

    def setUp(self):
        self.litter_a = LitterStore("usera", test = True)
        self.litter_b = LitterStore("userb", test = True)

    def tearDown(self):
        self.litter_a.close()
        self.litter_b.close()
        self.litter_a = None
        self.litter_b = None

    def test_pull(self):
        request_a = {'m' : 'pull_req'}
        results_a = self.litter_a.process(request_a)

        request_b = results_a[0]
        results_b = self.litter_b.process(request_b)

        msg = 'this is a test'
        request_a = {'m': 'post', 'msg' : msg}
        results_a = self.litter_a.process(request_a)
        request_a = {'m': 'post', 'msg' : msg}
        results_a = self.litter_a.process(request_a)

        request_b = {'m': 'pull_req'}
        results_b = self.litter_b.process(request_b)

        request_a = results_b[0]
        results_a = self.litter_a.process(request_a)

        request_b = results_a[0]
        results_b = self.litter_b.process(request_b)

        self.assertEqual(results_b[0]['msg'], msg)

    def test_gap(self):
        request_a = {'m' : 'gap_req'}
        results_a = self.litter_a.process(request_a)
        self.assertEqual(results_a[0]['m'], 'gap_rcv')
        self.assertEqual(len(results_a[0]['friends']), 0)

        request_b = results_a[0]
        results_b = self.litter_b.process(request_b)
        self.assertEqual(len(results_b), 0)

        msg = 'this is a test'
        request_a = {'m': 'post', 'msg' : msg}
        results_a = self.litter_a.process(request_a)
        request_a = {'m': 'post', 'msg' : msg}
        results_a = self.litter_a.process(request_a)
        self.assertEqual(results_a[0]['postid'], 2)
        self.assertEqual(results_a[0]['msg'], msg)

        request_b = results_a[0]
        results_b = self.litter_b.process(request_b)

        request_b = {'m': 'gap_req'}
        results_b = self.litter_b.process(request_b)
        self.assertEqual(results_b[0]['m'], 'gap_rcv')
        self.assertEqual(results_b[0]['friends'].keys()[0], 'usera')

        request_a = results_b[0]
        results_a = self.litter_a.process(request_a)
        self.assertEqual(results_a[0]['postid'], 1)
        self.assertEqual(results_a[0]['msg'], msg)



if __name__ == '__main__':
    unittest.main()
