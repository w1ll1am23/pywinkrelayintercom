import socket
import time
import tempfile

from pydub import AudioSegment

UDP_PORT = 10444
MESSAGE_START = "\x7f"
MESSAGE_END = b'\x80'
START_PACKET = "\x00" * 320


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

    def send_audio(self, filename=None, data=None):
        """
        Play the provided file.
        
        :param filename: Full path to the file that should be played.
        :param data: Raw data from an Audio file.
        :return: Nothing
        """
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
            _temp_input_audio_file = open(filename, "rb")
        _temp_output_audio_file = tempfile.NamedTemporaryFile()
            
        if self.audio_boost or self.convert:
            _sound = AudioSegment.from_file(_temp_input_audio_file)
            _sound.export(_temp_output_audio_file.name,
                          format="s16le",
                          codec="pcm_s16le",
                          parameters=ffmpeg_params)
        else:
            _temp_output_audio_file = _temp_input_audio_file
        
        # This wakes up the Wink Relay
        self.socket.sendto(bytes(MESSAGE_START, "utf-8"), (self.bcast_addr, UDP_PORT))
        # Send in some null data packets to prime the stream
        for x in range(0, 10):
            self.socket.sendto(bytes(START_PACKET, "utf-8"), (self.bcast_addr, UDP_PORT))
            
        _packet = _temp_output_audio_file.read(320)
        while _packet:
            packet_length = len(_packet)
            # All packets should have exactly 320 bytes of data
            if packet_length != 320:
                _packet = _packet + bytes("\x00", "utf-8") * (320 - packet_length)
            self.socket.sendto(_packet, (self.bcast_addr, UDP_PORT))
            time.sleep(.012)
            _packet = _temp_output_audio_file.read(320)
        # Not sure if this is needed, but the Relay sends these every time.
        self.socket.sendto(MESSAGE_END, (self.bcast_addr, UDP_PORT))
        time.sleep(.01)
        self.socket.sendto(MESSAGE_END, (self.bcast_addr, UDP_PORT))
        time.sleep(.01)
        self.socket.sendto(MESSAGE_END, (self.bcast_addr, UDP_PORT))
