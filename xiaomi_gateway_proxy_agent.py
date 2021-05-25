import socket
import platform
import struct
import logging
import time
import threading
import json
import re
import argparse
import os, signal

SOCKET_BUFSIZE = 4096
MULTICAST_PORT = 9898
MULTICAST_ADDRESS = '224.0.0.50'

logging.basicConfig(
    format=
    '%(asctime)s - %(pathname)s[:%(lineno)3d] - %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    level=logging.DEBUG)
_LOGGER = logging.getLogger(os.path.basename(__file__))


def create_mcast_socket(interface, port):
    """Create and bind a socket for communication."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    if interface != 'any':
        if platform.system() != "Windows":
            try:
                sock.bind((MULTICAST_ADDRESS, port))
            except OSError:
                sock.bind((interface, port))
        else:
            sock.bind((interface, port))

        mreq = socket.inet_aton(MULTICAST_ADDRESS) + socket.inet_aton(
            interface)
    else:
        if platform.system() != "Windows":
            try:
                sock.bind((MULTICAST_ADDRESS, port))
            except OSError:
                sock.bind(('', port))
        else:
            sock.bind(('', port))
        mreq = struct.pack("=4sl", socket.inet_aton(MULTICAST_ADDRESS),
                           socket.INADDR_ANY)

    sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
    return sock


class Agent:
    def __init__(self, host, port):
        self._host = host
        self._port = port
        self._threads = []
        self._next_interval = 10
        self.sender = self._connect()
        mcastsocket = create_mcast_socket('any', MULTICAST_PORT)
        mcastsocket.settimeout(5.0)
        self.recevier = mcastsocket
        self._connected = False

    def start(self):
        _LOGGER.info('Start agent')
        self._listening = True
        _LOGGER.info('Creating sender reconnect thread')
        thread = threading.Thread(target=self._reconnect)
        self._threads.append(thread)
        thread.setDaemon(True)
        thread.start()
        _LOGGER.info('Creating reciever thread')
        self._listen_to_msg()

    def stop(self):
        _LOGGER.info('Stopping agent')
        self._listening = False

        if self.recevier is not None:
            _LOGGER.info('Closing UDP Multisocket')
            self.recevier.close()
            self.recevier = None

        if self.sender is not None:
            _LOGGER.info('Closing TCP Socket')
            self.sender.close()
            self.sender = None

        # for thread in self._threads:
        #     thread.join()
        _LOGGER.info('Agent stopped')

    def _listen_to_msg(self):
        while self._listening:
            if self.recevier is None:
                continue
            try:
                data, (ip_add, port) = self.recevier.recvfrom(SOCKET_BUFSIZE)
            except socket.timeout:
                continue
            try:
                messages = re.findall(r'\{.+?\}(?=\{|$)', data.decode(),
                                      re.M | re.I)
                for message in messages:
                    _LOGGER.debug('Received from %s: %s', ip_add, message)
                    msg = {'ip': ip_add, 'port': port, 'data': message}
                    self.send(json.dumps(msg).encode())
            except Exception as e:
                _LOGGER.error('send error: %s'.format(repr(e)))
                continue
        _LOGGER.info('Listener stopped')

    def send(self, message):
        if not self._connected:
            _LOGGER.debug('Skip sending: sender not ready')
            return
        try:
            self.sender.sendall(message)
        except socket.error:
            _LOGGER.error('Fail to send: socket error')
            self._connected = False
        except Exception as e:
            _LOGGER.error('Fail to send: %s', repr(e))
            self._connected = False

    def _reconnect(self):
        while self._listening:
            if not self._connected:
                _LOGGER.debug('(%s)Try reconnect',
                              threading.currentThread().name)
                self.sender = self._connect()
            time.sleep(self._next_interval)

    def _connect(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.connect((self._host, self._port))
            self._connected = True
            self._next_interval = 10
        except Exception as e:
            self._next_interval = self._next_interval if self._next_interval >= 60 else self._next_interval + 10
            _LOGGER.error('Fail to connect: %s, retry after %ss', repr(e),
                          self._next_interval)
        return sock


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', required=True, help="server ip")
    parser.add_argument('--port', required=True, type=int, help="server port")
    parser.add_argument('--verbose',
                        '-v',
                        action='store_true',
                        help='verbose mode',
                        default=False)
    args = parser.parse_args()

    out = os.popen("ps aux | grep {} | awk '!/grep/'".format(
        os.path.basename(__file__))).read()
    for line in out.splitlines():
        pid = int(line.split()[1])
        if pid == os.getpid(): continue
        os.kill(pid, signal.SIGKILL)
        _LOGGER.info('kill present process[%s]' % pid)

    agent = Agent(args.host, args.port)
    try:
        agent.start()
    except KeyboardInterrupt as e:
        agent.stop()