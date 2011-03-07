
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

# from http://code.activestate.com/recipes/439094-get-the-ip-address-associated-with-a-network-inter/
def get_ip_address(ifname):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    return socket.inet_ntoa(fcntl.ioctl(
        s.fileno(),
        0x8915,  # SIOCGIFADDR
        struct.pack('256s', ifname[:15])
    )[20:24])


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

    def __init__(self, queue):
        self.queue = queue

    def send(self, data):
        self.queue.put(data)


# Producer thread
class MulticastServer(threading.Thread):

    def __init__(self, queue):
        threading.Thread.__init__(self)
        self.queue = queue
        self.intf = get_ip_address(sys.argv[1])
        self.sock = MulticastServer.init_mcast(self.intf)

    @staticmethod
    def init_mcast(intf="127.0.0.1", port=MCAST_PORT, addr=MCAST_ADDR):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except AttributeError:
            pass

        s.setsockopt(socket.SOL_IP, socket.IP_MULTICAST_TTL, 20)
        s.setsockopt(socket.SOL_IP, socket.IP_MULTICAST_LOOP, 1)

        s.bind(('', port))

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
                self.queue.put((data, UDPSender(self.sock, addr)))


# Producer thread
class UnicastServer(threading.Thread):

    def __init__(self, queue):
        threading.Thread.__init__(self)
        self.queue = queue
        self.sock = UnicastServer.init_ucast()

    @staticmethod
    def init_ucast(port=0, addr=''):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.bind((addr, port))
        return s

    def run(self):
        while True:
            data, addr = self.sock.recvfrom(1024)
            print "UnicastServer: sender ", repr(addr), data
            self.queue.put((data, UDPSender(self.sock, addr)))


class HTTPHandler(BaseHTTPServer.BaseHTTPRequestHandler):

    def do_GET(self):
        print 'HTTPHandler: doing get'
        presults = urlparse.urlparse(self.path)
        request = urlparse.parse_qs(presults[4])
        self.process_request(request)

    def do_POST(self):
        print 'HTTPHandler: doing post'
        clen = int(self.headers.get('Content-Length'))
        request = urlparse.parse_qs(self.rfile.read(clen))
        self.process_request(request)

    def process_request(self, request):
        print "HTTPHandler: %s " % request
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()

        tmp_queue = Queue.Queue()
        data = request['json'][0]
        self.server.queue.put((data, HTTPSender(tmp_queue)))
        self.wfile.write(tmp_queue.get())


class HTTPThread(threading.Thread):

    def __init__(self, queue):
        threading.Thread.__init__(self)
        self.http = BaseHTTPServer.HTTPServer(('', 8000), HTTPHandler)
        self.http.queue = queue

    def run(self):
        self.http.serve_forever()


# Consumer thread
class WorkerThread(threading.Thread):

    def __init__(self, queue, uid):
        threading.Thread.__init__(self)
        self.queue = queue
        self.uid = uid

    def run(self):
        # SQL database has to be created in same thread
        self.litstore = LitterStore(self.uid)
        while True:
            data, sender = self.queue.get()
            print 'WorkerThread: %s : %s' % (sender.dest, data)

            # need try catch cause crazy things can happen
            try:
                request = json.loads(data)
                response = self.litstore.process(request)
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
        print 'ResponseThread: ', repr(self.response)

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


def heartbeat(queue, sender, uid, disc):
    tstamp = time.time()
    begin = int(tstamp - 30.0)
    until = int(tstamp)

    # this will push posts via multicast to peers every 30 seconds
    # if new posts are available
    data = build_msg('get_posts', uid, begin, until)
    queue.put((data, sender))

    # check to see if we need to send discovery request
    if disc:
        data = build_msg('discover', uid)
        sender.send(data)


def main():

    uid = socket.gethostname()

    queue = Queue.Queue()

    mserver = MulticastServer(queue)
    mserver.start()

    userver = UnicastServer(queue)
    userver.start()

    httpd = HTTPThread(queue)
    httpd.start()

    wthread = WorkerThread(queue, uid)
    wthread.start()

    counter = 0
    while True:
        time.sleep(30)
        addr = (MCAST_ADDR, MCAST_PORT)
        disc = False

        # send discover request every 5 minutes
        if (counter % 10 == 0):
            disc = True

        heartbeat(queue, UDPSender(userver.sock, addr), uid, disc)
        counter += 1


if __name__ == '__main__':
    main()

