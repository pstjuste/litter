#!/usr/bin/env python

import json
import socket
import random
import logging

#logging.basicConfig(level=logging.DEBUG)

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

            if len(self.__intfs) > 0:
                for intf in self.__intfs:
                    self.__sock.setsockopt(socket.SOL_IP, 
                        socket.IP_MULTICAST_IF, socket.inet_aton(intf))
                    self.__sock.sendto(data, dest)
            else:
                # let OS determine default interface
                self.__sock.sendto(data, dest)
                # hack for socialvpn
                try:
                    self.__sock.setsockopt(socket.SOL_IP, 
                        socket.IP_MULTICAST_IF, socket.inet_aton('172.31.0.2'))
                    self.__sock.sendto(data, dest)
                except Exception as ex:
                    logging.exception(ex)

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

    def __should_send(self, headers):

        hto = str(headers.get('hto'))
        hfrom = str(headers.get('hfrom'))
        htype = str(headers.get('htype'))
        hid = headers.get('hid')
        httl = headers.get('httl')

        result = httl >= 0 and hto != self.__uid
        if htype == 'req': result = result and hid not in self.__mid_to_addr
        return result

    def send(self, data, sender=None, addr=None):
        logging.debug('SEND : %s %s' % (sender, data))

        new_sender = sender
        headers = data.get('headers', None)

        if headers != None and self.__should_send(headers):

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


