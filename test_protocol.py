import unittest

from protocol import StreamOfPeerIteratoration, ClientHandshake, Have, Request, \
    Piece, Interested, Cancel


class PeerStreamIteratorTests(unittest.TestCase):
    def test_parse_empty_buffer(self):
        iterator = StreamOfPeerIteratoration(None)
        iterator.buffer = ""
        self.assertIsNone(iterator.parse())


Tester = PeerStreamIteratorTests()
Tester.test_parse_empty_buffer()

class HandshakeTests(unittest.TestCase):
    def test_construction(self):
        handshake = ClientHandshake(
            info_hash=b"CDP;~y~\xbf1X#'\xa5\xba\xae5\xb1\x1b\xda\x01",
            peer_id=b"-qB3200-iTiX3rvfzMpr")

        self.assertEqual(
            handshake.encode(),
            b"\x13BitTorrent protocol\x00\x00\x00\x00\x00\x00\x00\x00"
            b"CDP;~y~\xbf1X#'\xa5\xba\xae5\xb1\x1b\xda\x01"
            b"-qB3200-iTiX3rvfzMpr")

    def test_parse(self):
        handshake = ClientHandshake.decode(
            b"\x13BitTorrent protocol\x00\x00\x00\x00\x00\x00\x00\x00"
            b"CDP;~y~\xbf1X#'\xa5\xba\xae5\xb1\x1b\xda\x01"
            b"-qB3200-iTiX3rvfzMpr")

        self.assertEqual(
            b"CDP;~y~\xbf1X#'\xa5\xba\xae5\xb1\x1b\xda\x01",
            handshake.info_hash)
        self.assertEqual(
            b"-qB3200-iTiX3rvfzMpr",
            handshake.peer_id)


Tester = HandshakeTests()
Tester.test_construction()
Tester.test_parse()

class HaveMessageTests(unittest.TestCase):
    def test_can_construct_have(self):
        have = Have(33)
        self.assertEqual(
            have.encode(),
            b"\x00\x00\x00\x05\x04\x00\x00\x00!")

    def test_can_parse_have(self):
        have = Have.decode(b"\x00\x00\x00\x05\x04\x00\x00\x00!")
        self.assertEqual(33, have.index)

Tester = HaveMessageTests()
Tester.test_can_construct_have()
Tester.test_can_parse_have()

class RequestTests(unittest.TestCase):
    def test_can_construct_request(self):
        request = Request(0, 2)

        self.assertEqual(
            request.encode(),
            b"\x00\x00\x00\r\x06\x00\x00\x00\x00\x00\x00\x00\x02\x00\x00@\x00")

    def test_can_parse_request(self):
        request = Request.decode(
            b"\x00\x00\x00\r\x06\x00\x00\x00\x00\x00\x00\x00\x02\x00\x00@\x00")

        self.assertEqual(request.index, 0)
        self.assertEqual(request.begin, 2)


Tester = RequestTests()
Tester.test_can_construct_request()
Tester.test_can_parse_request()

class PieceTests(unittest.TestCase):
    def test_can_construct_piece(self):
        piece = Piece(0, 0, b'ok')

        self.assertEqual(
            piece.encode(),
            b"\x00\x00\x00\x0b\x07\x00\x00\x00\x00\x00\x00\x00\x00ok")

    def test_can_parse_request(self):
        piece = Piece.decode(
            b'\x00\x00\x00\x0b\x07\x00\x00\x00\x00\x00\x00\x00\x00ok')

        self.assertEqual(piece.index, 0)
        self.assertEqual(piece.begin, 0)
        self.assertEqual(piece.block, b'ok')


Tester = PieceTests()
Tester.test_can_construct_piece()
Tester.test_can_parse_request()

class InterestedTests(unittest.TestCase):
    def test_can_encode(self):
        message = Interested()
        raw = message.encode()

        self.assertEqual(raw, b'\x00\x00\x00\x01\x02') # при замене на self.assertEqual(raw, b'\x00\x00\x00\x01\x01') тест выдаст ошибку

Tester = InterestedTests()
Tester.test_can_encode()

class CancelTests(unittest.TestCase):
    def test_can_encode(self):
        message = Cancel(0, 2)

        self.assertEqual(
            message.encode(),
            b"\x00\x00\x00\r\x08\x00\x00\x00\x00\x00\x00\x00\x02\x00\x00@\x00")

    def test_can_decode(self):
        message = Cancel.decode(
            b"\x00\x00\x00\r\x08\x00\x00\x00\x00\x00\x00\x00\x02\x00\x00@\x00")

        self.assertEqual(message.index, 0)
        self.assertEqual(message.begin, 2)

Tester = CancelTests()
Tester.test_can_encode()
Tester.test_can_decode()