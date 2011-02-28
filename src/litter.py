
import socket
import Queue
import threading

# Producer thread
class MulticastServer(threading.Thread):

    def __init__(self, queue):
        threading.Thread.__init__(self)
        self.queue = queue
        self.sock = self.init_mcast()

    # code from http://wiki.python.org/moin/UdpCommunication
    def init_mcast(self, port=50000, addr="239.192.1.100"):

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
        print intf

        s.setsockopt(socket.SOL_IP, socket.IP_MULTICAST_IF, \
            socket.inet_aton('10.128.80.91'))
        s.setsockopt(socket.SOL_IP, socket.IP_ADD_MEMBERSHIP, \
            socket.inet_aton(addr) + socket.inet_aton('10.128.80.91'))

        return s

    def run(self):
        while True:
            data, sender = self.sock.recvfrom(1024)
            print data, sender
            self.queue.put((data, sender, s))


class TCPHandler(SocketServer.StreamRequestHandler):

    def __init__(self, queue):
        SocketServer.StreamRequestHandler.__init__(self)
        self.queue = queue

    def handle(self):
        data = self.rfile.read()
        self.queue.put((data, self.client_address[0], self))

# Producer thread
class TCPServer(threading.Thread):

    def __init__(self, queue):
        threading.Thread.__init__(self)
        self.server = TCPHandler(queue)

    def run(self):
        self.server.server_forever()

# Consumer thread
class WorkerThread(threading.Thread):

    def __init__(self, queue):
        threading.Thread.__init__(self)
        self.queue = queue
        self.litter = Litter()

    def run(self):
        while True:
            data, sender, con = self.queue.get()
            print "wthread received %s from %s" % (data, sender)

            req = json.loads(data)
            method = request['m']

            if(method == 'discover'):
                resp = {'m' : 'discover-res', 'uid' : litter.uid}
                con.sendto(json.dumps(resp), sender)

            elif(method == 'discover-res'):
                litter.update_follow(req['uid'])

            elif(method == 'post'):
                litter.post(req['mid'], req['uid'], req['time'], req['msg'])
                resp = {'m' : 'post-ack', req['mid'], litter.uid}
                con.sendto(json.dumps(resp), sender)

            elif(method = 'post-ack'):
                litter.post_ack(req['mid'], req['uid'])

            elif(method = 'get'):
                posts = litter.get(req['fids'], req['since'])
                resp = {'m' : 'get-res', 'posts' : posts}
                con.wfile.write(json.dumps(resp))

            elif(method = 'get-res'):
                litter.add_posts(req['posts'])

            self.queue.task_done()


#TODO - needs implementation
class Litter():

    def __init__(self):
        # TODO - place holder, use big number
        self.uid = socket.gethostname()
        self.fids = []

    def update_follow(self, uid):
        return

    def post(self, uid, time, msg):
        return

    def get(self, fids, since):
        return []

    def add_posts(posts):
        return

def main(port=50000, addr='239.192.1.100'):

    queue = Queue.Queue()

    mserver = MulticastServer(queue)
    mserver.start()

    wthread = WorkerThread(queue)
    wthread.start()

    tserver = TCPServer(queue)
    tserver.start()

    #TODO - this will be the main IO thread

    queue.join()
    mserver.join()
    wthread.join()


if __name__ == '__main__':
    main()

