#!/usr/bin/env python
"""
A very lightweight Litter (LAN + microblog) implementation with absolutely no
security mechanisms.  Messages are stored in a database and relationships are
stored in a in process data structure.  Incoming posts from both remote servers
and local clients are sent to the "post" method.  A remote Litter serve can
obtain any missing state via the "discover" method.  "discover" stores state,
so that if a server receives identitical discover "begin" times, they are
ignored.  A client can get posts via the "get_posts" method.

Todo:  discover state should potentially be stored into the database, so we
can ignore duplicate requests after a local Litter restart.
"""
import unittest, sqlite3, time, sys, random, hashlib

class StoreError(Exception):
    pass

class LitterStore:
  def __init__(self, uid, test = False):
    self.con = sqlite3.connect(":memory:" if test else uid + ".db")
    self.uid = uid
    self.discovered = {}
    self._db_call("CREATE TABLE IF NOT EXISTS posts \
        (uid TEXT, postid INTEGER, msg TEXT, txtime INTEGER, rxtime INTEGER, \
        hashid TEXT, PRIMARY KEY(hashid ASC))")
    cid = self._db_call("SELECT MAX(postid) FROM posts WHERE uid == ?", (uid, ))
    self.nextid = 0 if cid[0][0] == None else cid[0][0] + 1

  def _db_call(self, action, params = None):
    print "dbcall -- %s %s" % (action, params)
    cur = self.con.cursor()
    cur.execute(action, params) if params != None else cur.execute(action)
    result = cur.fetchall()
    cur.close()
    self.con.commit()
    return result

  def _cal_hash(self, uid, msg, txtime, postid):
    hash = hashlib.sha1()
    tohash = str(uid) + msg + str(txtime) + str(postid)
    #tohash is potentially unicode, if msg is, so we need to convert
    #back to bytes, to do this, we use utf-8:
    tohash = tohash.encode('utf-8')
    hash.update(tohash)
    return hash.hexdigest()

  def post(self, msg, uid=None, txtime = None, postid = -1, hashid=None):
    # we always update the received time
    rxtime = int(time.time())

    if uid == None:
      uid = self.uid

    if txtime == None:
      txtime = rxtime

    if len(msg) > 140:
      raise Exception("message is too long, has to be less than 140 chars")

    if None != hashid:
      if hashid != self._cal_hash(uid, msg, txtime, postid):
        raise Exception("hashid doesn't match:" + \
                        " uid: %s msg: %s time: %s postid: %s badhash: %s" \
                        % (uid, msg, txtime, postid, hashid))

    if uid == self.uid and hashid == None:
      postid = self.nextid
      hashid = self._cal_hash(uid, msg, txtime, postid)
      self.nextid += 1
    if postid == -1:
      raise Exception("Invalid postid: " + str(postid))

    try:
      self._db_call("INSERT INTO posts (uid, postid, txtime, rxtime, msg, hashid) \
          VALUES (?, ?, ?, ?, ?, ?)", (uid, postid, txtime, rxtime, msg, hashid))
    except sqlite3.IntegrityError as ie:
      raise StoreError(str(ie))    
    return [(uid, postid, txtime, msg, hashid)]

  def get_posts(self, uid = None, begin = 0, until = sys.maxint, limit = 100):
    msg = "SELECT uid, postid, rxtime, msg, hashid FROM posts WHERE "
    if uid == None:
      msg = msg + "rxtime > ? and rxtime < ? ORDER BY rxtime DESC LIMIT ?", \
          (begin, until, limit)
    else:
      msg = msg + "uid == ? and rxtime > ? and rxtime < ? ORDER BY rxtime DESC \
          LIMIT ?", (uid, begin, until, limit)

    return self._db_call(msg[0], msg[1])

  def discover(self, uid, begin, until):
    if uid in self.discovered:
      if self.discovered[uid] == begin:
        return []
    self.discovered[uid] = begin
    return self._db_call("SELECT uid, postid, txtime, msg, hashid FROM posts \
        WHERE txtime > ? and txtime < ? LIMIT 50", (begin, until))

  def close(self):
    self.con.close()

  def process(self, request):
    results = []
    method = request['m']
    del request['m']

    if (method == 'discover'):
      results = self.discover(**request)
    elif (method == 'post'):
      results = self.post(**request)
    elif (method == 'get_posts'):
      results = self.get_posts(**request)

    return self.process_results(results)

  def process_results(self, response):
    results = []
    for post in response:
      kwargs = {}
      kwargs['uid'] = post[0]
      kwargs['postid'] = post[1]
      kwargs['txtime'] = post[2]
      kwargs['msg'] = post[3]
      kwargs['hashid'] = post[4]
      kwargs['m'] = 'post'
      results.append(kwargs)

    return results

class LitterUnit(unittest.TestCase):
  def test_post(self):
    litter = LitterStore("David", test = True)
    litter.post("David", "Litter is working great!")
    self.assertEqual(1, len(litter.get_posts()))
    litter.post("David", "Litter is still working great!")
    self.assertEqual(2, len(litter.get_posts()))
    self.assertEqual(0, len(litter.get_posts("Fail")))
    self.assertEqual("Litter is still working great!", litter.get_posts()[1][3])
    self.assertRaises(Exception, litter.post, ("Bob", "Litter is still working great!"))
    self.assertEqual(2, len(litter.get_posts()))
    litter.post("Bob", "Bob's test", postid = 0)
    self.assertEqual(3, len(litter.get_posts()))
    self.assertEqual("Bob's test", litter.get_posts(uid = "Bob")[0][3])
    litter.close()

  def test_discover(self):
    litter = LitterStore("David", test = True)
    before = int(time.time()) - 1
    self.assertEqual(len(litter.discover("Bob", 0, sys.maxint)), 0)
    litter.post("David", "Litter is working great!")
    litter.post("David", "Litter is still working great!")
    now = time.time()
    self.assertEqual(len(litter.discover("Bob", 0, sys.maxint)), 0)
    self.assertEqual(len(litter.discover("Bob", before, sys.maxint)), 2)
    self.assertEqual(len(litter.discover("Bob", now, sys.maxint)), 0)

  def test_rpc(self):
    litter = LitterStore("David", test = True)
    before = int(time.time()) - 1
    after = int(time.time()) + 1
    litter.post(**{"uid" : "David", "msg" : "Litter is working great!"})
    litter.post(**{"uid" : "David", "msg" : "Litter is still working great!"})
    litter.post(**{"uid" : "Alice", "postid" : 2, "txtime" : before - 1, "msg" : "Hmm!"})
    self.assertEqual(len(litter.discover(**{"uid" : "Bob", "begin" : before, "until" : sys.maxint})), 2)
    self.assertEqual(len(litter.discover(**{"uid" : "Bob", "begin" : before, "until" : sys.maxint})), 0)
    self.assertEqual(len(litter.discover(**{"uid" : "Bob", "begin" : after, "until" : sys.maxint})), 0)
    self.assertEqual(len(litter.discover(**{"uid" : "Bob", "begin" : 0, "until" : sys.maxint})), 3)

if __name__ == '__main__':
  unittest.main()
