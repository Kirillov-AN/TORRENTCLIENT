from decoder import *
with open('random.torrent', 'rb') as f:
     meta_info = f.read()
     torrent = Decoder(meta_info).decode()
     print(torrent)
