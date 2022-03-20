from hashlib import sha1
from collections import namedtuple

from decoder import *

TorrentFileContainer = namedtuple('TorrentFileContainer', ['name', 'length'])


class TorrentContent:
    def __init__(self, file_title):
        self.file_title = file_title
        self.file_list = []

        with open(self.file_title, 'rb') as file:
            meta_data = file.read()
            self.meta_data = Decoder(meta_data).decode()
            self.torrent_info = Encoder(self.meta_data[b'info']).encode("utf-8")
            self.torrent_info_hash = sha1(self.torrent_info).digest()
            # self.get_files_list()

    def PrintTorrentContent(self):
          print(self.meta_data)
          return None

    def get_files_list(self):
        if self.multi_file:
            raise RuntimeError('Multi-file torrents is not supported!')
        self.file_list.append(
            TorrentFileContainer(
                self.meta_data[b'info'][b'name'].decode('utf-8'),
                self.meta_data[b'info'][b'length']))

    @property
    def declare(self):
        return self.meta_data[b'announce'].decode('utf-8')

    @property
    def multi_file(self):
        return b'files' in self.meta_data[b'info']

    @property
    def chunk_length(self):
        return self.meta_data[b'info'][b'piece length']

    @property
    def all_size(self):
        if self.multi_file:
            raise RuntimeError('Multi-file torrents is not supported!')
        return self.file_list[0].length

    @property
    def chunks(self):
        data = self.meta_data[b'info'][b'pieces']
        chunks = []
        offset = 0
        length = len(data)

        while offset < length:
            chunks.append(data[offset:offset + 20])
            offset += 20
        return chunks

    @property
    def export_file(self):
        return self.meta_data[b'info'][b'name'].decode('utf-8')

    def __str__(self):
        return 'File title: {0}\n' \
               'File content length: {1}\n' \
               'Declared URL: {2}\n' \
               'File SHA hash: {3}'.format(self.meta_data[b'info'][b'name'],
                                  self.meta_data[b'info'][b'length'],
                                  self.meta_data[b'announce'],
                                  self.torrent_info_hash)

TorrentReader = TorrentContent('RimWorld.torrent')
TorrentReader.PrintTorrentContent()

# from decoder import *
#
# with open('random.torrent', 'rb') as file:
#      meta_data = file.read()
#      torrent = Decoder(meta_data).decode()
#      print(torrent)