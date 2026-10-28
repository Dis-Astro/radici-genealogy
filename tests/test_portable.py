import concurrent.futures
import http.client
import json
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from app.portable import complete_backup, BackupCancelled
from app.portable_rpc import OwnerProxy, ResponsiveServer
from app.server import build_server


class PortableTests(unittest.TestCase):
    def test_idle_browser_sockets_do_not_block_health_or_static_files(self):
        proxy=OwnerProxy()
        server=build_server(proxy,'portable-test-password',('127.0.0.1',0),
                            server_type=ResponsiveServer,portable_control=proxy,bootstrap_token='control')
        thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.02},daemon=True)
        thread.start()
        idle=[socket.create_connection(server.server_address,timeout=2) for _ in range(6)]
        try:
            for route in ['/health','/app.js','/api/portable/status']:
                c=http.client.HTTPConnection(*server.server_address,timeout=1)
                c.request('GET',route,headers={'X-Radici-Control':'control'})
                r=c.getresponse();self.assertEqual(r.status,200);self.assertTrue(r.read());c.close()
            c=http.client.HTTPConnection(*server.server_address,timeout=1)
            c.request('POST','/api/portable/control','{"action":"shutdown"}',
                      {'Content-Type':'application/json','X-Radici-Control':'wrong'})
            r=c.getresponse();self.assertEqual(r.status,403);r.read();c.close()
            self.assertFalse(proxy.stop.is_set())
        finally:
            for s in idle:s.close()
            server.shutdown();server.server_close();thread.join()

    def test_native_calls_serialize_on_owner_and_recheck_bound_tree(self):
        proxy=OwnerProxy();owner=threading.get_ident();calls=[]
        class Target:
            active='one'
            def state(self):calls.append(threading.get_ident());return self.active
            def check_tree(self,identifier):
                if identifier!=self.active:raise ValueError('tree changed')
        proxy.target=Target()
        with concurrent.futures.ThreadPoolExecutor(4) as pool:
            futures=[pool.submit(proxy.state) for _ in range(4)]
            while not all(f.done() for f in futures):proxy.run_one(.01)
            self.assertEqual([f.result() for f in futures],['one']*4)
            self.assertEqual(calls,[owner]*4)
            checked=threading.Event();resume=threading.Event()
            def late_request():
                proxy.check_tree('one');checked.set();resume.wait(2);return proxy.state()
            f=pool.submit(late_request)
            while not checked.is_set():proxy.run_one(.01)
            proxy.target.active='two';resume.set()
            while not f.done():proxy.run_one(.01)
            with self.assertRaisesRegex(ValueError,'tree changed'):f.result()

    def test_unchanged_signature_skips_backup_but_changes_trigger_it(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for name in ['Dati','Foto','Backup']:(root/name).mkdir()
            (root/'Dati/trees.json').write_text('{}')
            exported=[]
            engine=SimpleNamespace(export=lambda:exported.append(True) or b'gramps-export')
            service=SimpleNamespace(engine=engine,view={})
            workspace=SimpleNamespace(index={'trees':[{'id':'one'}]},_open=lambda identifier:service)
            first=complete_backup(workspace,root)
            self.assertEqual(complete_backup(workspace,root,force=False),first)
            self.assertEqual(len(exported),1)
            (root/'Foto/new.jpg').write_bytes(b'photo')
            self.assertNotEqual(complete_backup(workspace,root,force=False),first)
            self.assertEqual(len(exported),2)
            (root/'Backup/ultima-copia.json').write_text('invalid')
            complete_backup(workspace,root,force=False)
            self.assertEqual(len(exported),3)

    def test_cancelling_manual_backup_preserves_previous_copy_and_cleans_partial(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for name in ['Dati','Foto','Backup']:(root/name).mkdir()
            (root/'Dati/trees.json').write_text('{}')
            service=SimpleNamespace(engine=SimpleNamespace(export=lambda:b'gramps-export'),view={})
            workspace=SimpleNamespace(index={'trees':[{'id':'one'}]},_open=lambda identifier:service)
            previous=complete_backup(workspace,root)
            before=(root/'Backup'/previous).read_bytes()
            (root/'Foto/large.jpg').write_bytes(b'X'*(1024*1024))
            checks=[]
            def cancelled():checks.append(True);return len(checks)>=5
            with self.assertRaises(BackupCancelled):complete_backup(workspace,root,cancelled=cancelled)
            self.assertEqual((root/'Backup'/previous).read_bytes(),before)
            self.assertEqual(list((root/'Backup').glob('*.partial')),[])
            self.assertEqual(len(list((root/'Backup').glob('*.zip'))),1)
