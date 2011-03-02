#!/usr/bin/python
"""
A very lightweight Litter (LAN + Twitter) implementation with absolutely no
security mechanisms.  Messages are stored in a database and relationships are
stored in a in process data structure.  Incoming posts from both remote servers
and local clients are sent to the "post" method.  A remote Litter serve can
obtain any missing state via the "discover" method.  "discover" stores state,
so that if a server receives identitical discover "begin" times, they are
ignored.  A client can get posts via the "get_posts" method.

Todo:  discover state should potentially be stored into the database, so we
can ignore duplicate requests after a local Litter restart.
"""
import unittest, sqlite3, time, sys, random

class LitterStore:
  def __init__(self, uid, test = False):
    self.con = sqlite3.connect(":memory:" if test else uid + ".db")
    self.uid = uid
    self.discovered = {}
    self._db_call("CREATE TABLE IF NOT EXISTS posts \
        (uid TEXT, postid INTEGER, msg TEXT, time INTEGER)")
    cid = self._db_call("SELECT MAX(postid) FROM posts WHERE uid == ?", (uid, ))
    self.nextid = 0 if cid[0][0] == None else cid[0][0] + 1

  def _db_call(self, action, params = None):
    cur = self.con.cursor()
    cur.execute(action, params) if params != None else cur.execute(action)
    result = cur.fetchall()
    cur.close()
    self.con.commit()
    return result

  def post(self, uid, msg, tstamp = int(time.time()), postid = -1):
    if uid == self.uid:
      postid = self.nextid
      self.nextid += 1
    if postid == -1:
      raise Exception("Invalid postid: " + str(postid))
    self._db_call("INSERT INTO posts (uid, postid, time, msg) VALUES (?, ?, ?, ?)", \
        (uid, postid, tstamp, msg))

  def get_posts(self, uid = None, begin = 0, until = sys.maxint):
    msg = "SELECT uid, postid, time, msg FROM posts WHERE "
    if uid == None:
      msg = msg + "time > ? and time < ?", (begin, until)
    else:
      msg = msg + "uid == ? and time > ? and time < ?", (uid, begin, until)
    return self._db_call(msg[0], msg[1])

  def discover(self, uid, begin, until):
    if uid in self.discovered:
      if self.discovered[uid] == begin:
        return []
    self.discovered[uid] = begin
    return self._db_call("SELECT uid, postid, time, msg FROM posts \
        WHERE time > ? and time < ?", (begin, until))

  def close(self):
    self.con.close()

  def process(self, method, kwargs):
    results = []

    if (method == 'discover'):
      for post in self.discover(**kwargs):
        kwargs = {}
        kwargs['uid'] = post[0]
        kwargs['postid'] = post[1]
        kwargs['tstamp'] = post[2]
        kwargs['msg'] = post[3]
        request = { 'method' : 'post', 'kwargs' : kwargs }
        results.append(request)
    elif (method == 'post'):
      self.post(**kwargs)
    elif (method == 'get_posts'):
      results = self.get_posts(**kwargs)

    return results

class LitterUnit(unittest.TestCase):
  def test_post(self):
    litter = Litter("David", test = True)
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
    litter = Litter("David", test = True)
    before = int(time.time()) - 1
    self.assertEqual(len(litter.discover("Bob", 0, sys.maxint)), 0)
    litter.post("David", "Litter is working great!")
    litter.post("David", "Litter is still working great!")
    now = time.time()
    self.assertEqual(len(litter.discover("Bob", 0, sys.maxint)), 0)
    self.assertEqual(len(litter.discover("Bob", before, sys.maxint)), 2)
    self.assertEqual(len(litter.discover("Bob", now, sys.maxint)), 0)

  def test_rpc(self):
    litter = Litter("David", test = True)
    before = int(time.time()) - 1
    after = int(time.time()) + 1
    litter.post(**{"uid" : "David", "msg" : "Litter is working great!"})
    litter.post(**{"uid" : "David", "msg" : "Litter is still working great!"})
    litter.post(**{"uid" : "Alice", "postid" : 2, "time" : before - 1, "msg" : "Hmm!"})
    self.assertEqual(len(litter.discover(**{"uid" : "Bob", "begin" : before, "until" : sys.maxint})), 2)
    self.assertEqual(len(litter.discover(**{"uid" : "Bob", "begin" : before, "until" : sys.maxint})), 0)
    self.assertEqual(len(litter.discover(**{"uid" : "Bob", "begin" : after, "until" : sys.maxint})), 0)
    self.assertEqual(len(litter.discover(**{"uid" : "Bob", "begin" : 0, "until" : sys.maxint})), 3)

if __name__ == '__main__':
  unittest.main()
