#!/usr/bin/env python

import sqlite3 
import time
import sys
import random
import socket
import unittest
import logging
import cgi
from jsoncert import JsonCert

#logging.basicConfig(level=logging.DEBUG)

class StoreError(Exception):
    """Used to raise litterstore error"""

    def __init__(self, msg):
        self.msg = msg

    def __str__(self):
        return str(self.msg)


class LitterStore:
    """Handles storage and processes requests"""

    def __init__(self, uid=None, test=False):
        self.__uid = uid if uid != None else socket.gethostname()
        self.__con = sqlite3.connect(":memory:" if test else self.__uid + ".db")
        self.__nextid = 1
        self.__init_db()

    def __db_call(self, action, params=None):
        logging.debug("dbcall -- %s %s" % (action, params))

        try:
            cur = self.__con.cursor()

            if params != None:
                cur.execute(action, params) 
            else:
                cur.execute(action)

            result = cur.fetchall()
            self.__con.commit()
            cur.close()

        except sqlite3.IntegrityError as ie:
            raise StoreError(str(ie))

        return result

    def __init_db(self):
        self.__db_call("CREATE TABLE IF NOT EXISTS posts "
            "(uid TEXT, postid INTEGER, msg TEXT, txtime NUM, "
            "rxtime NUM, perms NUM, sig TEXT, PRIMARY KEY(sig ASC))")

        self.__db_call("CREATE TABLE IF NOT EXISTS friends "
            "(uid TEXT, fid TEXT, txtime NUM, PRIMARY KEY(uid, fid))")

        cid = self.__db_call("SELECT MAX(postid) FROM posts WHERE uid == ?",
            (self.__uid, ))

        if cid[0][0] != None: 
            self.__nextid = cid[0][0] + 1

    def __update_time(self, uid, fid, txtime=0):
        msg = "SELECT txtime FROM friends WHERE uid == ? and fid == ?"
        results = self.__db_call(msg,(uid, fid))

        if len(results) < 1:
            msg = "INSERT INTO friends (uid, fid, txtime) VALUES (?, ?, ?)"
            self.__db_call(msg, (uid, fid, txtime))

        elif results[0][0] != None and results[0][0] < txtime:
            msg = "UPDATE friends SET txtime = ? WHERE uid == ? and fid == ?"
            self.__db_call(msg, (txtime, uid, fid))

    def __post(self, msg, uid=None, txtime=None, rxtime=None, postid=-1, 
        perms=None, sig=None):

        rxtime = time.time()

        # sets default permission to public
        if perms == None:
            perms = 1

        if uid == None:
            uid = self.__uid
            txtime = rxtime
            postid = self.__nextid
            self.__nextid += 1
            sig = JsonCert.cal_hash('%s%s%s%s%s' % 
                                     (msg, uid, txtime, postid, perms))

        post = (uid, postid, txtime, rxtime, msg, perms, sig)

        logging.debug('POST : %s %s %s %s %s %s %s' % post)

        if len(msg) > 140:
            raise StoreError("message too long")

        if postid == -1:
            raise StoreError("Invalid postid: " + str(postid))

        self.__db_call("INSERT INTO posts (uid, postid, txtime, "
            "rxtime, msg, perms, sig) VALUES (?, ?, ?, ?, ?, ?, ?)", post)

        self.__update_time(self.__uid, uid, txtime)

        return post

    def __get(self, uid=None, perms=None, begin=0, until=sys.maxint, limit=10):

        msg = None
        pref = "SELECT msg, uid, txtime, rxtime, postid, perms, sig \
                FROM posts WHERE "

        if uid == None or uid == self.__uid:
            msg = pref + ("txtime > ? and txtime < ? ORDER BY "
                "txtime DESC LIMIT ?"), (begin, until, limit)
        else:
            msg = pref + ("uid == ? and perms == ? and txtime > ? and "
                "txtime < ? ORDER BY txtime DESC LIMIT ?"), \
                (uid, perms, begin, until, limit)

        data = self.__db_call(msg[0], msg[1])
        for i in range(len(data)):
            d = list(data[i])
            d[0] = cgi.escape(d[0])
            d[1] = cgi.escape(d[1])
            data[i] = tuple(d)
        return data

    def __pull(self, uid, friends=None):
        results = []
        self.__update_time(self.__uid, uid, 0)

        if friends != None and len(friends) == 0:
            # if friends is empty, this is a new node, so reply your posts
            results = self.__get(uid=self.__uid, perms=1)
        elif friends != None:
            for fid, txtime in friends:
                self.__update_time(uid, fid, txtime)
                results.extend(self.__get(uid=fid, perms=1, begin=txtime))

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
        if last_item != None and last_item[0] != 1:
            gaps.append((0, last_item[1]))

        return gaps

    def __find_all_gaps(self):
        msg = "SELECT DISTINCT fid FROM friends WHERE uid ==?"
        fids = self.__db_call(msg, (self.__uid,))
        results = {}

        for fid, in fids:
            gaps = self.__find_gaps_by_uid(fid)

            # only add if gaps are found
            if len(gaps) > 0:
                results[fid] = self.__find_gaps_by_uid(fid)

        return results

    def __gap(self, uid, friends=None):
        results = []
        self.__update_time(self.__uid, uid, 0)

        for fid, gaps in friends.iteritems():
            for start, end in gaps:
                self.__update_time(uid, fid, end)
                posts = self.__get(fid, start, end)
                results.extend(posts)

        return results

    def __gen_push(self):
        pass

    def __gen_pull(self):
        request = { 'm' : 'pull', 'uid': self.__uid}
        msg = "SELECT fid, txtime FROM friends WHERE uid == ?"
        request['friends'] = []
        request['friends'].extend(self.__db_call(msg, (self.__uid,)))
        return request

    def __gen_gap(self):
        request = []
        gap_list = self.__find_all_gaps()

        # only return dictionary if gaps are found
        if len(gap_list) > 0:
            request = {'m': 'gap', 'friends': gap_list}

        return request

    def __get_headers(self, request, meth=None):

        logging.debug('GETHEADERS : %s %s' % (request,meth))

        headers = None

        if meth == 'gen_push' or meth == 'gen_pull' or meth == 'gen_gap':
            headers = {}
            headers['hto'] = request.get('hto','all')
            headers['hfrom'] = self.__uid
            headers['hid'] = random.random()
            headers['htype'] = 'req'
            headers['httl'] = request.get('httl', 2)
        elif meth == 'push' or meth == 'pull' or meth == 'gap':
            headers = {}
            headers['hto'] = request.get('hfrom', 'any')
            headers['hfrom'] = self.__uid
            headers['hid'] = request.get('hid', None)
            headers['httl'] = 4
            headers['htype'] = 'rep'
        elif meth == 'gen_rand_push' or meth == 'gen_rand_pull':
            headers = {}
            headers['hto'] = request.get('hto','any')
            headers['hfrom'] = self.__uid
            headers['hid'] = random.random()
            headers['htype'] = 'req'
            headers['httl'] = request.get('httl', 5) #should be higher


        return headers

    def process(self, request):

        logging.debug('PROCESS : %s' % (request,))

        result = {}
        meth = request.get('m', None)
        headers = request.get('headers', {})

        if 'posts' in request:
            for post in request['posts']:
                try:
                    if isinstance(post, dict):
                        #self.post__(msg=post['msg'],perms=post['perms'])
                        self.__post(**post)
                    elif isinstance(post, list):
                        self.__post(*post)

                except StoreError as err:
                    if str(err) != "column sig is not unique":
                        logging.exception(err)

        if 'query' in request:
            meth = request['query']['m']

        if meth == 'get':
            limit = request['limit']
            result['posts'] = self.__get(limit=limit)
        elif meth == 'gen_push' or meth == 'gen_rand_push':
            result['posts'] = self.__get(self.__uid, limit=1)
        elif meth == 'gen_pull' or meth == 'gen_rand_push':
            result['query'] = self.__gen_pull()
        elif meth == 'pull':
            uid = request['query']['uid']
            friends = request['query']['friends']
            result['posts'] = self.__pull(uid, friends)
        elif meth == 'gen_gap':
            result['query'] = self.__gen_pull()
        elif meth == 'gap':
            uid = request['query']['uid']
            friends = request['query']['friends']
            result['posts'] = self.__gap(uid, friends)

        result['headers'] = self.__get_headers(headers, meth)
        return result

    def close(self):
        self.__con.close()


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
