import logging
import json
import socket
import threading
import socketserver
import re
from .udp import gen_udp_packet

_LOGGER = logging.getLogger(__name__)

DOMAIN = 'xiaomi_gateway_proxy'
MULTICAST_ADDRESS = '224.0.0.50'
MULTICAST_PORT = 9898
SOCKET_BUFSIZE = 4096


async def async_setup(hass, config):
    conf = config.get(DOMAIN)
    proxy = XiaomiGatewayProxy(conf)
    proxy.listen()
    return True


class XiaomiGatewayProxy:
    def __init__(self, config):
        self._threads = []
        self._mcastsocket = None
        self._listening = False
        self._port = config.get('port', 4321)

    def listen(self):
        """Start listening."""

        _LOGGER.info('proxy start: Creating Multicast Socket')
        self._mcastsocket = socket.socket(socket.AF_INET, socket.SOCK_RAW,
                                          socket.IPPROTO_RAW)
        self._mcastsocket.settimeout(5.0)
        self._listening = True
        server = socketserver.ThreadingTCPServer(("0.0.0.0", self._port),
                                                 Handler)
        server._mcastsocket = self._mcastsocket
        thread = threading.Thread(target=server.serve_forever,
                                  name="socketserver")
        self._threads.append(thread)
        thread.daemon = True
        thread.start()

    def stop_listen(self):
        """Stop listening."""
        self._listening = False

        if self._mcastsocket is not None:
            _LOGGER.info('Closing multisocket')
            self._mcastsocket.close()
            self._mcastsocket = None

        for thread in self._threads:
            thread.join()
        _LOGGER.info('proxy stopped')


class Handler(socketserver.BaseRequestHandler):
    def setup(self):
        super().setup()
        self.event = threading.Event()
        _LOGGER.debug("agent[%s] connect".format(self.client_address))

    def handle(self):
        super().handle()
        sk: socket.socket = self.request
        while not self.event.is_set():
            try:
                data = sk.recv(SOCKET_BUFSIZE).decode()
                messages = re.findall(r'\{.+?\}(?=\{|$)', data, re.M | re.I)
                for message in messages:
                    msg = json.loads(message)
                    _LOGGER.debug("received: %s", msg)
                    packet = gen_udp_packet(msg.get('ip'), msg.get('port'),
                                            MULTICAST_ADDRESS, MULTICAST_PORT,
                                            msg.get('data'))
                    self.server._mcastsocket.sendto(
                        packet, (MULTICAST_ADDRESS, MULTICAST_PORT))
            except Exception as e:
                _LOGGER.error("fail to handle data [%s]: %s", data, repr(e))

            # 返回空串时表示 TCP 连接已正常关闭
            if not data:
                _LOGGER.debug("agent[%s] disconnect".format(
                    self.client_address))
                break

    def finish(self):
        super().finish()
        self.event.set()
        self.request.close()