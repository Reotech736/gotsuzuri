"""人工GTだけで、持続接続の転送・保存・拒否・終了を確認する。"""
import copy
import hashlib
import http.client
import json
import random
import socket
import tempfile
import threading
import unittest
import uuid
from pathlib import Path

from PIL import Image
from server import HERE, make_server, prepare


class HttpConnectionTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='http-test-', dir=HERE.parents[1]/'captures')
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        image = root/'noise.png'
        Image.frombytes('RGB', (640, 640), random.Random(42).randbytes(640*640*3)).save(image)
        self.folder = root/'dataset'
        prepare(image, self.folder, 'fixture', 'synthetic', [[.1,.1],[.9,.1],[.9,.9],[.1,.9]])
        self.server = make_server(self.folder)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop)
        self.origin = f'http://127.0.0.1:{self.server.server_port}'

    def stop(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()

    def connection(self):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
        self.addCleanup(connection.close)
        return connection

    def get(self, connection, route='/api/data', headers=None):
        connection.request('GET', route, headers=headers or {})
        response = connection.getresponse()
        raw = response.read()
        return response, raw

    def test_large_image_and_save_replay_share_the_same_connection(self):
        connection = self.connection()
        response, raw = self.get(connection)
        live = json.loads(raw); original_socket = connection.sock
        self.assertEqual('keep-alive', response.getheader('Connection'))
        digest = hashlib.sha256((self.folder/'source.png').read_bytes()).digest()
        for _ in range(5):
            response, raw = self.get(connection, '/source.png')
            self.assertGreater(len(raw), 1048576)
            self.assertEqual(digest, hashlib.sha256(raw).digest())
            self.assertIs(original_socket, connection.sock)
        candidate = copy.deepcopy(live['data']); candidate['geometryReviewed'] = True
        candidate['labels'][0] = 'black'
        payload = json.dumps(dict(saveId=str(uuid.uuid4()), expectedRevision=0, data=candidate))
        headers = {'Origin': self.origin, 'X-Label-Token': live['token'], 'Content-Type':'application/json'}
        def save(body):
            connection.request('POST', '/api/save', body, headers)
            response = connection.getresponse(); raw = response.read()
            return response, json.loads(raw)
        response, first = save(payload)
        self.assertEqual(200, response.status)
        previous = (self.folder/'annotations.previous.json').read_bytes()
        response, replay = save(payload)
        self.assertEqual(200, response.status)
        self.assertEqual(first, replay)
        self.assertEqual(previous, (self.folder/'annotations.previous.json').read_bytes())
        self.assertIs(original_socket, connection.sock)
        stale = json.loads(payload); stale['saveId'] = str(uuid.uuid4())
        response, _ = save(json.dumps(stale))
        self.assertEqual(409, response.status)
        self.assertEqual('close', response.getheader('Connection'))
        saved = json.loads((self.folder/'annotations.json').read_bytes())
        self.assertEqual((1, 'black'), (saved['revision'], saved['labels'][0]))

    def test_rejects_host_origin_and_token_without_saving(self):
        _, raw = self.get(self.connection()); live = json.loads(raw)
        body = json.dumps(dict(expectedRevision=0, data=live['data']))
        valid = {'Host':f'127.0.0.1:{self.server.server_port}', 'Origin':self.origin, 'X-Label-Token':live['token']}
        before = (self.folder/'annotations.json').read_bytes()
        for key in valid:
            with self.subTest(header=key):
                headers = dict(valid); headers[key] = 'wrong'
                connection = self.connection()
                connection.request('POST', '/api/save', body, headers)
                response = connection.getresponse(); response.read()
                self.assertEqual(403, response.status)
                self.assertEqual('close', response.getheader('Connection'))
        self.assertEqual(before, (self.folder/'annotations.json').read_bytes())

    def test_unread_or_ambiguous_request_body_closes_connection(self):
        before = (self.folder/'annotations.json').read_bytes()
        requests = [
            b'GET /api/data HTTP/1.1\r\nContent-Length: 1\r\n\r\nx',
            b'GET /api/data HTTP/1.1\r\nTransfer-Encoding: chunked\r\n\r\n0\r\n\r\n',
        ]
        for request in requests:
            connection = socket.create_connection(('127.0.0.1',self.server.server_port), timeout=2)
            with connection:
                request = request.replace(b'\r\n', f'\r\nHost: 127.0.0.1:{self.server.server_port}\r\n'.encode(), 1)
                connection.sendall(request)
                response = http.client.HTTPResponse(connection); response.begin(); response.read()
                self.assertEqual(400, response.status)
                self.assertEqual('close', response.getheader('Connection'))
        # 本文長の重複は、同じ値でも接続を維持せず拒否する。
        _, raw = self.get(self.connection()); token = json.loads(raw)['token']
        for framing in ['Content-Length: 2\r\nContent-Length: 2', 'Content-Length: 2\r\nTransfer-Encoding: chunked']:
            with socket.create_connection(('127.0.0.1',self.server.server_port), timeout=2) as connection:
                connection.sendall((f'POST /api/save HTTP/1.1\r\nHost: 127.0.0.1:{self.server.server_port}\r\nOrigin: {self.origin}\r\nX-Label-Token: {token}\r\n{framing}\r\n\r\n{{}}').encode())
                response = http.client.HTTPResponse(connection); response.begin(); response.read()
                self.assertEqual(400, response.status)
                self.assertEqual('close', response.getheader('Connection'))
        self.assertEqual(before, (self.folder/'annotations.json').read_bytes())

    def test_idle_timeout_and_client_requested_close(self):
        self.server.RequestHandlerClass.timeout = .15
        connection = self.connection()
        self.get(connection)
        transport = connection.sock
        transport.settimeout(2)
        self.assertEqual(b'', transport.recv(1))
        response, _ = self.get(self.connection(), headers={'Connection':'close'})
        self.assertEqual('close', response.getheader('Connection'))
        self.assertTrue(response.will_close)
