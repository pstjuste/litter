
import socket, json, time, random, sys, hashlib, urllib

def post_msg(uid, msg, tstamp = time.time()):
    kwargs = {}
    kwargs['uid'] = uid
    kwargs['tstamp'] = tstamp
    kwargs['msg'] = msg

    #TODO - postid has to be string type in database
    #shash = hashlib.sha1()
    #shash.update(str(uid) + msg + str(tstamp))
    #kwargs['postid'] = int(shash.digest())

    kwargs['postid'] = random.randint(0, sys.maxint)
    kwargs['m'] = 'post'

    return json.dumps(kwargs)

def get_msg(uid=None, begin = 0, until = sys.maxint):
    kwargs = {}
    kwargs['uid'] = uid
    kwargs['begin'] = begin
    kwargs['until'] = until
    kwargs['m'] = 'get_posts'

    return json.dumps(kwargs)

def http_main():

    uid = random.randint(0, sys.maxint)
    msg = 'this is my tcp message, litter woohoo'
    #params = urllib.urlencode({ 'json' : post_msg(uid, msg)})
    params = urllib.urlencode({ 'json' : get_msg()})

    print params

    f = urllib.urlopen("http://127.0.0.1:8000/", params)

    print 'received ', f.read()
    

def main(port=50000, addr='239.192.1.100'):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(('', 0))

    uid = random.randint(0, sys.maxint)
    msg = "this is my message, litter all day and all night"

    #s.sendto(post_msg(uid, msg), (addr, port))

    s.sendto(get_msg(), (addr, port))

    while True:
        data, addr = s.recvfrom(1024)
        print "from %s data %s" % (addr, data)

if __name__ == '__main__':
    http_main()
    main(**{ 'addr' : '127.0.0.1'})
