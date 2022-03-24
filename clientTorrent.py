import asyncio
import logging
import math
import os
import time
from asyncio import Queue
from collections import namedtuple, defaultdict
from hashlib import sha1
from piece import *

from protocol import ConnectionToPeer, REQUEST_SIZE
from tracker import Tracker

class TorrentClient:
    """
    Торрент-клиент — это локальный узел, поддерживающий одноранговые соединения.
    подключения для загрузки и выгрузки фрагментов для данного торрента.

    После запуска клиент делает периодические анонсирующие вызовы на трекер.
    прописан в метаданных торрента. Результатом этих вызовов является список
    одноранговые узлы, которые следует попробовать, чтобы обменяться частями.

    Каждый полученный одноранговый узел хранится в очереди, которую пул PeerConnection
    объекты потребляют. Существует фиксированное количество PeerConnections, которые могут иметь
    соединение, открытое для партнера. Так как мы не создаем дорогие темы
    (или еще хуже процессы) мы можем создать их все сразу и они будут
    ждать, пока в очереди не появится одноранговый узел для потребления.
    """
    def __init__(self, torrent):
        self.tracker = Tracker(torrent) # инициализация трекера. Реализация в tracker.py
        self.available_peers = Queue() # Список потенциальных пиров - это рабочая очередь, потребляемая ConnectionToPeer
        self.peers = [] # Список пиров — это список воркеров, которые *могут* быть подключены. В противном случае они ждут, чтобы потреблять новые удаленные одноранговые узлы из
        self.piece_manager = PieceManager(torrent) # Менеджер частей реализует стратегию, на которой фигуры должны запрос, а также логика сохранения полученных фрагментов на диск.
        self.abort = False

    async def start(self):
        """
        Начать загрузку торрента, удерживаемого этим клиентом.

        Это приводит к подключению к трекеру для получения списка
        сверстники для общения. Как только торрент полностью скачается или
        если загрузка будет прервана, этот метод завершится.
        """
        self.peers = [ConnectionToPeer(self.available_peers,
                                     self.tracker.torrent.info_hash,
                                     self.tracker.peer_id,
                                     self.piece_manager,
                                     self._on_block_retrieved)
                      for _ in range(MAX_PEER_CONNECTIONS)] # инициализация поля пиры объектами ConnectionToPeer. Реализация в ConnectionToPeer

        previous = None # предыдущий по умолчанию None
        interval = 30*60 # интервал звонка. Отметка времени

        while True: # бесконечный цикл
            if self.piece_manager.complete:  # если загрузка завершена сказать, что все закончилось
                logging.info('Torrent fully downloaded!')
                break
            if self.abort: # иначе сообщить о проблеме
                logging.info('Aborting download...')
                break

            current = time.time() # получение текущего времени
            if (not previous) or (previous + interval < current): # если сумма предыдущего и времени меньше временной метки
                response = await self.tracker.connect(
                    first=previous if previous else False,
                    uploaded=self.piece_manager.bytes_uploaded,
                    downloaded=self.piece_manager.bytes_downloaded) # сделать асинхронный запрос к трекеру используя предыдущее время, загруженные байты,байты которые надо скачать

                if response: # если ответ получен
                    previous = current # присвоение предыдущему времени текущей метки времени
                    interval = response.interval # инициализация временного интервала временем ответа
                    self._empty_queue() # чистим очередь
                    for peer in response.peers: # пока есть пиры в ответе
                        self.available_peers.put_nowait(peer) # положить пиры без блокировки
            else:
                await asyncio.sleep(5) # асинхронная задержка 5 миллисекунд
        self.stop() # остановить загрузку

    def _empty_queue(self): # метод очистки очереди
        while not self.available_peers.empty(): # пока все доступные пиры не пустые
            self.available_peers.get_nowait() # функция удаления элементов из очереди. Реализация в queues.py

    def stop(self):
        """
        Остановите процесс загрузки или заполнения.
        """
        self.abort = True # отменить процесс True
        for peer in self.peers: # пока есть пиры
            peer.stop() # останавливаем пиры. Реализация функции stop в protocol.py
        self.piece_manager.close() # закрываем файл для записи
        self.tracker.close() # закрываем http соединение

    def _on_block_retrieved(self, peer_id, piece_index, block_offset, data): # при получении блока
        """
        Функция обратного вызова, вызываемая `ConnectionToPeer`, когда блок
        получено от сверстника.

        :param peer_id: идентификатор пира, из которого был получен блок
        :param piece_index: индекс части, частью которого является этот блок
        :param block_offset: Смещение блока внутри его части
        :param data: Полученные двоичные данные
        """
        self.piece_manager.block_received(
            peer_id=peer_id, piece_index=piece_index,
            block_offset=block_offset, data=data) # получение блока по выше указанным параметрам
