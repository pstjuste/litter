#!/usr/bin/env python

import socket, json, time, random, sys, urllib

def post_msg(uid, msg):
    kwargs = {}
    kwargs['uid'] = uid
    kwargs['msg'] = msg
    kwargs['m'] = 'post'
    result =  json.dumps(kwargs)
    print result
    return result

def get_msg(uid=None, begin = 0, until = sys.maxint):
    kwargs = {}
    kwargs['uid'] = uid
    kwargs['begin'] = begin
    kwargs['until'] = until
    kwargs['m'] = 'get_posts'
    result = json.dumps(kwargs)
    print result
    return result

def http_main(uid, msg):

    if msg != "":
        params = urllib.urlencode({ 'json' : post_msg(uid, msg)})
    else:
        params = urllib.urlencode({ 'json' : get_msg()})

    print 'sent params ', repr(params)

    f = urllib.urlopen("http://127.0.0.1:8000/api", params)

    print 'received ', repr(f.read())
    

def main():

    uid = socket.gethostname()
    while True:
        msg = raw_input('Enter message: ')
        http_main(uid, msg)


if __name__ == '__main__':
    main()
