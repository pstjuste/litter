#!/usr/bin/env python

import unittest
import json
import socket
import random
import logging

logging.basicConfig(level=logging.DEBUG)

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
        self.__sock = sock
        self.__dest = dest
        self.__intfs = intfs

    @property
    def dest(self):
        return self.__dest

    def __str__(self):
        return "UDP Sender: %s" % (self.dest,)

    def send(self, data, dest=None):
        """Sends over UDP socket, if no destination address is found,
           multicast address is used"""

        if dest == None and self.__dest == None and self.__intfs != None:
            dest = (MCAST_ADDR, PORT)

            for intf in self.__intfs:
                self.__sock.setsockopt(socket.SOL_IP, socket.IP_MULTICAST_IF,
                                       socket.inet_aton(intf))
                self.__sock.sendto(data, dest)

        elif dest == None and self.__dest != None:
            dest = self.__dest
            self.__sock.sendto(data, dest)

        elif dest != None:
            self.__sock.sendto(data, dest)

        logging.debug('UDP send : %s : %s' % (dest, data))
        return dest


class HTTPSender(Sender):
    """Implements sender over HTTP protocol"""

    def __init__(self, queue, dest=None):
        self.__queue = queue
        self.__dest = dest

    @property
    def dest(self):
        return self.__dest

    def __str__(self):
        return "HTTP Sender: %s" % (self.dest,)

    def send(self, data, dest=None):
        """Send message by putting in queue for processing"""
        self.__queue.put((None, data))
        logging.debug('HTTP send : %s : %s' % (self.dest, data))

    def send_error(self, excep):
        """Send error by putting in queue"""
        self.__queue.put((excep, None))



class RouterError(Exception):
    """Used to raise litterstore error"""

    def __init__(self, msg):
        self.msg = msg


class LitterRouter:

    def __init__(self, sock, intfs, uid):
        self.__sock = sock
        self.__intfs = intfs
        self.__uid = uid
        self.__addrs = []
        self.__uid_to_addr = {}
        self.__mid_to_addr = {}

    def __get_bcast_sender(self):
        logging.debug('GET BCAST')
        return UDPSender(self.__sock, self.__intfs)

    def __get_rand_sender(self):
        sender = None
        length = len(self.__addrs)

        if length < 1:
            raise RouterError("empty routing table")

        if length >= 1:
            rand_idx = random.randint(0, length-1)
            next_hop = self.__addrs[rand_idx]
            sender = UDPSender(self.__sock, dest=next_hop)

        logging.debug('GET RND: %s' % (sender,))
        return sender

    def __get_sender(self, uid=None, mid=None):
        sender = None

        if mid != None and mid in self.__mid_to_addr:
            addr = self.__mid_to_addr[mid]
            sender = UDPSender(self.__sock, dest=addr)
            logging.debug('MID %s' % (sender,))
        elif uid != None and uid in self.__uid_to_addr:
            addr = self.__uid_to_addr[uid]
            sender = UDPSender(self.__sock, dest=addr)
            logging.debug('UID %s' % (sender,))
        else:
            raise RouterError("uid or mid not found")

        return sender

    def __add_route(self, headers, addr):
        logging.debug('ADD ROUTE : %s : %s' % (headers, addr))

        if addr != None and not addr[0].startswith('127'):
            self.__uid_to_addr[headers['hfrom']] = addr

            if headers['htype'] == 'req': 
                self.__mid_to_addr[headers['hid']] = addr

            if addr not in self.__addrs: 
                self.__addrs.append(addr)

            return True

        else:
            return False

    def __should_send(self, hto, hfrom, hid, htype, httl):
        result = httl >= 0 and hto != self.__uid
        if htype == 'req': result = result and hid not in self.__mid_to_addr
        return result

    def send(self, data, sender=None, addr=None):
        logging.debug('SEND : %s %s' % (sender, data))

        new_sender = sender
        headers = data.get('headers', None)

        if headers != None and self.__should_send(**headers):

            if headers['hto'] == 'any' and headers['htype'] == 'req':
                new_sender = self.__get_rand_sender()
            elif headers['hto'] == 'all' and headers['htype'] == 'req':
                new_sender = self.__get_bcast_sender()
            else:
                new_sender = self.__get_sender(uid = headers['hto'], 
                    mid = headers['hid'])

            # it's important to decrement ttl
            headers['httl'] -= 1

            if isinstance(new_sender, Sender) and headers['httl'] >= 0:
                msg = json.dumps(data, ensure_ascii=False).encode("utf-8")
                new_sender.send(msg)

        # always update route even if we dont foward packet
        if isinstance(sender, Sender) and headers != None:
            self.__add_route(headers, sender.dest)

        return new_sender

    def should_process(self, data, sender=None):
        logging.debug('SPROCESS : %s %s' % (sender, data))

        headers = data.get('headers', None)
        if isinstance(sender, Sender) and sender.dest[0] in self.__intfs: 
            return False
        elif isinstance(headers, dict) and headers['htype'] == 'req' and \
            headers['hid'] in self.__mid_to_addr: return False
        elif headers != None:
            try:
                self.send(data, sender)
                #restore ttl since send decrements it
                headers['httl'] += 1
            except RouterError as err:
                logging.exception(err)

        return True


class MockSocket:

    def setsockopt(self, opt, mcastif, intf):
        pass

    def sendto(self, data, dest):
        pass


class UDPSenderTest(unittest.TestCase):

    def test(self):
        sock = MockSocket()

        # case 1
        sender_a = UDPSender(sock)
        self.assertEqual(sender_a.send(''), None)

        # case 2
        dest_a = ('addr1',1234)
        self.assertEqual(sender_a.send('',dest_a), dest_a)

        # case 3
        dest_b = ('addr2', 1234)
        sender_b = UDPSender(sock, dest=dest_a)
        self.assertEqual(sender_b.send(''), dest_a)

        # case 5
        self.assertEqual(sender_b.send('', dest_b), dest_b)

        # case 6
        sender_c = UDPSender(sock, ['127.0.0.1'])
        mcast = (MCAST_ADDR, PORT)
        self.assertEqual(sender_c.send(''), mcast)

        # case 7
        self.assertEqual(sender_c.send('',dest_a), dest_a)


class LitterRouterTest(unittest.TestCase):

    def setUp(self):
        self.sock = MockSocket()
        self.intfs = ['127.0.0.1', '0.0.0.0']
        self.router_a = LitterRouter(self.sock, self.intfs, 'user_a')
        self.router_b = LitterRouter(self.sock, self.intfs, 'user_b')

    def tearDown(self):
        pass

    def test(self):
        result = self.router_a.should_process({})
        self.assertEqual(result, True)

        bcast_addr = (MCAST_ADDR, PORT)
        headers = {}
        headers['hto'] = 'user_b'
        headers['hfrom'] = 'user_a'
        headers['hid'] = 'id1'
        headers['htype'] = 'req'
        headers['httl'] = -1

        data = {}
        data['headers'] = headers

        # case 1
        self.assertEqual(self.router_a.send(data), None)

        # case 2
        headers['httl'] = 1
        headers['hto'] = 'user_a'
        self.assertEqual(self.router_a.send(data), None)

        # case 3
        headers['hto'] = 'any'
        headers['httl'] = 1
        self.assertRaises(RouterError, self.router_a.send, data)

        # case 4a
        headers['httl'] = 1
        sender_a = UDPSender(self.sock, dest="192.168.0.101");
        self.assertRaises(RouterError, self.router_a.send, data)

        # case 4b
        headers['hid'] = 'id3'
        self.assertRaises(RouterError, self.router_a.send, data,
            sender=sender_a)

        # case 5
        headers['hto'] = 'all'
        headers['httl'] = 1
        self.assertEqual(self.router_a.send(data).dest, None)

        # case 6
        headers['httl'] = 1
        headers['hid'] = 'id2'
        self.assertEqual(self.router_a.send(data).dest, None)

        # case 7
        headers['httl'] = 1
        headers['htype'] = 'rep'
        headers['hid'] = 'id1'
        self.assertRaises(RouterError, self.router_a.send, data)

        # case 8
        headers['httl'] = 1
        headers['htype'] = 'rep'
        headers['hid'] = 'id2'
        self.assertRaises(RouterError, self.router_a.send, data)

        #case 9
        headers['httl'] = 1
        headers['htype'] = 'req'
        headers['hto'] = 'any'
        self.assertRaises(RouterError, self.router_b.send, data, sender = sender_a)

        #case 10
        headers['httl'] = 1
        headers['htype'] = 'rep'
        headers['hto'] = 'user_a'
        self.assertRaises(RouterError, self.router_b.send, data)

        #case 11
        headers['httl'] = 1
        headers['htype'] = 'rep'
        self.assertRaises(RouterError, self.router_b.send, data)

        #case 12
        self.assertEqual(self.router_a.should_process({}), True)

        #case 13
        sender_b = UDPSender(self.sock, dest=('127.0.0.1',PORT))
        self.assertEqual(self.router_a.should_process(data, sender_b), False)
        
        #case 14
        headers['htype'] = 'req'
        headers['httl'] = 2
        headers['hto'] = 'all'
        headers['hfrom'] = 'user_a'
        headers['hid'] = 'id14'
        sender_c = UDPSender(self.sock, dest=('172.31.34.21',PORT))
        self.assertEqual(self.router_a.send(data, sender_c).dest, None)
        self.assertEqual(self.router_a.should_process(data, sender_c), False)

        #case 15
        headers['httl'] = 1
        headers['hid'] = 'id15'
        self.assertEqual(self.router_a.should_process(data, sender_c), True)

        #case 16
        sender_d = UDPSender(self.sock, dest=('182.231.11.2',PORT))
        self.assertEqual(self.router_a.send({},sender=sender_c), sender_c)
        

if __name__ == '__main__':
    unittest.main()

