import socket
import time
import tempfile
import logging
import ipaddress
import threading
import select
import uuid
from datetime import datetime

from pydub import AudioSegment, exceptions

UDP_PORT = 10444
MESSAGE_START = "\x7f"
MESSAGE_END = b'\x80'
NULL_PACKET = "\x00" * 320

_LOGGER = logging.getLogger(__name__)


class WinkRelayIntercomBroadcaster:
    """
    Audio broadcaster for Wink Relay.
    """

    def __init__(self, host_addr, net_mask="255.255.255.0", convert=False, audio_boost=None):
        """

        :param host_addr: The host address of the system running this code.
        :param net_mask: The net_mask of the network. Defaults to the most common 255.255.255.0.
        :param convert: Should the audio files provided be converted?
        :param audio_boost: Should the audio files provided have their audio increased? If so by how much.
        """
        self.host_addr = host_addr
        try:
            _net = ipaddress.IPv4Network(host_addr + "/" + net_mask, False)
            self.bcast_addr = str(_net.broadcast_address)
        except ipaddress.NetmaskValueError:
            _LOGGER.error("An invalid net mask was provided. Setting default.")
            net_mask = "255.255.255.0"
            _net = ipaddress.IPv4Network(host_addr + "/" + net_mask, False)
            self.bcast_addr = str(_net.broadcast_address)
        self.net_mask = net_mask
        self.convert = convert
        self.audio_boost = audio_boost
        self.socket = socket.socket(socket.AF_INET,
                                    socket.SOCK_DGRAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self.ssdpResponder = UPNPResponderThread(host_addr, "8888")

    def activate_relay_intercom(self):
        """
        Start the SSDP responder to activate the Relay's intercom.
        
        For users with only one Relay the intercom function isn't enabled unless
        another Relay is detected on the same network. This will fake another
        Relay. This only needs done once. (Maybe after a software update as well?) 
        """
        self.ssdpResponder.start()

    def set_boost(self, audio_boost):
        """
        Sets the audio boost to apply to a provided file.
        
        :param audio_boost: The number of dB to increase volume by 
        """
        self.audio_boost = audio_boost

    def send_audio(self, filename=None, data=None):
        """
        Play the provided file.

        :param filename: Full path to the file that should be played.
        :param data: Raw data from an Audio file.
        """
        if filename is None and data is None:
            _LOGGER.error("No data provided.")
            return

        ffmpeg_params = []
        if self.convert:
            ffmpeg_params.append("-ac")
            ffmpeg_params.append("1")
            ffmpeg_params.append("-ar")
            ffmpeg_params.append("16000")
        if self.audio_boost:
            ffmpeg_params.append("-af")
            ffmpeg_params.append("volume=" + str(self.audio_boost) + "dB")

        if data:
            _temp_input_audio_file = tempfile.NamedTemporaryFile()
            _temp_input_audio_file.write(data)
        else:
            try:
                _temp_input_audio_file = open(filename, "rb")
                _temp_data = _temp_input_audio_file.read()
                if len(_temp_data) == 0:
                    _LOGGER.error("Empty file provided.")
                    return
                _temp_input_audio_file.seek(0)
            except ValueError:
                _LOGGER.error("Invalid file name. Are you trying to send in raw data in the filename field?")
                return
        _temp_output_audio_file = tempfile.NamedTemporaryFile()

        if self.convert:
            try:
                _sound = AudioSegment.from_file(_temp_input_audio_file.name)
            except (exceptions.CouldntDecodeError, KeyError):
                _LOGGER.error("Failed to decode file. Trying to convert a raw PCM file?")
                return
            _sound.export(_temp_output_audio_file.name,
                          format="s16le",
                          codec="pcm_s16le",
                          parameters=ffmpeg_params)
        elif self.audio_boost:
            _sound = AudioSegment.from_file(_temp_input_audio_file.name,
                                            format="raw",
                                            sample_width=2,
                                            frame_rate=16000,
                                            channels=1)
            _sound.export(_temp_output_audio_file.name,
                          format="s16le",
                          codec="pcm_s16le",
                          parameters=ffmpeg_params)
        else:
            _temp_output_audio_file = _temp_input_audio_file

        # This wakes up the Relay
        self.socket.sendto(bytes(MESSAGE_START, "utf-8"), (self.bcast_addr, UDP_PORT))
        # Send in some null data packets to prime the stream
        for x in range(0, 15):
            self.socket.sendto(bytes(NULL_PACKET, "utf-8"), (self.bcast_addr, UDP_PORT))
        time.sleep(.02)

        _packet = _temp_output_audio_file.read(320)
        packet_count = 0
        while _packet:
            packet_length = len(_packet)
            # All packets should have exactly 320 bytes of data
            if packet_length != 320:
                _packet = _packet + bytes("\x00", "utf-8") * (320 - packet_length)
            self.socket.sendto(_packet, (self.bcast_addr, UDP_PORT))
            # Sending the packets too fast causes the audio to get jumbled because... UDP
            # Every 100 packets it sleeps just a little longer to let the relay catch up
            if packet_count%100 == 0:
                time.sleep(.02)
            else:
                time.sleep(.01)
            _packet = _temp_output_audio_file.read(320)
            packet_count = packet_count + 1
        # This prevents the "audio finished playing tone" from cutting off the last part of the users audio
        for x in range(0, 10):
            self.socket.sendto(bytes(NULL_PACKET, "utf-8"), (self.bcast_addr, UDP_PORT))
        # Without this, it seems the Relay can get locked up and stop accepting new UDP audio
        # it appears these let the Relay know we are finished.
        self.socket.sendto(MESSAGE_END, (self.bcast_addr, UDP_PORT))
        time.sleep(.01)
        self.socket.sendto(MESSAGE_END, (self.bcast_addr, UDP_PORT))
        time.sleep(.01)
        self.socket.sendto(MESSAGE_END, (self.bcast_addr, UDP_PORT))


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

        ssdp_socket.bind(("", 1900))

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

            _data = data.decode('utf-8', errors='ignore')
            if "M-SEARCH" in _data and "ST: urn:wink-com:device:relay:2" in _data:
                resp_socket = socket.socket(
                    socket.AF_INET, socket.SOCK_DGRAM)

                resp_socket.sendto(self.upnp_response, addr)
                resp_socket.close()
                self._stop()

    def _stop(self):
        """Stop the server."""
        # Request for server
        self._interrupted = True
        self.join()


def clean_socket_close(sock):
    """Close a socket connection and logs its closure."""
    _LOGGER.info("UPNP responder shutting down.")

    sock.close()
