
import socket
import time
import sys
import json
import random
import Queue
import threading
import SocketServer
from litterstore import LitterStore

MCAST_ADDR = "239.192.1.100"
MCAST_PORT = 50000
MYUID = 'thisismyuid'

# Producer thread
class MulticastServer(threading.Thread):

    def __init__(self, queue):
        threading.Thread.__init__(self)
        self.queue = queue
        self.sock = MulticastServer.init_mcast()

    # code from http://wiki.python.org/moin/UdpCommunication
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
            socket.inet_aton('192.168.0.101'))
        s.setsockopt(socket.SOL_IP, socket.IP_ADD_MEMBERSHIP, \
            socket.inet_aton(addr) + socket.inet_aton('192.168.0.101'))

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

class UDPSender:

    def __init__(self, sock, dest):
        self.sock = sock
        self.dest = dest

    def send(self, data):
        self.sock.sendto(data, self.dest)


# Consumer thread
class WorkerThread(threading.Thread):

    def __init__(self, queue):
        threading.Thread.__init__(self)
        self.queue = queue
        self.uid = MYUID

    def run(self):
        # SQL database has to be created in same thread
        self.litstore = LitterStore(self.uid)
        while True:
            data, sender = self.queue.get()
            request = json.loads(data)
            print 'request from %s >> %s' % (sender.dest, request)
            response = self.litstore.process(**request)

            rthread = ResponseThread(response, sender, self.uid)
            rthread.start()


class ResponseThread(threading.Thread):

    def __init__(self, response, sender, uid):
        threading.Thread.__init__(self)
        self.response = response
        self.sender = sender

    def run(self):
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
    request = { 'method' : 'discover', 'kwargs' : kwargs }
    return request

def main():

    queue = Queue.Queue()

    mserver = MulticastServer(queue)
    mserver.start()

    userver = UnicastServer(queue)
    userver.start()

    wthread = WorkerThread(queue)
    wthread.start()

    # heartbeat loop set for every 5 min
    while True:
        userver.sock.sendto(json.dumps(discover_msg()), (MCAST_ADDR, MCAST_PORT))
        time.sleep(300)

    mserver.join()
    userver.join()
    wthread.join()

if __name__ == '__main__':
    main()

