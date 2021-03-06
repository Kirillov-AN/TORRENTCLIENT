from collections import OrderedDict

TOKEN_INT= b'i'
TOKEN_LIST = b'l'
TOKEN_DICT=b'd'
TOKEN_END=b'e'
TOKEN_SEPARATE=b':'




class Encoder:

    def __init__(self, data):
        self._data = data

    def encode(self) -> bytes:

        return self.encode_next(self._data)

    def encode_next(self, data):
        if type(data) == str:
            return self._encode_string(data)
        elif type(data) == int:
            return self._encode_int(data)
        elif type(data) == list:
            return self._encode_list(data)
        elif type(data) == dict or type(data) == OrderedDict:
            return self._encode_dict(data)
        elif type(data) == bytes:
            return self._encode_bytes(data)
        else:
            return None

    def _encode_int(self, value):
        return str.encode('i' + str(value) + 'e')

    def _encode_string(self, value: str):
        res = str(len(value)) + ':' + value
        return str.encode(res)

    def _encode_bytes(self, value: str):
        result = bytearray()
        result += str.encode(str(len(value)))
        result += b':'
        result += value
        return result

    def _encode_list(self, data):
        result = bytearray('l', 'utf-8')
        result += b''.join([self.encode_next(item) for item in data])
        result += b'e'
        return result

    def _encode_dict(self, data: dict) -> bytes:
        result = bytearray('d', 'utf-8')
        for k, v in data.items():
            key = self.encode_next(k)
            value = self.encode_next(v)
            if key and value:
                result += key
                result += value
            else:
                raise RuntimeError('Bad dict')
        result += b'e'
        return result

class Decoder:
    def __init__(self,data):
        if not isinstance(data,bytes):
            raise TypeError("data must be bytes")
        self.data = data
        self.index = 0

    def rr(self):
          print(lol) # Здесь в идеале заменить на self.lol
    def decode(self):


            c = self.lol()
            if c is None:
                  raise EOFError('Unexpected end-of-file')
            elif c == TOKEN_INT:
                    self.consume()
                    return self.decode_int()
            elif c == TOKEN_LIST:
                    self.consume()
                    return self.decode_list()
            elif c == TOKEN_DICT:
                    self.consume()
                    return self.decode_dict()
            elif c == TOKEN_END:
                    return None
            elif c in b'01234567899':
                        return self.decode_string()
            else:
                        raise RuntimeError('Invalid token read at {0}'.format(
                            str(self.index)))


    def lol(self):

        if self.index + 1 >= len(self.data):
            return None
        return self.data[self.index:self.index + 1]

    def consume(self) -> bytes:
        self.index += 1
    def read(self, length) -> bytes:

        if self.index + length > len(self.data):
            raise IndexError('Cannot read {0} bytes from current position {1}'
                             .format(str(length), str(self.index)))
        res = self.data[self.index:self.index+length]
        self.index += length
        return res
    def read_until(self, token) -> bytes:

        try:
            occurrence = self.data.index(token, self.index)
            result = self.data[self.index:occurrence]
            self.index = occurrence + 1
            return result
        except ValueError:
            raise RuntimeError('Unable to find token {0}'.format(
                str(token)))
            def _decode_int(self):                          # Зачем дважды писать decode_int ?
              return int(self._read_until(TOKEN_END))
    def decode_int(self):
        return int(self.read_until(TOKEN_END))

    def decode_list(self):
        res = []
        while self.data[self.index: self.index + 1] != TOKEN_END:
            res.append(self.decode())
        self.consume()
        return res

    def decode_dict(self):
        res = OrderedDict()
        while self.data[self.index: self.index + 1] != TOKEN_END:
            key = self.decode()
            obj = self.decode()
            res[key] = obj
        self.consume()
        return res

    def decode_string(self):
        bytes_to_read = int(self.read_until(TOKEN_SEPARATE))
        data = self.read(bytes_to_read)
        return data



with open("RimWorld.torrent", 'rb') as f:
            meta_info = f.read()
            meta_info = Decoder(meta_info).decode()
            info = Encoder(meta_info[b'info']).encode()
