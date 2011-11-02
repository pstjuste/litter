#!/usr/bin/env python

import socket
import os
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
import getopt
from litterstore import LitterStore, StoreError

MCAST_ADDR = "239.192.1.100"
MCAST_PORT = 50000
LOOP_ADDR = "127.0.0.1"
IP_ANY = "0.0.0.0"

# Log everything, and send it to stderr.
logging.basicConfig(level=logging.DEBUG)

class Sender:
    """Base class sender interface"""

    dest = 'not assigned'

    def send(self, data):
        """Not implemented"""
        raise Exception("Base class, no implementation")


class UDPSender(Sender):
    """Implements sender over UDP socket"""

    def __init__(self, sock, intfs, dest):
        self.sock = sock
        self.dest = dest
        self.intfs = intfs

    def send(self, data):
        """Simply sends over UDP socket"""
        for intf in self.intfs:
            self.sock.setsockopt(socket.SOL_IP, socket.IP_MULTICAST_IF,
                socket.inet_aton(intf))
            self.sock.sendto(data, self.dest)

class HTTPSender(Sender):
    """Implements sender over HTTP protocol"""

    def __init__(self, queue, dest):
        self.queue = queue
        self.dest = dest

    def send(self, data):
        """Send message by putting in queue for processing"""
        self.queue.put((None, data))

    def send_error(self, excep):
        """Send error by putting in queue"""
        self.queue.put((excep, None))


class MulticastServer(threading.Thread):
    """Listens for multicast and put them in queue"""

    def __init__(self, queue, devs):
        threading.Thread.__init__(self)
        self.queue = queue
        self.running = threading.Event()
        self.intfs = [MulticastServer.get_ip(d) for d in devs]
        self.sock = MulticastServer.init_mcast() 

    # from http://code.activestate.com/recipes/439094-get-the-ip-address-
    # associated-with-a-network-inter/
    @staticmethod
    def get_ip(ifname):
        """Retreives the ip address of an interface (Linux only)"""
        ip = ""
        print ifname
        if os.name != "nt":
            import fcntl
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            ip = socket.inet_ntoa(fcntl.ioctl(
                            s.fileno(),
                            0x8915,  # SIOCGIFADDR
                            struct.pack('256s', ifname[:15])
                            )[20:24])
        else:
            ip =([ip for ip in socket.gethostbyname_ex(socket.gethostname())[2]
                  if not ip.startswith("127.")][0]) 
        return ip

    @staticmethod
    def init_mcast(intf=IP_ANY, port=MCAST_PORT, addr=MCAST_ADDR):
        """Initilizes a multicast socket"""

        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        except AttributeError as ex:
            logging.exception(ex)

        s.setsockopt(socket.SOL_IP, socket.IP_MULTICAST_TTL, 255)
        s.setsockopt(socket.SOL_IP, socket.IP_MULTICAST_LOOP, 1)

        s.bind(('', port))

        s.setsockopt(socket.SOL_IP, socket.IP_ADD_MEMBERSHIP,
            socket.inet_aton(addr) + socket.inet_aton(intf))

        return s

    @staticmethod
    def close_mcast(s, addr=MCAST_ADDR):
        intf = s.getsockname()[0]
        s.setsockopt(socket.SOL_IP, socket.IP_DROP_MEMBERSHIP,
            socket.inet_aton(addr) + socket.inet_aton(intf))
        s.close()


    def run(self):
        """Waits in a loop for incoming packet then puts them in queue"""

        self.running.set() #set to true
        while self.running.is_set():
            data, addr = self.sock.recvfrom(1024)
            self.queue.put((data, UDPSender(self.sock, self.intfs, addr)))
            print "MulticastServer: sender ", repr(addr), data

    def stop(self):
        """Set run to false, and send an empty message"""

        self.running.clear() 
        msender = UDPSender(self.sock, self.intfs, self.sock.getsockname())
        msender.send("")

    def __del__(self):
        self.close_mcast(self.sock)

class HTTPHandler(BaseHTTPServer.BaseHTTPRequestHandler):
    """Handles HTTP requests"""

    def do_GET(self):
        """Handles get requests"""

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
        """Handles post requests"""

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
        """Extract json from request and queues it for processing"""

        print "HTTPHandler: %s " % request
        data = request['json'][0]
        queue = Queue.Queue()
        self.server.queue.put((data, HTTPSender(queue, self.client_address)))
        # waits for response from workerthread
        err, data = queue.get()

        if err:
            #Exception happened, TODO do something better here:
            self.send_error(500, str(err))
        else:
            self.send_response(200)
            self.send_header("Content-type", "text/x-json; charset=utf-8")
            self.end_headers()
            self.wfile.write(data.encode("utf-8"))

    def process_file(self, path):
        """Handles HTTP file requests"""

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

    def __init__(self, queue, addr=LOOP_ADDR, port=8000):
        threading.Thread.__init__(self)
        self.port = port
        self.http = BaseHTTPServer.HTTPServer(('0.0.0.0', port), HTTPHandler)
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

    def __init__(self, queue, rqueue, name):
        threading.Thread.__init__(self)
        self.queue = queue
        self.rqueue = rqueue
        self.name = name

    def run(self):
        # SQL database has to be created in same thread
        self.litstore = LitterStore(self.name)
        while True:
            data, sender = self.queue.get()
            if data == None or len(data) < 2:
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
                response = self.litstore.process(request, sender.dest)
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


def usage():
    print "usage: ./litter.py [-i intf] [-n name] [-p port]"


def main():

    devs = []
    name = socket.gethostname()
    port = "8080";

    try:
        opts, args = getopt.getopt(sys.argv[1:], "i:n:p:")
    except getopt.GetoptError, err:
        usage()
        sys.exit()

    for o, a in opts:
        if o == "-i":
            devs.append(a)
        elif o == "-n":
            name = a
        elif o == "-p":
            port = a
        else:
            usage()
            sys.exit()

    queue = Queue.Queue()
    rqueue = Queue.Queue()

    mserver = MulticastServer(queue, devs)
    mserver.start()

    rthread = ResponseThread(rqueue)
    rthread.start()

    wthread = WorkerThread(queue, rqueue, name)
    wthread.start()

    httpd = HTTPThread(queue, port=int(port))
    httpd.start()

    # wait a few seconds for threads to setup
    time.sleep(5)

    addr = (MCAST_ADDR, MCAST_PORT)
    sender = UDPSender(mserver.sock, mserver.intfs, addr)

    pull_req = { 'm' : 'pull_req' }
    pull_data = json.dumps(pull_req)

    gap_req = { 'm' : 'gap_req' }
    gap_data = json.dumps(gap_req)

    try:
        while True:
            queue.put((pull_data, sender))
            queue.put((gap_data, sender))
            time.sleep(60)
    except:
        #Control-C will put us here, let's stop the other threads:
        httpd.stop()
        mserver.stop()
        wthread.stop()
        rthread.stop()


if __name__ == '__main__':
    main()

