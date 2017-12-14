from winkrelayintercom import WinkRelayIntercomBroadcaster
broadcaster = WinkRelayIntercomBroadcaster("192.168.1.255", convert=True, audio_boost=10)
broadcaster.send_audio("brian.mp3")
