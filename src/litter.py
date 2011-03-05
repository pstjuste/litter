
import socket
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

# Sender classes
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
        self.sock = MulticastServer.init_mcast()

    @staticmethod
    def init_mcast(port=MCAST_PORT, addr=MCAST_ADDR):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except AttributeError:
            pass

        s.setsockopt(socket.SOL_IP, socket.IP_MULTICAST_TTL, 20)
        s.setsockopt(socket.SOL_IP, socket.IP_MULTICAST_LOOP, 1)

        s.bind(('', port))

        intf = socket.gethostbyname(socket.gethostname())
        s.setsockopt(socket.SOL_IP, socket.IP_MULTICAST_IF, \
            socket.inet_aton(intf))
        s.setsockopt(socket.SOL_IP, socket.IP_ADD_MEMBERSHIP, \
            socket.inet_aton(addr) + socket.inet_aton(intf))

        return s

    def run(self):
        while True:
            data, addr = self.sock.recvfrom(1024)
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
            self.queue.put((data, UDPSender(self.sock, addr)))


class HTTPHandler(BaseHTTPServer.BaseHTTPRequestHandler):

    def do_GET(self):
        print 'doing get'
        presults = urlparse.urlparse(self.path)
        request = urlparse.parse_qs(presults[4])
        self.process_request(request)

    def do_POST(self):
        print 'doing post'
        clen = int(self.headers.get('Content-Length'))
        request = urlparse.parse_qs(self.rfile.read(clen))
        print "request %s " % request
        self.process_request(request)

    def process_request(self, request):
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
            print data
            request = json.loads(data)

            print 'request from %s >> %s' % (sender.dest, request)
            response = self.litstore.process(request)

            rthread = ResponseThread(response, sender, self.uid)
            rthread.start()


class ResponseThread(threading.Thread):

    def __init__(self, response, sender, uid):
        threading.Thread.__init__(self)
        self.response = response
        self.sender = sender

    def run(self):
        print 'response = ', repr(self.response)
        if isinstance(self.sender, HTTPSender):
            data = json.dumps(self.response)
            self.sender.send(data)
        else:
            for post in self.response:
                data = json.dumps(post)
                print 'reply to %s >> %s' % (self.sender.dest, data)
                self.sender.send(data)
                time.sleep(1)


# TODO - better time range right now it requests everything
def discover_msg(uid='uid', begin = 0, until = sys.maxint):
    kwargs = {}
    kwargs['uid'] = random.randint(0, sys.maxint)
    kwargs['begin'] = begin
    kwargs['until'] = until
    kwargs['m'] = 'discover'
    return kwargs

def main():

    uid = sys.argv[1]

    queue = Queue.Queue()

    mserver = MulticastServer(queue)
    mserver.start()

    userver = UnicastServer(queue)
    userver.start()

    httpd = HTTPThread(queue)
    httpd.start()

    wthread = WorkerThread(queue, uid)
    wthread.start()

    # heartbeat loop set for every 5 min
    while True:
        userver.sock.sendto(json.dumps(discover_msg(uid)), \
            (MCAST_ADDR, MCAST_PORT))
        time.sleep(300)

    mserver.join()
    userver.join()
    wthread.join()

if __name__ == '__main__':
    main()

