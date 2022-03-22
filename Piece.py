
import asyncio
import logging
import math
import os
import time
from asyncio import Queue
from collections import namedtuple, defaultdict
from hashlib import sha1

from pieces.protocol import PeerConnection, REQUEST_SIZE
from pieces.tracker import Tracker

MAX_PEER_CONNECTIONS = 40



class Block:

    Missing = 0
    Pending = 1
    Retrieved = 2

    def __init__(self, piece: int, offset: int, length: int):
        self.piece = piece
        self.offset = offset #положение блока данных в куске
        self.length = length
        self.status = Block.Missing #Состояния отсутствует,ожидается, готово(судя по переводу восстановлен что не соответсвует контексту)
        self.data = None

class Piece:

    def __init__(self, index: int, blocks: [], hash_value):
        self.index = index
        self.blocks = blocks
        self.hash = hash_value

    def deleteall(self):
   #Метод для удаления всех данных в куске для скачивания повторно
        for block in self.blocks:
            block.status = Block.Missing

    def next_request_block(self):
    #Возвращает следующий блок для скачивания или ничего если нечего закачивать
        missing = [b for b in self.blocks if b.status is Block.Missing]
        if missing:
            missing[0].status = Block.Pending
            return missing[0]
        return None

    def block_received(self, offset: int, data: bytes):
    #Отмечает блок как скачанный если его текущая  позиция в куске равна запланированной
        matches = [b for b in self.blocks if b.offset == offset]
        block = matches[0] if matches else None
        if block:
            block.status = Block.Retrieved
            block.data = data
        else:
            logging.warning('Trying to complete a non-existing block {offset}'
                            .format(offset=offset))

    def is_complete_retrieved(self): #не осталось блоков со статусом не готов
        blocks = [b for b in self.blocks if b.status is not Block.Retrieved]
        return len(blocks) is 0

    def is_hash_matching(self):

        piece_hash = sha1(self.data).digest()
        return self.hash == piece_hash

    @property
    def data(self):
        """
        Соединяет байты  из  списка blocks_data вместе
        return b''.join
     результат    b'\xd1\x81\xd1\x83\xd0\xbf\xd0\xb5\xd1\x80'

        """
        retrieved = sorted(self.blocks, key=lambda b: b.offset)
        blocks_data = [b.data for b in retrieved]
        return b''.join(blocks_data)

# The type used for keeping track of pending request that can be re-issued
PendingRequest = namedtuple('PendingRequest', ['block', 'added'])


class PieceManager:
    """
    Должен находить доступные куски у других пиров и  помечать те куски которые можно отдать пирам
    """
    def __init__(self, torrent):
        self.torrent = torrent # обобщенный класс со списком фалов и кусков реализация в модуле torrent.py
        self.peers = {}
        self.pending_blocks = []
        self.missing_pieces = []
        self.ongoing_pieces = []
        self.have_pieces = []
        self.max_pending_time = 300 * 1000  # 5 min сколько можно ждать что нам отдадут кусок
        self.missing_pieces = self._initiate_pieces() # что нам нужно
        self.total_pieces = len(torrent.pieces)
        self.fd = os.open(self.torrent.output_file,  os.O_RDWR | os.O_CREAT) #файл для записи

    def _initiate_pieces(self) -> [Piece]:
        """
        Pre-construct the list of pieces and blocks based on the number of
        pieces and request size for this torrent.
        """
        torrent = self.torrent
        pieces = []
        total_pieces = len(torrent.pieces)
        std_piece_blocks = math.ceil(torrent.piece_length / REQUEST_SIZE)
         # расчет количества блоков для куска, округляет результат деления

        for index, hash_value in enumerate(torrent.pieces):

            if index < (total_pieces - 1):
                blocks = [Block(index, offset * REQUEST_SIZE, REQUEST_SIZE)
                          for offset in range(std_piece_blocks)]
            else:
                last_length = torrent.total_size % torrent.piece_length
                num_blocks = math.ceil(last_length / REQUEST_SIZE)
                blocks = [Block(index, offset * REQUEST_SIZE, REQUEST_SIZE)
                          for offset in range(num_blocks)]

                if last_length % REQUEST_SIZE > 0:
# тут идет расчет уже для последнего блока который меньше чем обычный
                    last_block = blocks[-1]
                    last_block.length = last_length % REQUEST_SIZE
                    blocks[-1] = last_block
            pieces.append(Piece(index, blocks, hash_value))
        return pieces

    def close(self):
#закрывает файл для записи
        if self.fd:
            os.close(self.fd)

    @property
    def complete(self):
        """
Проверяет скачаны ли все куски торрента
        """
        return len(self.have_pieces) == self.total_pieces

    @property
    def bytes_downloaded(self) -> int:
        """
Сколько блоков куска скачано
        """
        return len(self.have_pieces) * self.torrent.piece_length

    @property
    def bytes_uploaded(self) -> int:
        return 0

    def add_peer(self, peer_id, bitfield):

        self.peers[peer_id] = bitfield

    def update_peer(self, peer_id, index: int):
        """
Сколько кусков  имеет другой  пир
        """
        if peer_id in self.peers:
            self.peers[peer_id][index] = 1

    def remove_peer(self, peer_id):
        """
    Удаляет пир, используется при разрыве соединения
        """
        if peer_id in self.peers:
            del self.peers[peer_id]

    def next_request(self, peer_id) -> Block:


        if peer_id not in self.peers:
            return None

        block = self._expired_requests(peer_id)
        if not block:
            block = self._next_ongoing(peer_id)
            if not block:
                block = self._get_rarest_piece(peer_id).next_request()
        return block

    def block_received(self, peer_id, piece_index, block_offset, data):

        logging.debug('Received block {block_offset} for piece {piece_index} '
                      'from peer {peer_id}: '.format(block_offset=block_offset,
                                                     piece_index=piece_index,
                                                     peer_id=peer_id))

        for index, request in enumerate(self.pending_blocks):
            if request.block.piece == piece_index and \
               request.block.offset == block_offset:
                del self.pending_blocks[index]
                break

        pieces = [p for p in self.ongoing_pieces if p.index == piece_index]
        piece = pieces[0] if pieces else None
        if piece:
            piece.block_received(block_offset, data)
            if piece.is_complete_retrieved():
                if piece.is_hash_matching():
                    self._write(piece)
                    self.ongoing_pieces.remove(piece)
                    self.have_pieces.append(piece)
                    complete = (self.total_pieces -
                                len(self.missing_pieces) -
                                len(self.ongoing_pieces))
                    logging.info(
                        '{complete} / {total} pieces downloaded {per:.3f} %'
                        .format(complete=complete,
                                total=self.total_pieces,
                                per=(complete/self.total_pieces)*100))
                else:
                    logging.info('Discarding corrupt piece {index}'
                                 .format(index=piece.index))
                    piece.reset()
        else:
            logging.warning('Trying to update piece that is not ongoing!')

    def _expired_requests(self, peer_id) -> Block:

        current = int(round(time.time() * 1000))
        for request in self.pending_blocks:
            if self.peers[peer_id][request.block.piece]:
                if request.added + self.max_pending_time < current:
                    logging.info('Re-requesting block {block} for '
                                 'piece {piece}'.format(
                                    block=request.block.offset,
                                    piece=request.block.piece))
                    # Reset expiration timer
                    request.added = current
                    return request.block
        return None

    def _next_ongoing(self, peer_id) -> Block:

        for piece in self.ongoing_pieces:
            if self.peers[peer_id][piece.index]:
                # Is there any blocks left to request in this piece?
                block = piece.next_request()
                if block:
                    self.pending_blocks.append(
                        PendingRequest(block, int(round(time.time() * 1000))))
                    return block
        return None

    def _get_rarest_piece(self, peer_id):

        piece_count = defaultdict(int)
        for piece in self.missing_pieces:
            if not self.peers[peer_id][piece.index]:
                continue
            for p in self.peers:
                if self.peers[p][piece.index]:
                    piece_count[piece] += 1

        rarest_piece = min(piece_count, key=lambda p: piece_count[p])
        self.missing_pieces.remove(rarest_piece)
        self.ongoing_pieces.append(rarest_piece)
        return rarest_piece

    def _next_missing(self, peer_id) -> Block:

        for index, piece in enumerate(self.missing_pieces):
            if self.peers[peer_id][piece.index]:
                # Move this piece from missing to ongoing
                piece = self.missing_pieces.pop(index)
                self.ongoing_pieces.append(piece)
                # The missing pieces does not have any previously requested
                # blocks (then it is ongoing).
                return piece.next_request_block()
        return None

    def _write(self, piece):

        pos = piece.index * self.torrent.piece_length
        os.lseek(self.fd, pos, os.SEEK_SET)
        os.write(self.fd, piece.data)
