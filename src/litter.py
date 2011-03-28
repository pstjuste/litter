#!/usr/bin/env python

import socket
import fcntl
import struct
import time
import sys
import json
import random
import threading
import urlparse
import Queue
import BaseHTTPServer
import logging
import urllib
import pickle
from litterstore import LitterStore, StoreError

MCAST_ADDR = "239.192.1.100"
MCAST_PORT = 50000

# Log everything, and send it to stderr.
logging.basicConfig(level=logging.DEBUG)

# Sender base class
class Sender:
    dest = 'not assigned'

    def send(self, data):
        raise Exception("Base class, no implementation")


class UDPSender(Sender):

    def __init__(self, sock, dest):
        self.sock = sock
        self.dest = dest

    def send(self, data):
        self.sock.sendto(data, self.dest)


class HTTPSender(Sender):

    def __init__(self, queue, dest):
        self.queue = queue
        self.dest = dest

    def send(self, data):
        self.queue.put((None, data))

    def send_error(self, excep):
        self.queue.put((excep, None))


class MulticastServer(threading.Thread):

    def __init__(self, queue, intf):
        threading.Thread.__init__(self)
        self.queue = queue
        self.intf = intf
        self.running = threading.Event()
        self.sock = MulticastServer.init_mcast(intf)

    # from http://code.activestate.com/recipes/439094-get-the-ip-address-
    # associated-with-a-network-inter/
    @staticmethod
    def get_ip_address(ifname):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        return socket.inet_ntoa(fcntl.ioctl(
            s.fileno(),
            0x8915,  # SIOCGIFADDR
            struct.pack('256s', ifname[:15])
            )[20:24])

    @staticmethod
    def init_mcast(intf="127.0.0.1", port=MCAST_PORT, addr=MCAST_ADDR):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except AttributeError as ex:
            logging.exception(ex)

        s.setsockopt(socket.SOL_IP, socket.IP_MULTICAST_TTL, 255)
        s.setsockopt(socket.SOL_IP, socket.IP_MULTICAST_LOOP, 1)

        s.bind(('', port))

        print intf

        s.setsockopt(socket.SOL_IP, socket.IP_MULTICAST_IF, \
            socket.inet_aton(intf) + socket.inet_aton('0.0.0.0'))

        s.setsockopt(socket.SOL_IP, socket.IP_ADD_MEMBERSHIP, \
            socket.inet_aton(addr) + socket.inet_aton(intf))

        return s

    def run(self):
        self.running.set() #set to true
        while self.running.is_set():
            data, addr = self.sock.recvfrom(1024)
            print "MulticastServer: sender ", repr(addr), data
            # we ignore our own requests
            if addr[0] != self.intf:
                self.queue.put((data, UDPSender(self.sock, addr)))

    def stop(self):
        """set run to false, and send an empty message"""
        self.running.clear() 
        msender = UDPSender(self.sock, self.sock.getsockname())
        msender.send("")


class HTTPHandler(BaseHTTPServer.BaseHTTPRequestHandler):

    def do_GET(self):
        try:
            if self.path.startswith('/api'):
                presults = urlparse.urlparse(self.path)
                request = urlparse.parse_qs(presults[4])
                self.process_request(request)
            else:
                self.process_file(self.path)
        except Exception as ex:
            self.send_error(400, str(ex))
            logging.exception(ex)

    def do_POST(self):
        try:
            if self.path.startswith('/api'):
                presults = urlparse.urlparse(self.path)
                clen = int(self.headers.get('Content-Length'))
                request = urlparse.parse_qs(self.rfile.read(clen))
                self.process_request(request)
            else:
                self.process_file(self.path)
        except Exception as ex:
            self.send_error(400, str(ex))
            logging.exception(ex);

    def process_request(self, request):
        print "HTTPHandler: %s " % request
        data = request['json'][0]
        queue = Queue.Queue()
        self.server.queue.put((data, HTTPSender(queue, self.client_address)))
        (err, data) = queue.get()
        if err:
            #Exception happened, TODO do something better here:
            self.send_error(500, str(err))
        else:
            self.send_response(200)
            self.send_header("Content-type", "text/x-json; charset=utf-8")
            self.end_headers()
            self.wfile.write(data.encode("utf-8"))

    def process_file(self, path):
        if path == "/":
            self.send_file("web/litter.html", "text/html")
        elif path == "/litter.css":
            self.send_file("web/litter.css", "text/css")
        elif path == "/litter.js":
            self.send_file("web/litter.js", "text/javascript")
        elif path == "/jquery.js":
            self.send_file("web/jquery.js", "text/javascript")
        elif path == "/jquery-ui.js":
            self.send_file("web/jquery-ui.js", "text/javascript")
        elif path == "/jquery-ui.css":
            self.send_file("web/jquery-ui.css", "text/css")
        elif path == "/json2.js":
            self.send_file("web/json2.js", "text/javascript")
        elif path == "/md5.js":
            self.send_file("web/md5.js", "text/javascript")
        elif path == "/ping":
            #just to have a test method
            self.send_response(200)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write("pong")
        else:
            self.send_error(404, "Not found")

    def send_file(self, path, ctype):
        try:
            f = open(path)
            data = f.read()
            f.close()
            self.send_response(200)
            self.send_header("Content-type", ctype)
            self.end_headers()
            self.wfile.write(data)
        except Exception as ex:
            logging.exception(ex)


class HTTPThread(threading.Thread):

    def __init__(self, queue):
        threading.Thread.__init__(self)
        self.port = 8000
        self.http = BaseHTTPServer.HTTPServer(('127.0.0.1', self.port), HTTPHandler)
        self.http.queue = queue
        self.running = threading.Event()

    def run(self):
        self.running.set()
        while self.running.is_set(): 
          self.http.handle_request()

    def stop(self):
        self.running.clear()
        #wake up the server:
        urllib.urlopen("http://127.0.0.1:%i/ping" % (self.port,)).read()


class WorkerThread(threading.Thread):

    def __init__(self, queue, rqueue, uid, sock):
        threading.Thread.__init__(self)
        self.queue = queue
        self.rqueue = rqueue
        self.uid = uid
        self.sock = sock

    def run(self):
        # SQL database has to be created in same thread
        self.litstore = LitterStore(self.uid)
        while True:
            data, sender = self.queue.get()
            if not sender:
                # we close DB then break out of loop to stop thread
                self.litstore.close()
                break
            data = unicode(data, "utf-8")
            print 'WorkerThread: %s : %s' % (sender.dest, data)

            try:
                request = json.loads(data)

                # save method locally before sending it litterstore
                # just in case it gets modified
                method = request['m']
                response = self.litstore.process(request)

                if method == 'post' and isinstance(sender, HTTPSender):
                    # if post from http it means this is a local post so
                    # we neeed to broadcast to multicast
                    addr = (MCAST_ADDR, MCAST_PORT)
                    msender = UDPSender(self.sock, addr)
                    self.rqueue.put((response, msender))
                elif method != 'post' and isinstance(sender, UDPSender):
                    # we send response back through sender of request
                    self.rqueue.put((response, sender))

                if isinstance(sender, HTTPSender):
                    # also send reply back to HTTP path directly from
                    # thread, since it's put in queue for HTTP thread
                    data = json.dumps(response, ensure_ascii=False)
                    sender.send(data)

            except StoreError as ie:
                if str(ie) == "column hashid is not unique":
                    #this means we got a duplicate, no need to log:
                    pass
                else:
                    if isinstance(sender, HTTPSender):
                        sender.send_error(ex)
                    logging.exception(ie)
            except Exception as ex:
                if isinstance(sender, HTTPSender):
                    sender.send_error(ex)
                logging.exception(ex)

    def stop(self):
        self.queue.put((None,None))


class ResponseThread(threading.Thread):

    def __init__(self, rqueue):
        threading.Thread.__init__(self)
        self.rqueue = rqueue

    def run(self):
        while True:
            response, sender = self.rqueue.get()

            if None == sender:
                # time to exit loop and thread
                break

            for post in response:
                data = json.dumps(post, ensure_ascii=False)
                print 'ResponseThread: %s : %s' % (sender.dest, data)
                sender.send(data.encode("utf-8"))
                time.sleep(0.1)

    def stop(self):
        self.rqueue.put((None, None))


def build_msg(method, uid, begin = 0, until = sys.maxint):
    kwargs = {}
    kwargs['m'] = method
    kwargs['uid'] = uid
    kwargs['begin'] = begin
    kwargs['until'] = until
    return json.dumps(kwargs, ensure_ascii=False)


def load_state():
    state = { 'ltime' : 0}
    try:
        state_file = open('state.pkl', 'rb')
        state = pickle.load(state_file)
    except IOError as ex:
        print ex

    return state


def update_state(state):
    try:
        state_file = open('state.pkl', 'wb')
        pickle.dump(state, state_file)
    except IOError as ex:
        print ex 

def main():

    uid = socket.gethostname()
    intf = MulticastServer.get_ip_address('tapipop')

    queue = Queue.Queue()
    rqueue = Queue.Queue()

    httpd = HTTPThread(queue)
    httpd.start()

    mserver = MulticastServer(queue, intf)
    mserver.start()

    rthread = ResponseThread(rqueue)
    rthread.start()

    wthread = WorkerThread(queue, rqueue, uid, mserver.sock)
    wthread.start()

    state = load_state()

    print "state = %s" % state

    begin = int(state['ltime'])
    until = int(time.time())

    # wait a few seconds for threads to setup
    time.sleep(5)

    addr = (MCAST_ADDR, MCAST_PORT)
    try:
        while True:
            # update time and save state to filesystem
            state['ltime'] = time.time()
            update_state(state)

            data = build_msg('discover', uid, begin, until)
            mserver.sock.sendto(data, addr)
            print "MainThread : %s %s" % (data, addr)
            time.sleep(1080) # every 15 minutes
    except:
        #a Control-C will put us here, let's stop the other threads:
        httpd.stop()
        mserver.stop()
        wthread.stop()
        rthread.stop()


if __name__ == '__main__':
    main()

