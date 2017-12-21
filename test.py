import time

from winkrelayintercom import WinkRelayIntercomBroadcaster

# Takes an MP3, converts and boosts the audio sends to broadcaster as raw data
broadcaster = WinkRelayIntercomBroadcaster("192.168.1.255", convert=True, audio_boost=15)
with open("test.mp3", "rb") as f:
   data = f.read()
   broadcaster.send_audio(data)

# # Takes a PCM raw audio file and sends it as a file path. No audio boost.
broadcaster = WinkRelayIntercomBroadcaster("192.168.1.255", convert=False, audio_boost=10)
# Wait for the relay to send out an SSDP request (Not sure how long that takes)
time.sleep(120)
broadcaster.send_audio("test.pcm")
# Kill the SSDP responder
broadcaster.stop()
