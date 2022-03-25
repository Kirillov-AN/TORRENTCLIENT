from hashlib import sha1
from collections import namedtuple
from bcoding import bencode, bdecode # для работы с кодировкой бенкод
from decoder import * # parser нам больше не нужен
import math
import time
import os

TorrentFile = namedtuple('TorrentFile', ['name', 'length'])


class Torrent:

    """
    init это parser
    """
    def __init__(self, filename):
        self.filename = filename
        self.torrent_file = {}  # словаоь для получения контента из торрента
        self.total_length = 0  # для получения длины из списка file["length"]
        self.piece_length = 0  # длина куска как в нашем проекте
        self.pieces = 0  # получение какого-то числа из словаря torrent_file['info']['pieces']
        self.info_hash = ''  # хэш файла torrent_file['info']
        self.peer_id = ''  # идентификатор пира
        self.announce_list = ''  # список трекеров
        self.file_names = []  # имена файлов в торренте
        self.number_of_pieces = 0  # количество кусков
        self.multi_file = False

        with open(filename, 'rb') as file:
            contents = bdecode(file) # декодируем контент из торрента

            self.torrent_file = contents # записываем декодированный контент
            self.piece_length = self.torrent_file['info']['piece length'] # узнаем длину куска
            self.pieces = self.torrent_file['info']['pieces'] # узнаем число кусков видимо это не количество
            raw_info_hash = bencode(self.torrent_file['info']) # получаем сырой hash
            self.info_hash = sha1(raw_info_hash).digest() # получаем sha1 hash
            self.peer_id = self.generate_peer_id() # получаем идентификатор пира
            self.announce_list = self.get_trakers() # получаем список трекеров
            self.init_files() # разбираемся с количеством файлов
            self.number_of_pieces = math.ceil(self.total_length / self.piece_length)

    def init_files(self):
        root = self.torrent_file['info']['name'] # видимо корневая папка

        if 'files' in self.torrent_file['info']: # пока файлы в словаре
            self.multi_file = True
            if not os.path.exists(root): # если путь существуем
                os.mkdir(root, 0o0766 ) # создаем структуру папок, в которой будут лежать файлы

            for file in self.torrent_file['info']['files']: # идем по списку files
                path_file = os.path.join(root, *file["path"]) # получаем пути для файлов в торренте

                if not os.path.exists(os.path.dirname(path_file)): # если путь не создан
                    os.makedirs(os.path.dirname(path_file)) # создаем папки

                self.file_names.append({"path": path_file , "length": file["length"]}) # заносим в словарь пары путь к файлу и длинна файла
                self.total_length += file["length"] # суммируем размер необходимый для закачки

        else:
            self.multi_file = False
            self.file_names.append({"path": root , "length": self.torrent_file['info']['length']}) #иначе заносим в словарь корневую папку и длину torrent_file
            self.total_length = self.torrent_file['info']['length'] # это код для однофайлового торрента

    def get_trakers(self):
        if 'announce-list' in self.torrent_file: # идем по словарю announce. Получаем список трекеров. Как в нашем проекте
            return self.torrent_file['announce-list'] # возврат списка трекеров
        else:
            return [[self.torrent_file['announce']]] # иначе возврат списка списка трекеров

    def generate_peer_id(self): # генерируем айдишник пира
        seed = str(time.time()) # через функцию time
        return sha1(seed.encode('utf-8')).digest() # возварт id в виде sha1 hash

    def __str__(self):
        if self.multi_file:
            dict_content=""
            for dictionary in self.file_names:
                dictionary_keys = list(dictionary.keys())
                dict_content+="Filename: {0}. Size of file {1}\n".format(dictionary[dictionary_keys[0]],dictionary[dictionary_keys[1]])
            return 'Filename: {0}\n' \
                   'Files lengths: {1}\n' \
                   'Announce URL: {2}\n' \
                   'Hash: {3}\n\n'.format(self.torrent_file['info']['name'],
                                      dict_content,
                                      self.torrent_file['announce'],
                                      self.info_hash)
        else:
            return 'Filename: {0}\n' \
                   'File length: {1}\n' \
                   'Announce URL: {2}\n' \
                   'Hash: {3}\n\n'.format(self.torrent_file['info']['name'],
                                      self.torrent_file['info']['length'],
                                      self.torrent_file['announce'],
                                      self.info_hash)
    def PrintTorrentInfo(self):
        print("Filename {0}\nTorrent file dict {1}\nTotal length {2}\nPiece length {3}\nPieces {4}\nInfo hash {5}\nPeer id {6}\nAnnounce list {7}\nFile names {8}\nNumber of pieces {9}\nIs multi-file {10}\n".format(self.filename,
        self.torrent_file,
        self.total_length,
        self.piece_length,
        self.pieces,
        self.info_hash,
        self.peer_id,
        self.announce_list,
        self.file_names,
        self.number_of_pieces,
        self.multi_file))