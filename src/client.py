
import socket, json, time, random, sys, hashlib

def post_msg(uid, msg, tstamp = time.time()):
    shash = hashlib.sha1()
    shash.update(str(uid) + msg + str(tstamp))

    kwargs = {}
    kwargs['uid'] = uid
    kwargs['tstamp'] = tstamp
    kwargs['msg'] = msg

    #TODO - postid has to be string type in database
    #kwargs['postid'] = int(shash.digest())
    kwargs['postid'] = random.randint(0, sys.maxint)

    return { 'method' : 'post', 'kwargs' : kwargs }

def get_msg(uid=None, begin = 0, until = sys.maxint):
    kwargs = {}
    kwargs['uid'] = uid
    kwargs['begin'] = begin
    kwargs['until'] = until

    return { 'method' : 'get_posts', 'kwargs' : kwargs }

def main(port=50000, addr='239.192.1.100'):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(('', 0))

    uid = random.randint(0, sys.maxint)
    msg = "this is my message, litter all day and all night"

    s.sendto(json.dumps(post_msg(uid, msg)), (addr, port))

    s.sendto(json.dumps(get_msg()), (addr, port))

    while True:
        data, addr = s.recvfrom(1024)
        print "from %s data %s" % (addr, data)

if __name__ == '__main__':
    main()
