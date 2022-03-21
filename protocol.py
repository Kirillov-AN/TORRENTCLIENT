import struct
from concurrent.futures import CancelledError
import asyncio
from asyncio import Queue

import bitstring

REQUEST_SIZE = 2**14


class ProtocolBaseError(BaseException):
    pass


class ConnectionToPeer:
    def __init__(self, torrent_queue, torrent_hash,
                 torrent_peer_id, torrent_piece_manager, torrent_on_block_cb=None):
        self.my_state = []
        self.peer_state = []
        self.torrent_queue = torrent_queue
        self.torrent_hash = torrent_hash
        self.torrent_peer_id = torrent_peer_id
        self.torrent_remote_id = None
        self.torrent_writer = None
        self.torrent_reader = None
        self.torrent_piece_manager = torrent_piece_manager
        self.torrent_on_block_cb = torrent_on_block_cb
        self.torrent_future = asyncio.ensure_future(self.start())

    async def start(self):
        while 'stopped' not in self.my_state:
            ip, port = await self.torrent_queue.get()
            print('Got assigned peer with: {ip}'.format(ip=ip))

            try:
                self.reader, self.writer = await asyncio.open_connection(
                    ip, port)
                print('Connection open to peer: {ip}'.format(ip=ip))

                buffer = await self.handshake()

                self.my_state.append('choked')

                await self.send_interested()
                self.my_state.append('interested')

                async for message in StreamOfPeerIteratoration(self.reader, buffer):
                    if 'stopped' in self.my_state:
                        break
                    if type(message) is BitField:
                        self.torrent_piece_manager.add_peer(self.remote_id,
                                                    message.bitfield)
                    elif type(message) is Interested:
                        self.peer_state.append('interested')
                    elif type(message) is NotInterested:
                        if 'interested' in self.peer_state:
                            self.peer_state.remove('interested')
                    elif type(message) is Choke:
                        self.my_state.append('choked')
                    elif type(message) is Unchoke:
                        if 'choked' in self.my_state:
                            self.my_state.remove('choked')
                    elif type(message) is Have:
                        self.torrent_piece_manager.update_peer(self.remote_id,
                                                       message.index)
                    elif type(message) is KeepAlive:
                        pass
                    elif type(message) is Piece:
                        self.my_state.remove('pending_request')
                        self.torrent_on_block_cb(
                            peer_id=self.remote_id,
                            piece_index=message.index,
                            block_offset=message.begin,
                            data=message.block)
                    elif type(message) is Request:
                        print('Ignoring the received Request message.')
                    elif type(message) is Cancel:
                        print('Ignoring the received Cancel message.')

                    if 'choked' not in self.my_state:
                        if 'interested' in self.my_state:
                            if 'pending_request' not in self.my_state:
                                self.my_state.append('pending_request')
                                await self.request_chunk()

            except ProtocolBaseError as e:
                print('Protocol error')
            except (ConnectionRefusedError, TimeoutError):
                print('Unable to connect to peer')
            except (ConnectionResetError, CancelledError):
                print('Connection closed')
            except Exception as e:
                print('An error occurred')
                self.cancel()
                raise e
            self.cancel()

    def cancel(self):
        print('Closing peer {id}'.format(id=self.remote_id))
        if not self.torrent_future.done():
            self.torrent_future.cancel()
        if self.writer:
            self.writer.close()

        self.torrent_queue.task_done()

    def stop(self):
        self.my_state.append('stopped')
        if not self.torrent_future.done():
            self.torrent_future.cancel()

    async def request_chunk(self):
        block = self.torrent_piece_manager.next_request(self.remote_id)
        if block:
            message = Request(block.piece, block.offset, block.length).encode()
            print('Requesting block {block} for piece {piece} '
                          'of {length} bytes from peer {peer}'.format(
                            piece=block.piece,
                            block=block.offset,
                            length=block.length,
                            peer=self.remote_id))

            self.writer.write(message)
            await self.writer.drain()

    async def handshake(self):
        self.writer.write(ClientHandshake(self.torrent_hash, self.torrent_peer_id).encode())
        await self.writer.drain()

        buf = b''
        tries = 1
        while len(buf) < ClientHandshake.length and tries < 10:
            tries += 1
            buf = await self.reader.read(StreamOfPeerIteratoration.CHUNK_SIZE)

        response = ClientHandshake.decode(buf[:ClientHandshake.length])
        if not response:
            raise ProtocolBaseError('Unable receive and parse a handshake')
        if not response.info_hash == self.torrent_hash:
            raise ProtocolBaseError('Handshake with invalid info_hash')

        self.remote_id = response.peer_id
        print('Handshake with peer was successful')

        return buf[ClientHandshake.length:]

    async def send_interested(self):
        message = Interested()
        print('Sending message: {type}'.format(type=message))
        self.writer.write(message.encode())
        await self.writer.drain()


class StreamOfPeerIteratoration:
    CHUNK_SIZE = 10*1024

    def __init__(self, reader, initial: bytes=None):
        self.reader = reader
        self.buffer = initial if initial else b''

    async def __aiter__(self):
        return self

    async def __anext__(self):
        while True:
            try:
                data = await self.reader.read(StreamOfPeerIteratoration.CHUNK_SIZE)
                if data:
                    self.buffer += data
                    message = self.parse()
                    if message:
                        return message
                else:
                    print('No data read from stream')
                    if self.buffer:
                        message = self.parse()
                        if message:
                            return message
                    raise StopAsyncIteration()
            except ConnectionResetError:
                print('Connection closed by peer')
                raise StopAsyncIteration()
            except CancelledError:
                raise StopAsyncIteration()
            except StopAsyncIteration as e:
                raise e
            except Exception:
                print('Error when iterating over stream!')
                raise StopAsyncIteration()

    def parse(self):
        header_length = 4

        if len(self.buffer) > 4:  # 4 bytes is needed to identify the message
            message_length = struct.unpack('>I', self.buffer[0:4])[0]

            if message_length == 0:
                return KeepAlive()

            if len(self.buffer) >= message_length:
                message_id = struct.unpack('>b', self.buffer[4:5])[0]

                def _consume():
                    self.buffer = self.buffer[header_length + message_length:]

                def _data():
                    return self.buffer[:header_length + message_length]

                if message_id is PeerResponse.BitField:
                    data = _data()
                    _consume()
                    return BitField.decode(data)
                elif message_id is PeerResponse.Interested:
                    _consume()
                    return Interested()
                elif message_id is PeerResponse.NotInterested:
                    _consume()
                    return NotInterested()
                elif message_id is PeerResponse.Choke:
                    _consume()
                    return Choke()
                elif message_id is PeerResponse.Unchoke:
                    _consume()
                    return Unchoke()
                elif message_id is PeerResponse.Have:
                    data = _data()
                    _consume()
                    return Have.decode(data)
                elif message_id is PeerResponse.Piece:
                    data = _data()
                    _consume()
                    return Piece.decode(data)
                elif message_id is PeerResponse.Request:
                    data = _data()
                    _consume()
                    return Request.decode(data)
                elif message_id is PeerResponse.Cancel:
                    data = _data()
                    _consume()
                    return Cancel.decode(data)
                else:
                    print('Unsupported message!')
            else:
                print('Not enough in buffer in order to parse')
        return None


class PeerResponse:
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

    def encode(self) -> bytes:
        pass

    @classmethod
    def decode(cls, data: bytes):
        pass


class ClientHandshake(PeerResponse):
    length = 49 + 19

    def __init__(self, info_hash: bytes, peer_id: bytes):
        if isinstance(info_hash, str):
            info_hash = info_hash.encode('utf-8')
        if isinstance(peer_id, str):
            peer_id = peer_id.encode('utf-8')
        self.info_hash = info_hash
        self.peer_id = peer_id

    def encode(self) -> bytes:
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
        if len(data) < (49 + 19):
            return None
        parts = struct.unpack('>B19s8x20s20s', data)
        return cls(info_hash=parts[2], peer_id=parts[3])

    def __str__(self):
        return 'Handshake'


class KeepAlive(PeerResponse):
    def __str__(self):
        return 'KeepAlive'


class BitField(PeerResponse):
    def __init__(self, data):
        self.bitfield = bitstring.BitArray(bytes=data)

    def encode(self) -> bytes:
        bits_length = len(self.bitfield)
        return struct.pack('>Ib' + str(bits_length) + 's',
                           1 + bits_length,
                           PeerResponse.BitField,
                           self.bitfield)

    @classmethod
    def decode(cls, data: bytes):
        message_length = struct.unpack('>I', data[:4])[0]
        print('Decoding BitField of length: {length}'.format(
            length=message_length))

        parts = struct.unpack('>Ib' + str(message_length - 1) + 's', data)
        return cls(parts[2])

    def __str__(self):
        return 'BitField'


class Interested(PeerResponse):
    def encode(self) -> bytes:
        return struct.pack('>Ib',
                           1,  # Message length
                           PeerResponse.Interested)

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
        self.index = index

    def encode(self):
        return struct.pack('>IbI',
                           5,  # Message length
                           PeerResponse.Have,
                           self.index)

    @classmethod
    def decode(cls, data: bytes):
        print('Decoding Have of length: {length}'.format(
            length=len(data)))
        index = struct.unpack('>IbI', data)[2]
        return cls(index)

    def __str__(self):
        return 'Have'


class Request(PeerResponse):
    def __init__(self, index: int, begin: int, length: int = REQUEST_SIZE):
        self.index = index
        self.begin = begin
        self.length = length

    def encode(self):
        return struct.pack('>IbIII',
                           13,
                           PeerResponse.Request,
                           self.index,
                           self.begin,
                           self.length)

    @classmethod
    def decode(cls, data: bytes):
        print('Decoding Request of length: {length}'.format(
            length=len(data)))
        # Tuple with (message length, id, index, begin, length)
        parts = struct.unpack('>IbIII', data)
        return cls(parts[2], parts[3], parts[4])

    def __str__(self):
        return 'Request'


class Piece(PeerResponse):
    # The Piece message length without the block data
    length = 9

    def __init__(self, index: int, begin: int, block: bytes):
        self.index = index
        self.begin = begin
        self.block = block

    def encode(self):
        message_length = Piece.length + len(self.block)
        return struct.pack('>IbII' + str(len(self.block)) + 's',
                           message_length,
                           PeerResponse.Piece,
                           self.index,
                           self.begin,
                           self.block)

    @classmethod
    def decode(cls, data: bytes):
        print('Decoding Piece of length: {length}'.format(
            length=len(data)))
        length = struct.unpack('>I', data[:4])[0]
        parts = struct.unpack('>IbII' + str(length - Piece.length) + 's',
                              data[:length+4])
        return cls(parts[2], parts[3], parts[4])

    def __str__(self):
        return 'Piece'


class Cancel(PeerResponse):
    def __init__(self, index, begin, length: int = REQUEST_SIZE):
        self.index = index
        self.begin = begin
        self.length = length

    def encode(self):
        return struct.pack('>IbIII',
                           13,
                           PeerResponse.Cancel,
                           self.index,
                           self.begin,
                           self.length)

    @classmethod
    def decode(cls, data: bytes):
        print('Decoding Cancel of length: {length}'.format(
            length=len(data)))
        parts = struct.unpack('>IbIII', data)
        return cls(parts[2], parts[3], parts[4])

    def __str__(self):
        return 'Cancel'
