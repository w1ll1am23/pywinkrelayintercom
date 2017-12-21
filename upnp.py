import threading
import socket
import logging
import select
import uuid
from datetime import datetime

_LOGGER = logging.getLogger(__name__)


class UPNPResponderThread(threading.Thread):
    """Handle responding to UPNP/SSDP discovery requests."""

    _interrupted = False

    def __init__(self, host_ip_addr, advertise_port):
        """Initialize the class."""
        threading.Thread.__init__(self)

        self.host_ip_addr = host_ip_addr

        # Note that the double newline at the end of
        # this string is required per the SSDP spec
        resp_template = """HTTP/1.1 200 OK
ST: urn:wink-com:device:relay:2
USN: uuid:{0}::urn:wink-com:device:relay:2
LOCATION: https://{1}:{2}
CACHE-CONTROL: max-age=1800
DATE: {3}
SERVER: node.js/0.10.38 UpnP/1.1 node-ssdp/2.6.5
EXT:
"""

        self.upnp_response = resp_template.format(
            uuid.uuid4(),
            host_ip_addr, advertise_port,
            datetime.utcnow().strftime("%a, %d %b %Y %I:%M GMT")).replace("\n", "\r\n")\
            .encode('utf-8')

    def run(self):
        """Run the server."""
        # Listen for UDP port 1900 packets sent to SSDP multicast address
        ssdp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        ssdp_socket.setblocking(False)

        # Required for receiving multicast
        ssdp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        ssdp_socket.setsockopt(
            socket.SOL_IP,
            socket.IP_MULTICAST_IF,
            socket.inet_aton(self.host_ip_addr))

        ssdp_socket.setsockopt(
            socket.SOL_IP,
            socket.IP_ADD_MEMBERSHIP,
            socket.inet_aton("239.255.255.250") +
            socket.inet_aton(self.host_ip_addr))

        # if self.upnp_bind_multicast:
        #     ssdp_socket.bind(("", 1900))
        # else:
        ssdp_socket.bind((self.host_ip_addr, 1900))

        while True:
            if self._interrupted:
                clean_socket_close(ssdp_socket)
                return

            try:
                read, _, _ = select.select(
                    [ssdp_socket], [],
                    [ssdp_socket], 2)

                if ssdp_socket in read:
                    data, addr = ssdp_socket.recvfrom(1024)
                else:
                    # most likely the timeout, so check for interrupt
                    continue
            except socket.error as ex:
                if self._interrupted:
                    clean_socket_close(ssdp_socket)
                    return

                _LOGGER.error("UPNP Responder socket exception occurred: %s",
                              ex.__str__)
                # without the following continue, a second exception occurs
                # because the data object has not been initialized
                continue

            if "M-SEARCH" in data.decode('utf-8', errors='ignore'):
                resp_socket = socket.socket(
                    socket.AF_INET, socket.SOCK_DGRAM)

                resp_socket.sendto(self.upnp_response, addr)
                resp_socket.close()

    def stop(self):
        """Stop the server."""
        # Request for server
        self._interrupted = True
        self.join()


def clean_socket_close(sock):
    """Close a socket connection and logs its closure."""
    _LOGGER.info("UPNP responder shutting down.")

    sock.close()