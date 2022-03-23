import struct  # Интерпретировать байты как упакованные двоичные данные
from concurrent.futures import CancelledError #Это исключение можно перехватить для выполнения пользовательских операций при отмене асинхронных задач. Почти во всех ситуациях необходимо повторно вызвать исключение.
import asyncio # это библиотека для написания параллельного кода с использованием синтаксиса async/await
from asyncio import Queue # очереди asyncio спроектированы так, чтобы быть похожими на классы queueмодуля. Хотя асинхронные очереди не являются потокобезопасными, они предназначены специально для использования в асинхронном/ожидающем коде

import bitstring # это чистый модуль Python, разработанный, чтобы сделать создание и анализ двоичных данных максимально простым и естественным

REQUEST_SIZE = 2**14 # размер запроса


class ProtocolBaseError(BaseException): # исключение при работе протокола
    pass


"""
Одноранговое соединение, используемое для загрузки и выгрузки фрагментов.

    Одноранговое соединение будет потреблять один доступный одноранговый узел из данной очереди.
    На основе сведений об одноранговых узлах PeerConnection попытается открыть соединение.
    и выполните рукопожатие BitTorrent.

    После успешного рукопожатия PeerConnection будет в *задушенном* состоянии.
    состояние, не разрешено запрашивать какие-либо данные от удаленного узла. После отправки
    заинтересованное сообщение, которое PeerConnection будет ожидать, чтобы его *разблокировали*.

    Как только удаленный пир освободит нас, мы можем начать запрашивать части.
    PeerConnection будет продолжать запрашивать части до тех пор, пока есть
    куски, оставшиеся для запроса, или до тех пор, пока удаленный узел не отключится.

    Если соединение с удаленным узлом разрывается, PeerConnection потребляет
    следующий доступный одноранговый узел из очереди и попытаться подключиться к нему
    вместо.
"""

# Асинхронный HTTP

class ConnectionToPeer: # подключение к пиру
    def __init__(self, torrent_queue, torrent_hash,
                 torrent_peer_id, torrent_piece_manager, torrent_on_block_cb=None):
        """
        :param torrent_queue: асинхронная очередь, содержащая список доступных пиров
        :param torrent_hash: Хэш SHA1 для информации метаданных
        :param torrent_peer_id: Идентификатор нашего пира, используемый для идентификации нас
        :param torrent_piece_manager: Менеджер, ответственный за определение того, какие части
                              запросить
        :param torrent_on_block_cb: Функция обратного вызова для вызова, когда блок
                            получено от удаленного узла
        """

        """
            Choked (заблокирован) — в этом состоянии пир не может запрашивать фрагменты у другого пира;
            Unchoked (разблокирован) — в этом состоянии пир может запрашивать фрагменты у другого пира;
            Interested (заинтересован) — это состояние говорит о том, что пир заинтересован в получении фрагментов;
            Not interested (не заинтересован) — это состояние говорит о том, что пир не заинтересован в получении фрагментов.
        """
        self.my_state = [] # список наших состояний начинается с Choked или Not interested. Состояния меняются в результате ответа пиров
        self.peer_state = []  # список состояний пиров начинается с Choked или Not interested. Состояния меняются в результате ответа пиров
        self.torrent_queue = torrent_queue
        self.torrent_hash = torrent_hash
        self.torrent_peer_id = torrent_peer_id
        self.torrent_remote_id = None # нигде не используется в коде
        self.torrent_writer = None # нигде не используется в коде, но судя по всему нужен для записи данных
        self.torrent_reader = None # нигде не используется в коде, но судя по всему нужен для чтения данных
        self.torrent_piece_manager = torrent_piece_manager
        self.torrent_on_block_cb = torrent_on_block_cb
        self.torrent_future = asyncio.ensure_future(self.start()) # запускаем задачу из произвольного ожидаемого асинхронно

    async def start(self):
        while 'stopped' not in self.my_state: # запускаем цикл пока не получим в список my_state состояние stopped
            ip, port = await self.torrent_queue.get() # получаем кортеж из очереди торрента
            print('Got assigned peer with: {ip}'.format(ip=ip)) # сообщение о том по какому ip назначен узел

            try: # пытаемся
                self.reader, self.writer = await asyncio.open_connection(
                    ip, port) # получить кортеж из открытого соединения
                print('Connection open to peer: {ip}'.format(ip=ip)) # если все хорошо пишем, что соединение открыто

                buffer = await self.handshake() # ждем хэндшейк

                self.my_state.append('choked') # добавляем в список наших состояниц choked

                await self.send_interested() # посылаем заинтересованное состояние
                self.my_state.append('interested') # добавляем заинтересованное состояние к себе

                async for message in StreamOfPeerIteratoration(self.reader, buffer): # итерируемся по итераторам Пира ка по range
                    if 'stopped' in self.my_state: # если наше состояние stopped, то break
                        break
                    if type(message) is BitField: # проверка типа на BitField
                        self.torrent_piece_manager.add_peer(self.remote_id,
                                                    message.bitfield) # добавляем через add_peer id и bitfield MAGIC!
                    elif type(message) is Interested: # проверка типа на Interested
                        self.peer_state.append('interested') # добавление в список пира состояния Interested
                    elif type(message) is NotInterested: # проверка типа на NotInterested
                        if 'interested' in self.peer_state: # если в списке пира есть interested
                            self.peer_state.remove('interested') # удаляем из списка пира interested
                    elif type(message) is Choke: # проверка типа на Choke
                        self.my_state.append('choked') # добавление в наш список состояния Choke
                    elif type(message) is Unchoke: # проверка типа на Unchoke
                        if 'choked' in self.my_state: # если в нашем списке есть chocked
                            self.my_state.remove('choked') # удалить из нашего списка состояний
                    elif type(message) is Have: # проверка типа на Have
                        self.torrent_piece_manager.update_peer(self.remote_id,
                                                       message.index) # сколько кусков имеет другой пир. Реализация в Piece.py
                    elif type(message) is KeepAlive: # проверка типа на KeepAlive
                        pass # заглушка либо ничего не надо делать
                    elif type(message) is Piece: # проверка типа на Piece
                        self.my_state.remove('pending_request') # удалить из наших состояний ожидающий запрос
                        self.torrent_on_block_cb(
                            peer_id=self.remote_id,
                            piece_index=message.index,
                            block_offset=message.begin,
                            data=message.block) # Вызов функции обратного вызова для вызова, когда блок получено от удаленного узла
                    elif type(message) is Request: # проверка типа на Request
                        print('Ignoring the received Request message.')
                    elif type(message) is Cancel: # проверка типа на Cancel
                        print('Ignoring the received Cancel message.')

                    if 'choked' not in self.my_state: # если choked нету в списке наших состояний
                        if 'interested' in self.my_state: # и если interested нету в списке наших состояний
                            if 'pending_request' not in self.my_state: # и если pending_request нету в списке наших состояний
                                self.my_state.append('pending_request') # добавить в список наших состояний ожидающий запрос
                                await self.request_chunk() # вызвать асинхронную функцию

            except ProtocolBaseError as e: # обработка исключения протокола
                print('Protocol error')
            except (ConnectionRefusedError, TimeoutError): # Исключение, возникающее в случае отказа узла в попытке соединения или превышено время ожидания
                print('Unable to connect to peer')
            except (ConnectionResetError, CancelledError): # когда соединение сбрасывается узлом.
                print('Connection closed')
            except Exception as e: # для обработки прочих ошибок
                print('An error occurred')
                self.cancel() # прерываем процесс
                raise e # вызываем исключение e
            self.cancel() # для закрытия пира

    def cancel(self):
        print('Closing peer {id}'.format(id=self.remote_id)) # закрываем пир
        if not self.torrent_future.done(): # если не выполненно закрытие
            self.torrent_future.cancel() # то отменяем через torrent_future.cancel(). Есть прототип если перейти
        if self.writer: # если запись в файл открыта
            self.writer.close() # закрыть файл

        self.torrent_queue.task_done() # задание выполнено

    def stop(self):
        self.my_state.append('stopped') # добавляем состояние stopped. Значит закачка законченна
        if not self.torrent_future.done(): # если не выполненно закрытие
            self.torrent_future.cancel()  # то отменяем через torrent_future.cancel(). Есть прототип если перейти

    async def request_chunk(self):
        block = self.torrent_piece_manager.next_request(self.remote_id) # получаем bool ответ от next_request. Реализация в Piece.py
        if block: # если правда
            message = Request(block.piece, block.offset, block.length).encode() # получаем message через Request.encode()
            print('Requesting block {block} for piece {piece} '
                          'of {length} bytes from peer {peer}'.format(
                            piece=block.piece,
                            block=block.offset,
                            length=block.length,
                            peer=self.remote_id))

            self.writer.write(message) # запись message через поток writer в файл
            await self.writer.drain() # делаем запись асинхронно

    async def handshake(self): # получение handshake. Обмен рукопожатиями инициирует подключающийся клиент.
        self.writer.write(ClientHandshake(self.torrent_hash, self.torrent_peer_id).encode()) # Он позволяет записывать любую строку в открытый файл по полю writer
        await self.writer.drain() # Подождите, пока не будет уместно возобновить запись в поток.

        buf = b'' # инициализация бинарной строкой
        tries = 1 # счетчик попыток
        while len(buf) < ClientHandshake.length and tries < 10: # если попыток меньше 10 и длина буфера меньше фиксированной длины handshake
            tries += 1
            buf = await self.reader.read(StreamOfPeerIteratoration.CHUNK_SIZE) # пытаемся поймать handshake

        response = ClientHandshake.decode(buf[:ClientHandshake.length]) # ответ на рукопожатие
        if not response: # если ошибка
            raise ProtocolBaseError('Unable receive and parse a handshake') # Невозможно получить и проанализировать рукопожатие
        if not response.info_hash == self.torrent_hash: # если неверный hash
            raise ProtocolBaseError('Handshake with invalid info_hash') # то пишем, что пакет был поврежден

        self.remote_id = response.peer_id # инициализация удаленного id
        print('Handshake with peer was successful')

        return buf[ClientHandshake.length:] # возварт handshake

    async def send_interested(self):
        message = Interested() # инициализация message
        print('Sending message: {type}'.format(type=message))
        self.writer.write(message.encode()) # записываем message encode в файл
        await self.writer.drain() # Подождите, пока не будет уместно возобновить запись в поток.


class StreamOfPeerIteratoration: # итератор потока Пира
    CHUNK_SIZE = 10*1024 # размер куска

    def __init__(self, reader, initial: bytes=None):
        self.reader = reader # инициализация потока чтения
        self.buffer = initial if initial else b'' #инициализация буффера

    async def __aiter__(self): # для возврата асинхронного оператора
        return self

    async def __anext__(self): # для возврата следующего асинхронного оператора
        while True: # бесконечный цикл
            try:
                data = await self.reader.read(StreamOfPeerIteratoration.CHUNK_SIZE) # читаем 1 chunk
                if data: # если все хорошо
                    self.buffer += data # записываем chunk в buffer
                    message = self.parse() # парсим итератор
                    if message: # если успех вернуть message
                        return message
                else: # если ошибка вернуть,что не удалось прочитать chunk
                    print('No data read from stream')
                    if self.buffer: # парсим итератор
                        message = self.parse()
                        if message: # если успех вернуть message
                            return message
                    raise StopAsyncIteration() # вызов исключения асинхронного итератора
            except ConnectionResetError: # исключение закрытие пира
                print('Connection closed by peer')
                raise StopAsyncIteration()
            except CancelledError: # исключение закрытие пира
                raise StopAsyncIteration()
            except StopAsyncIteration as e:
                raise e
            except Exception: # исключение ошибки итерации
                print('Error when iterating over stream!')
                raise StopAsyncIteration()

    def parse(self): # парсер объекта
        header_length = 4 # длина заголовка

        if len(self.buffer) > 4:  # нужно для идентификации message
            message_length = struct.unpack('>I', self.buffer[0:4])[0] # получаем длинну сообщения

            if message_length == 0: # если длина равна нулю, то KeepAlive()
                return KeepAlive()

            if len(self.buffer) >= message_length: # если длинна буффера больше длины сообщения
                message_id = struct.unpack('>b', self.buffer[4:5])[0] # полукчаем message_id

                def _consume(): # функция потребитель
                    self.buffer = self.buffer[header_length + message_length:] # возврат обрезанного buffer

                def _data():  # функция данные
                    return self.buffer[:header_length + message_length]  # возврат обрезанного buffer

                if message_id is PeerResponse.BitField: # проверка на равенство message_id и BitField
                    data = _data() # запись данных
                    _consume() # потребить буффер
                    return BitField.decode(data) # возврат декодированных данных
                elif message_id is PeerResponse.Interested: # проверка на состояние Interested
                    _consume() # потребить буффер
                    return Interested() # вернуть заинтересованность
                elif message_id is PeerResponse.NotInterested: # проверка на состояние not Interested
                    _consume() # потребить буффер
                    return NotInterested() # вернуть незаинтересованность
                elif message_id is PeerResponse.Choke: # проверка на состояние Choke
                    _consume() # потребить буффер
                    return Choke() # вернуть закрытое состояние, но не Stopped!!!
                elif message_id is PeerResponse.Unchoke: # проверка на состояние Unchoke
                    _consume() # потребить буффер
                    return Unchoke() # вернуть открыть
                elif message_id is PeerResponse.Have: # проверка на Have. Have — сообщение, которое в любой момент может отправить нам удалённый пир
                    data = _data() # получение данных
                    _consume() # потребить буффер
                    return Have.decode(data) # вернуть декодированные данные
                elif message_id is PeerResponse.Piece: # проверка message_id на равенство Piece
                    data = _data() # получение данных
                    _consume() # потребить буффер
                    return Piece.decode(data) # вернуть декодированные данные
                elif message_id is PeerResponse.Request: # проверка message_id на соответсвие запросу
                    data = _data() # получение данных
                    _consume() # потребить буффер
                    return Request.decode(data) # вернуть декодированные данные
                elif message_id is PeerResponse.Cancel:  # проверка message_id на состояние отмены
                    data = _data() # получение данных
                    _consume() # потребить буффер
                    return Cancel.decode(data) # вернуть декодированные данные
                else:
                    print('Unsupported message!') # иначе сказать, что пакет не поддреживается
            else:
                print('Not enough in buffer in order to parse') # иначе недостаточно данных из буффера
        return None


class PeerResponse: # Ответы Пира
    Choke = 0
    Unchoke = 1
    Interested = 2
    NotInterested = 3
    Have = 4
    BitField = 5
    Request = 6
    Piece = 7
    Cancel = 8
    Port = 9
    Handshake = None
    KeepAlive = None

    def encode(self) -> bytes: # видимо заглушка
        pass

    @classmethod
    def decode(cls, data: bytes): # видимо заглушка
        pass


class ClientHandshake(PeerResponse): # Хэндшейк клиента
    length = 49 + 19 # размер хэндшейка

    def __init__(self, info_hash: bytes, peer_id: bytes):
        if isinstance(info_hash, str): # проверка соответсвия хэша на строку
            info_hash = info_hash.encode('utf-8') # превращаем хэш в байты
        if isinstance(peer_id, str): # проверка соответсвия peer_id на строку
            peer_id = peer_id.encode('utf-8')  # превращаем peer_id в байты
        self.info_hash = info_hash
        self.peer_id = peer_id

    def encode(self) -> bytes: # упаковываем хэш, пир id и другое в байты через структуру
        return struct.pack(
            '>B19s8x20s20s',
            19,                         # Single byte (B)
            b'BitTorrent protocol',     # String 19s
                                        # Reserved 8x (pad byte, no value)
            self.info_hash,             # String 20s
            self.peer_id)               # String 20s

    @classmethod
    def decode(cls, data: bytes):
        print('Decoding Handshake of length: {length}'.format(
            length=len(data)))
        if len(data) < (49 + 19): # проверка на целостность данных и на размер handshake
            return None
        parts = struct.unpack('>B19s8x20s20s', data) # распаковываем структуру
        return cls(info_hash=parts[2], peer_id=parts[3]) # это стандартное имя первого аргумента методов класса

    def __str__(self):
        return 'Handshake'


class KeepAlive(PeerResponse): # наследник класса состояния пиров
    def __str__(self):
        return 'KeepAlive'


class BitField(PeerResponse):
    def __init__(self, data):
        self.bitfield = bitstring.BitArray(bytes=data) # превращаем в bitstring байты data

    def encode(self) -> bytes:
        bits_length = len(self.bitfield) # получаем длинну битовой строки
        return struct.pack('>Ib' + str(bits_length) + 's',
                           1 + bits_length,
                           PeerResponse.BitField,
                           self.bitfield) # упаковываем длину строки, ответ от пира в структуру

    @classmethod
    def decode(cls, data: bytes):
        message_length = struct.unpack('>I', data[:4])[0]
        print('Decoding BitField of length: {length}'.format(
            length=message_length)) # распаковываем структуру битовой строки в message

        parts = struct.unpack('>Ib' + str(message_length - 1) + 's', data)
        return cls(parts[2]) # распаковываем структуру битовой строки в message

    def __str__(self):
        return 'BitField'


class Interested(PeerResponse):
    def encode(self) -> bytes:
        return struct.pack('>Ib',
                           1,  # Message length
                           PeerResponse.Interested) # упаковка состояния в байты

    def __str__(self):
        return 'Interested'


class NotInterested(PeerResponse):
    def __str__(self):
        return 'NotInterested'


class Choke(PeerResponse):
    def __str__(self):
        return 'Choke'


class Unchoke(PeerResponse):
    def __str__(self):
        return 'Unchoke'


class Have(PeerResponse):
    def __init__(self, index: int):
        self.index = index # получения индекса не нашел где вызывается конструктор

    def encode(self):
        return struct.pack('>IbI',
                           5,  # Message length
                           PeerResponse.Have,
                           self.index) # упаковка в структуру ответ пира и идекса

    @classmethod
    def decode(cls, data: bytes):
        print('Decoding Have of length: {length}'.format(
            length=len(data)))
        index = struct.unpack('>IbI', data)[2] # получения индекса и з распакованной структуры
        return cls(index)

    def __str__(self):
        return 'Have'


class Request(PeerResponse): # класс запрос
    def __init__(self, index: int, begin: int, length: int = REQUEST_SIZE):
        self.index = index # индекс
        self.begin = begin # откуда начинаем
        self.length = length # длина сообщения

    def encode(self):
        return struct.pack('>IbIII',
                           13,
                           PeerResponse.Request,
                           self.index,
                           self.begin,
                           self.length) # упаковываем ответ пира, индекс, откуда начинаем и длину в строку

    @classmethod
    def decode(cls, data: bytes):
        print('Decoding Request of length: {length}'.format(
            length=len(data)))
        # получаем кортеж (message length, id, index, begin, length)
        parts = struct.unpack('>IbIII', data)
        return cls(parts[2], parts[3], parts[4])

    def __str__(self):
        return 'Request'


class Piece(PeerResponse): # класс Piece но это не ток класс как в Piece.py
    length = 9 # длина пакета

    def __init__(self, index: int, begin: int, block: bytes):
        self.index = index # индекс куска в потоке
        self.begin = begin # с какого момента начинаем запись
        self.block = block # блок данных

    def encode(self):
        message_length = Piece.length + len(self.block)
        return struct.pack('>IbII' + str(len(self.block)) + 's',
                           message_length,
                           PeerResponse.Piece,
                           self.index,
                           self.begin,
                           self.block) # упаковка в структуру ответа пира, индекса куска в потоке, с какого момента начинаем запись, блока данных

    @classmethod
    def decode(cls, data: bytes):
        print('Decoding Piece of length: {length}'.format(
            length=len(data)))
        length = struct.unpack('>I', data[:4])[0] # распоковка длинны куска из структуры
        parts = struct.unpack('>IbII' + str(length - Piece.length) + 's',
                              data[:length+4]) # получение кортежа частей из структуры
        return cls(parts[2], parts[3], parts[4]) # возврат частей

    def __str__(self):
        return 'Piece'


class Cancel(PeerResponse): # класс отмены
    def __init__(self, index, begin, length: int = REQUEST_SIZE):
        self.index = index  # индекс
        self.begin = begin  # откуда начинаем
        self.length = length  # длина сообщения

    def encode(self):
        return struct.pack('>IbIII',
                           13,
                           PeerResponse.Cancel,
                           self.index,
                           self.begin,
                           self.length) # упаковка в структуру ответа пира, индекса куска в потоке, с какого момента начинаем запись, блока данных

    @classmethod
    def decode(cls, data: bytes):
        print('Decoding Cancel of length: {length}'.format(
            length=len(data)))
        parts = struct.unpack('>IbIII', data) # получение кортежа частей из структуры
        return cls(parts[2], parts[3], parts[4]) # возврат частей

    def __str__(self):
        return 'Cancel'


# последние 4 класса друг с другом очень похожи. Have, Request, Piece, Cancel имеют почти одинаковую структуру и отличаются лишь ответами