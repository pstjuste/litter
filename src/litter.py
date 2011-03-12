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
from litterstore import LitterStore

MCAST_ADDR = "239.192.1.100"
MCAST_PORT = 50000

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
        self.queue.put(data)


# Producer thread
class MulticastServer(threading.Thread):

    def __init__(self, queue, intf, usock):
        threading.Thread.__init__(self)
        self.queue = queue
        self.usock = usock
        self.intf = intf
        self.sock = MulticastServer.init_mcast(self.intf)

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
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except AttributeError:
            pass

        s.setsockopt(socket.SOL_IP, socket.IP_MULTICAST_TTL, 20)

        # we dont really need multicast on loopback for now
        #s.setsockopt(socket.SOL_IP, socket.IP_MULTICAST_LOOP, 1)

        s.bind(('', port))

        print intf

        s.setsockopt(socket.SOL_IP, socket.IP_MULTICAST_IF, \
            socket.inet_aton(intf))

        s.setsockopt(socket.SOL_IP, socket.IP_ADD_MEMBERSHIP, \
            socket.inet_aton(addr) + socket.inet_aton(intf))

        return s

    def run(self):
        while True:
            data, addr = self.sock.recvfrom(1024)
            print "MulticastServer: sender ", repr(addr), data
            # we ignore our own requests
            if addr[0] != self.intf:
                self.queue.put((data, UDPSender(self.usock, addr)))


# Producer thread
class UnicastServer(threading.Thread):

    def __init__(self, queue, intf, usock):
        threading.Thread.__init__(self)
        self.queue = queue
        self.intf = intf
        self.sock = usock

    @staticmethod
    def init_ucast(port=0, addr=''):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.bind((addr, port))
        return s

    def run(self):
        while True:
            data, addr = self.sock.recvfrom(1024)
            print "UnicastServer: sender ", repr(addr), data
            if addr[0] != self.intf:
                self.queue.put((data, UDPSender(self.sock, addr)))


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
            print ex

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
            print ex

    def process_request(self, request):
        print "HTTPHandler: %s " % request
        self.send_response(200)
        self.send_header("Content-type", "text/x-json")
        self.end_headers()

        queue = Queue.Queue()
        data = request['json'][0]
        self.server.queue.put((data, HTTPSender(queue, self.client_address)))
        self.wfile.write(queue.get())

    def process_file(self, path):
        if path == "/":
            self.send_file("web/litter.html", "text/html")
        elif path == "/litter.css":
            self.send_file("web/litter.css", "text/css")
        elif path == "/litter.js":
            self.send_file("web/litter.js", "text/javascript")
        elif path == "/jquery.js":
            self.send_file("web/jquery.js", "text/javascript")
        elif path == "jquery-ui.js":
            self.send_file("web/jquery-ui.js", "text/javascript")
        elif path == "/jquery-ui.css":
            self.send_file("web/jquery-ui.css", "text/css")

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
            print ex


class HTTPThread(threading.Thread):

    def __init__(self, queue):
        threading.Thread.__init__(self)
        self.http = BaseHTTPServer.HTTPServer(('127.0.0.1', 8000), HTTPHandler)
        self.http.queue = queue

    def run(self):
        self.http.serve_forever()


# Consumer thread
class WorkerThread(threading.Thread):

    def __init__(self, queue, uid, usock):
        threading.Thread.__init__(self)
        self.queue = queue
        self.uid = uid
        self.usock = usock

    def run(self):
        # SQL database has to be created in same thread
        self.litstore = LitterStore(self.uid)
        while True:
            data, sender = self.queue.get()
            print 'WorkerThread: %s : %s' % (sender.dest, data)

            # need try catch cause crazy things can happen
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
                    msender = UDPSender(self.usock, addr)
                    mthread = ResponseThread(response, msender, self.uid)
                    mthread.start()

                    # also send reply back to HTTP path
                    hthread = ResponseThread(response, sender, self.uid)
                    hthread.start()
                elif method != 'post':
                    # we send response back through sender of request
                    rthread = ResponseThread(response, sender, self.uid)
                    rthread.start()
            except Exception as ex:
                print ex


class ResponseThread(threading.Thread):

    def __init__(self, response, sender, uid):
        threading.Thread.__init__(self)
        self.response = response
        self.sender = sender

    def run(self):
        print 'ResponseThread: ', repr(self.sender.dest), repr(self.response)

        # If HTTP send all at once, if UDP send one by one
        # to avoid fragmentation, wait one second to minimize
        # probability of packet loss due to congestion
        if isinstance(self.sender, HTTPSender):
            data = json.dumps(self.response)
            self.sender.send(data)
        else:
            for post in self.response:
                data = json.dumps(post)
                print 'ResponseThread: %s : %s' % (self.sender.dest, data)
                self.sender.send(data)
                time.sleep(1)


def build_msg(method, uid, begin = 0, until = sys.maxint):
    kwargs = {}
    kwargs['m'] = method
    kwargs['uid'] = uid
    kwargs['begin'] = begin
    kwargs['until'] = until
    return json.dumps(kwargs)


def main():

    uid = socket.gethostname()
    intf = MulticastServer.get_ip_address('tapipop')

    # returns a UDP socket that is shared by multiple threads for sending
    # I'm not sure if sockets are thread safe
    # I am assuming that they are, NEED TO CHECK THAT
    usock = UnicastServer.init_ucast()
    queue = Queue.Queue()

    httpd = HTTPThread(queue)
    httpd.start()

    userver = UnicastServer(queue, intf, usock)
    userver.start()

    mserver = MulticastServer(queue, intf, usock)
    mserver.start()

    wthread = WorkerThread(queue, uid, usock)
    wthread.start()

    # wait a few seconds for threads to setup before sending first multicast
    time.sleep(5)

    addr = (MCAST_ADDR, MCAST_PORT)
    while True:
        # TODO - provide a more realistic time interval
        data = build_msg('discover', uid)
        usock.sendto(data, addr)
        time.sleep(300)


if __name__ == '__main__':
    main()

