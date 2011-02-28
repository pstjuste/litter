
import socket

def main(port=50000, addr='239.192.1.100'):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 20)
    s.sendto("hello", (addr, port))

    print "sent hello"

if __name__ == '__main__':
    main()
