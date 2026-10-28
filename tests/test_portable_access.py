import http.client
import http.cookiejar
import json
import tempfile
import threading
import time
import unittest
import urllib.request
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from app.demo import DemoEngine
from app.service import Service
from app.server import build_server


class PortableAccessTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.servers=[]
        self.client=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def tearDown(self):
        for server,thread in self.servers:
            server.shutdown();server.server_close();thread.join()
        self.temp.cleanup()

    def server(self):
        root=Path(self.temp.name)/str(len(self.servers))
        service=Service(DemoEngine(),root/'data',root/'media',root/'backup',True)
        server=build_server(service,'unused-secret-password',('127.0.0.1',0),bootstrap_token='test-launch-token',portable_export_dir=root/'prints')
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        self.servers.append((server,thread))
        return f'http://127.0.0.1:{server.server_port}'

    def read(self,url):
        return json.load(self.client.open(url,timeout=5))

    def bootstrap(self,url):
        self.client.open(url+'/?avvio=test-launch-token',timeout=5).read()

    def test_plain_page_stays_private_and_reports_passwordless_portable_mode(self):
        url=self.server()
        state=self.read(url+'/api/session')
        self.assertTrue(state['portable']);self.assertFalse(state['authenticated'])
        self.assertIsNone(state['csrf'])
        with self.assertRaises(urllib.error.HTTPError) as error:self.read(url+'/api/state')
        self.assertEqual(error.exception.code,401)
        self.bootstrap(url)
        self.assertTrue(self.read(url+'/api/session')['authenticated'])
        self.assertEqual(len(self.read(url+'/api/state')['people']),8)

    def test_two_local_copies_do_not_replace_each_others_access(self):
        a,b=self.server(),self.server()
        self.bootstrap(a);csrf_a=self.read(a+'/api/session')['csrf']
        self.bootstrap(b)
        self.assertEqual(self.read(a+'/api/session')['csrf'],csrf_a)
        self.assertTrue(self.read(b+'/api/session')['authenticated'])
        self.assertEqual(len(self.read(a+'/api/state')['people']),8)

    def test_expired_access_recovers_only_with_launcher_token(self):
        url=self.server();self.bootstrap(url)
        csrf=self.read(url+'/api/session')['csrf']
        future=time.monotonic()+9*3600
        with patch('app.server.time',SimpleNamespace(monotonic=lambda:future)):
            self.assertFalse(self.read(url+'/api/session')['authenticated'])
            self.client.open(url+'/?avvio=wrong',timeout=5).read()
            self.assertFalse(self.read(url+'/api/session')['authenticated'])
            self.bootstrap(url)
            state=self.read(url+'/api/session')
            self.assertTrue(state['authenticated']);self.assertNotEqual(state['csrf'],csrf)


if __name__=='__main__':unittest.main()
