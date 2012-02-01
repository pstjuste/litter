#!/usr/bin/env python

import os
import socket
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

from litterstore import LitterStore
from litterrouter import *

# Log everything, and send it to stderr.
logging.basicConfig(level=logging.DEBUG)

class MulticastServer(threading.Thread):
    """Listens for multicast and put them in queue"""

    # from http://code.activestate.com/recipes/439094-get-the-ip-address-
    # associated-with-a-network-inter/
    @staticmethod
    def get_ip(ifname):
        """Retreives the ip address of an interface (Linux only)"""
        ip = ifname
        if os.name != "nt":
            import fcntl
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            ip = socket.inet_ntoa(fcntl.ioctl(
                            s.fileno(),
                            0x8915,  # SIOCGIFADDR
                            struct.pack('256s', ifname[:15])
                            )[20:24])
                            
        return ip

    @staticmethod
    def init_mcast(intfs=[], port=PORT, addr=MCAST_ADDR):
        """Initilizes a multicast socket"""

        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        if os.name != "nt":
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        s.setsockopt(socket.SOL_IP, socket.IP_MULTICAST_TTL, 1)
        s.setsockopt(socket.SOL_IP, socket.IP_MULTICAST_LOOP, 0)

        s.bind(('', port))

        for intf in intfs:
            s.setsockopt(socket.SOL_IP, socket.IP_ADD_MEMBERSHIP,
                socket.inet_aton(addr) + socket.inet_aton(intf))

        return s

    @staticmethod
    def close_mcast(s, addr=MCAST_ADDR):
        intf = s.getsockname()[0]
        s.setsockopt(socket.SOL_IP, socket.IP_DROP_MEMBERSHIP,
            socket.inet_aton(addr) + socket.inet_aton(intf))
        s.close()

    def __init__(self, queue, devs):
        threading.Thread.__init__(self)
        self.queue = queue
        self.running = threading.Event()
        self.intfs = [MulticastServer.get_ip(d) for d in devs]
        self.sock = MulticastServer.init_mcast(self.intfs)

    def run(self):
        """Waits in a loop for incoming packet then puts them in queue"""

        self.running.set() #set to true
        while self.running.is_set():
            data, addr = self.sock.recvfrom(4096)
            logging.debug("MulticastServer: sender %s %s" % (addr, data))
            self.queue.put((data, UDPSender(self.sock, self.intfs, addr)))

    def stop(self):
        """Set run to false, and send an empty message"""

        self.running.clear() 
        msender = UDPSender(self.sock)
        msender.send("", (LOOP_ADDR, PORT))

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
            logging.exception(ex)

    def process_request(self, request):
        """Extract json from request and queues it for processing"""

        logging.debug("HTTPHandler: %s " % request)
        data = request['json'][0]
        queue = Queue.Queue(1)
        sender = HTTPSender(queue, self.client_address)
        self.server.queue.put((data, sender), timeout=2)
        # waits for response from workerthread for only 2 seconds
        err, data = queue.get(timeout=2)

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
        """Sends a file"""

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

    def __init__(self, queue, addr=LOOP_ADDR, port=8080):
        threading.Thread.__init__(self)
        self.port = port
        self.http = BaseHTTPServer.HTTPServer((addr, port), HTTPHandler)
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

    def __init__(self, queue, name, router):
        threading.Thread.__init__(self)
        self.queue = queue
        self.name = name
        self.router = router

    def run(self):
        # SQL database has to be created in same thread
        self.litstore = LitterStore(self.name)
        while True:
            data, sender = self.queue.get()
            if sender == None and data == None:
                # we close DB then break out of loop to stop thread
                self.litstore.close()
                break

            try:
                logging.debug("REQ: %s : %s" % (sender, data))

                if not isinstance(data, dict):
                    data = unicode(data, "utf-8")
                    request = json.loads(data)
                else:
                    request = data

                # save method locally before sending it litterstore
                # just in case it gets modified
                response = None
                if self.router.should_process(request, sender):
                    response = self.litstore.process(request)
                    logging.debug("REP: %s : %s" % (sender, response))
                    self.router.send(response, sender)

                if isinstance(sender, HTTPSender):
                    data = json.dumps(response, ensure_ascii=False)
                    sender.send(data.encode("utf-8"))

            except Exception as ex:
                if isinstance(sender, HTTPSender):
                    sender.send_error(ex)
                logging.exception(ex)

    def stop(self):
        self.queue.put((None,None))


def usage():
    print "usage: ./litter.py [-i intf] [-n name] [-p port]"


def main():

    devs = []
    name = socket.gethostname()
    port = "8080"
    debug_input = False

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

    queue = Queue.Queue(100)

    mserver = MulticastServer(queue, devs)
    mserver.start()

    router = LitterRouter(mserver.sock, mserver.intfs, name)

    wthread = WorkerThread(queue, name, router)
    wthread.start()

    httpd = HTTPThread(queue, port=int(port))
    httpd.start()

    pull_data = json.dumps({'m':'gen_pull'})
    gap_data = json.dumps({'m':'gen_gap'})

    sender = Sender()
    sender.dest = (MCAST_ADDR,PORT)

    try:
        while True:
            if debug_input == False:
                queue.put((pull_data, sender))
                queue.put((gap_data, sender))
                time.sleep(60)
            elif debug_input == True:
                user_input = raw_input()
                try:
                    data = eval(user_input)
                    queue.put((data, sender))
                except Exception as ex:
                    logging.exception(ex)
    except:
        #Control-C will put us here, let's stop the other threads:
        httpd.stop()
        mserver.stop()
        wthread.stop()

if __name__ == '__main__':
    main()

