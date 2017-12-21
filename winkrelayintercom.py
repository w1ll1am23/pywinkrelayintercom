import socket
import time
import tempfile
import logging

from pydub import AudioSegment, exceptions
from upnp import UPNPResponderThread

UDP_PORT = 10444
MESSAGE_START = "\x7f"
MESSAGE_END = b'\x80'
NULL_PACKET = "\x00" * 320

_LOGGER = logging.getLogger(__name__)


class WinkRelayIntercomBroadcaster:
    """
    Audio broadcaster for Wink Relay.
    """

    def __init__(self, bcast_addr, convert=False, audio_boost=None):
        """

        :param bcast_addr: The broadcast address for your network.
        :param convert: Should the audio files provided be converted?
        :param audio_boost: Should the audio files provided have their audio increased? If so by how much.
        """
        self.bcast_addr = bcast_addr
        self.convert = convert
        self.audio_boost = audio_boost
        self.socket = socket.socket(socket.AF_INET,
                                    socket.SOCK_DGRAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self.ssdpResponder = UPNPResponderThread("192.168.5.5", "8888")
        self.ssdpResponder.start()

    def stop(self):
        """Stop the ssdpResponder."""
        self.ssdpResponder.stop()

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
            except ValueError:
                _LOGGER.error("Invalid file name. Are you trying to send in raw data in the filename field?")
            _temp_data = _temp_input_audio_file.read()
            if len(_temp_data) == 0:
                _LOGGER.error("Empty file provided.")
                return
            _temp_input_audio_file.seek(0)
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
        for x in range(0, 10):
            self.socket.sendto(bytes(NULL_PACKET, "utf-8"), (self.bcast_addr, UDP_PORT))

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
