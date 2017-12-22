from winkrelayintercom import WinkRelayIntercomBroadcaster

# Takes a PCM raw audio file and sends it as a file path. No audio boost.
broadcaster = WinkRelayIntercomBroadcaster("192.168.1.5", "255.255.255.0", convert=False, audio_boost=10)

# If you only have one Relay on your network you must run the following at least once
# It could take up to a minute for your intercom to start working.
broadcaster.activate_relay_intercom()

# Send audio by file name
broadcaster.send_audio("test.pcm")

# Or send the raw file data

# Takes an MP3, converts and boosts the audio sends to broadcaster as raw data
broadcaster = WinkRelayIntercomBroadcaster("192.168.1.5", "255.255.255.0", convert=True, audio_boost=15)
with open("test.mp3", "rb") as f:
    data = f.read()
    broadcaster.send_audio(data)
