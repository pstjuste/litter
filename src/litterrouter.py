#!/usr/bin/env python

import unittest
import json
import socket
import random

MCAST_ADDR = "239.192.1.100"
PORT = 50000
LOOP_ADDR = "127.0.0.1"
IP_ANY = "0.0.0.0"

class Sender:
    """Base class sender interface"""

    dest = 'not assigned'

    def send(self, data, dest=None):
        """Not implemented"""
        raise Exception("Base class, no implementation")


class UDPSender(Sender):
    """Implements sender over UDP socket"""

    def __init__(self, sock, intfs=None, dest=None):
        self.sock = sock
        self.dest = dest
        self.intfs = intfs

    def send(self, data, dest=None):
        """Simply sends over UDP socket"""

        if not isinstance(self.sock, socket.socket):
            return None

        if dest == None and self.dest == None and self.intfs != None:
            dest = (MCAST_ADDR, PORT)

            for intf in self.intfs:
                self.sock.setsockopt(socket.SOL_IP, socket.IP_MULTICAST_IF,
                                     socket.inet_aton(intf))
                self.sock.sendto(data, dest)

        elif dest == None:
            dest = self.dest

        self.sock.sendto(data, dest)
        print 'UDP send : %s : %s' % (dest, data)


class HTTPSender(Sender):
    """Implements sender over HTTP protocol"""

    def __init__(self, queue, dest=None):
        self.queue = queue
        self.dest = dest

    def send(self, data, dest=None):
        """Send message by putting in queue for processing"""
        self.queue.put((None, data))
        print 'HTTP send : %s : %s' % (self.dest, data)

    def send_error(self, excep):
        """Send error by putting in queue"""
        self.queue.put((excep, None))


class LitterRouter:

    def __init__(self, sock, intfs, uid):
        self.sock = sock
        self.intfs = intfs
        self.uid = uid
        self.addrs = []
        self.uid_to_addr = {}
        self.mid_to_addr = {}


    def __get_bcast_sender(self):
        return UDPSender(self.sock, self.intfs)


    def __get_rand_sender(self):
        sender = None
        length = len(self.addrs)

        if length != 0:
            rand_idx = random.randint(1, length) - 1
            next_hop = self.addrs[rand_idx]
            sender = UDPSender(self.sock, dest=next_hop)

        return sender


    def __get_sender(self, uid=None, mid=None):

        sender = None

        if uid != None and uid in self.uid_to_addr:
            addr = self.uid_to_addr[uid]
            sender = UDPSender(self.sock, dest=addr)
        elif mid != None and mid in self.mid_to_addr:
            addr = self.mid_to_addr[mid]
            sender = UDPSender(self.sock, dest=addr)
        else:
            sender = self.__get_rand_sender()

        return sender


    def __add_route(self, headers, addr):

        print 'ADD ROUTE : %s : %s' % (headers, addr)

        if addr != None and not addr[0].startswith('127'):
            self.uid_to_addr[headers['hfrom']] = addr

            if headers['htype'] == 'req': 
                self.mid_to_addr[headers['hid']] = addr

            if addr not in self.addrs: 
                self.addrs.append(addr)

            return True

        return False


    def __should_send(self, hto, hfrom, hid, htype, httl):
        result = httl >= 1 and hto != self.uid
        if htype == 'req': result = result and hid not in self.mid_to_addr
        return result


    def send(self, data, sender=None, addr=None):

        print 'SEND : %s' % (data,)

        headers = data.get('headers', None)

        if headers != None and self.__should_send(**headers):
            self.__add_route(headers, addr)

            # TODO - cleanup this logic
            if headers['hto'] == 'any' and headers['htype'] == 'req':
                sender = self.__get_rand_sender()
            elif headers['hto'] == 'all' and headers['htype'] == 'req':
                sender = self.__get_bcast_sender()
            elif headers['htype'] == 'req':
                sender = self.__get_sender(headers['hto'])
            elif headers['htype'] == 'rep' and headers['hto'] != 'any':
                sender = self.__get_sender(headers['hid'])

            # it's important to decrement ttl
            headers['httl'] -= 1

            if isinstance(sender, Sender):
                msg = json.dumps(data, ensure_ascii=False).encode("utf-8")
                sender.send(msg)
                print 'SENT : %s : %s' % (data, sender.dest)
                return True

        return False


    def should_process(self, data, sender=None):

        headers = data.get('headers', None)
        if headers == None: return True

        if isinstance(sender, Sender) and sender.dest[0] in self.intfs: 
            return False
        elif self.__should_send(**headers):
            self.send(data, sender, sender.dest)
            return True

        return False


class LitterRouterTest(unittest.TestCase):

    def setUp(self):
        sock = 1
        intfs = ['intf1', 'intf2']
        self.router = LitterRouter(sock, intfs, 'uid1')

    def tearDown(self):
        pass

    def test(self):
        result = self.router.should_process({})
        self.assertEqual(result, True)

        headers = {}
        headers['hto'] = 'uid2'
        headers['hfrom'] = 'uid1'
        headers['hid'] = 'id1'
        headers['htype'] = 'req'
        headers['httl'] = 2

        data = {}
        data['headers'] = headers

        sender = Sender()
        sender.dest = ('intf1','port')

        result = self.router.should_process(data, sender)
        self.assertEqual(result, False)

        sender.dest = ('ip1', 'port1')
        result = self.router.should_process(data, sender)
        self.assertEqual(result, True)

        result = self.router.send({})
        self.assertEqual(result, False)

        headers['httl'] = 0
        result = self.router.send(data, None)
        self.assertEqual(result, False)

        headers['httl'] = 1
        headers['hid'] = 'id2'
        result = self.router.send(data, None)
        self.assertEqual(result, True)


if __name__ == '__main__':
    unittest.main()

