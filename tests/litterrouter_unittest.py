#!/usr/bin/env python

import unittest
from litterrouter import *

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

