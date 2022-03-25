from torrent import *

debugger = Torrent("random.torrent")
debugger.init_files()
debugger.get_trakers()
debugger.generate_peer_id()
print(debugger)

debugger.PrintTorrentInfo()

# От дебаженный torrent.py