import socket
import struct
from random import randint
 
 
def checksum(data):
    s = 0
    n = len(data) % 2
    for i in range(0, len(data) - n, 2):
        s += data[i] + (data[i + 1] << 8)
    if n:
        s += data[i + 1]
    while (s >> 16):
        s = (s & 0xFFFF) + (s >> 16)
    s = ~s & 0xffff
    return s
 
 
class IP(object):
    def __init__(self, source, destination, payload='', proto=socket.IPPROTO_TCP):
        self.version = 4
        self.ihl = 5  # Internet Header Length
        self.tos = 0  # Type of Service
        self.tl = 20 + len(payload)
        self.id = 0  # random.randint(0, 65535)
        self.flags = 0  # Don't fragment
        self.offset = 0
        self.ttl = 255
        self.protocol = proto
        self.checksum = 2  # will be filled by kernel
        self.source = socket.inet_aton(source)
        self.destination = socket.inet_aton(destination)
 
    def pack(self):
        ver_ihl = (self.version << 4) + self.ihl
        flags_offset = (self.flags << 13) + self.offset
        ip_header = struct.pack("!BBHHHBBH4s4s",
                                ver_ihl,
                                self.tos,
                                self.tl,
                                self.id,
                                flags_offset,
                                self.ttl,
                                self.protocol,
                                self.checksum,
                                self.source,
                                self.destination)
        self.checksum = checksum(ip_header)
        ip_header = struct.pack("!BBHHHBBH4s4s",
                                ver_ihl,
                                self.tos,
                                self.tl,
                                self.id,
                                flags_offset,
                                self.ttl,
                                self.protocol,
                                socket.htons(self.checksum),
                                self.source,
                                self.destination)
        return ip_header
 
 
class UDP(object):
    def __init__(self, src_port, dst_port, payload=''):
        self.src_port = src_port
        self.dst_port = dst_port
        self.payload = payload
        self.checksum = 0
        self.length = 8  # UDP Header length

    def pack(self, src_ip, dst_ip, proto=socket.IPPROTO_UDP):
        length = self.length + len(self.payload)
        pseudo_header = struct.pack('!4s4sBBH',
                                    socket.inet_aton(src_ip), socket.inet_aton(dst_ip), 0,
                                    proto, length)
        self.checksum = checksum(pseudo_header)
        packet = struct.pack('!HHHH',
                             self.src_port, self.dst_port, length, 0)
        return packet

def gen_udp_packet(src_ip, src_port, dst_ip, dst_port, payload):
    udp = UDP(src_port if src_port else randint(1, 65535), dst_port, payload).pack(src_ip, dst_ip)
    ip = IP(src_ip, dst_ip, udp, proto=socket.IPPROTO_UDP).pack()
    return ip + udp + payload.encode()
