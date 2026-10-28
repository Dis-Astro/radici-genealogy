import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path
from app.demo import DemoEngine
from app.service import Service
from app.server import build_server


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        root=Path(self.tmp.name)
        self.s=Service(DemoEngine(),root/'data',root/'media',root/'backup',True)
        self.server=build_server(self.s,'test-password-2026',('127.0.0.1',0))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.cookie=None
        self.csrf=None

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.tmp.cleanup()

    def request(self,path,data=None,headers=None):
        connection=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=5)
        h={'Content-Type':'application/json'}
        if self.cookie:h['Cookie']=self.cookie
        if self.csrf:h['X-CSRF-Token']=self.csrf
        h.update(headers or {})
        connection.request('POST' if data is not None else 'GET',path,json.dumps(data) if data is not None else None,h)
        response=connection.getresponse()
        body=response.read()
        result=response.status,dict(response.headers),body
        connection.close()
        return result

    def login(self):
        code,h,b=self.request('/api/login',{'password':'test-password-2026'})
        self.assertEqual(code,200)
        self.cookie=h['Set-Cookie'].split(';')[0]
        self.csrf=json.loads(b)['csrf']

    def test_authentication_and_cookie_policy(self):
        self.assertEqual(self.request('/api/state')[0],401)
        code,h,b=self.request('/api/login',{'password':'test-password-2026'})
        self.assertIn('HttpOnly',h['Set-Cookie'])
        self.assertIn('SameSite=Strict',h['Set-Cookie'])
        self.login()
        code,h,b=self.request('/api/state')
        self.assertEqual(code,200)
        self.assertEqual(len(json.loads(b)['people']),8)
        self.assertIn("frame-ancestors 'none'",h['Content-Security-Policy'])

    def test_csrf_origin_and_host_protection(self):
        self.login()
        for _ in range(5):
            for headers in ({'X-CSRF-Token':''},{'Origin':'https://evil.example'},{'Host':'evil.example'}):
                code, _, body = self.request('/api/command',{'action':'layout','revision':0},headers)
                self.assertEqual(code,403)
                self.assertIn('error',json.loads(body))
        self.assertEqual(self.s.state()['revision'],0)
        self.assertEqual(self.request('/api/state',headers={'Host':'evil.example'})[0],403)

    def test_no_path_traversal_or_unauthenticated_export(self):
        self.assertEqual(self.request('/../LICENSE')[0],404)
        self.assertEqual(self.request('/api/export')[0],401)

    def test_state_mutation_and_print_preview_over_http(self):
        self.login()
        code,h,b=self.request('/api/command',{'action':'add','revision':0,'first':'Ada','relation':'child','target':'p6'})
        self.assertEqual(code,200)
        self.assertEqual(len(json.loads(b)['people']),9)
        code,h,b=self.request('/api/print',{'format':'custom','unit':'cm','width':12.5,'height':25.6,'margin':1,'safety':.3})
        self.assertEqual(code,200)
        self.assertEqual(json.loads(b)['sheet']['width'],125)

    def test_login_throttle_and_logout(self):
        for i in range(10):
            self.assertEqual(self.request('/api/login',{'password':'wrong'})[0],401)
        self.assertEqual(self.request('/api/login',{'password':'wrong'})[0],429)

    def test_logout_invalidates_server_session(self):
        self.login()
        self.assertEqual(self.request('/api/logout',{})[0],200)
        self.assertEqual(self.request('/api/state')[0],401)

    def test_tree_creation_switch_and_confirmed_deletion_over_http(self):
        from app.workspace import Workspace
        self.server.shutdown();self.server.server_close();self.thread.join()
        root=Path(self.tmp.name)/'workspace'
        workspace=Workspace(root/'data',root/'media',root/'backups',True)
        self.addCleanup(workspace.close)
        self.server=build_server(workspace,'test-password-2026',('127.0.0.1',0))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.login()
        code,h,b=self.request('/api/trees/new',{'name':'Famiglia nuova'})
        self.assertEqual(code,200)
        created=json.loads(b);identifier=created['tree_id']
        self.assertEqual(created['people'],[])
        code,h,b=self.request('/api/command',dict(tree_id=identifier,revision=0,action='add',first='Ada'))
        self.assertEqual(code,200)
        person=json.loads(b)['people'][0]['id']
        self.assertEqual(self.request('/api/command',dict(tree_id=identifier,revision=1,action='delete',id=person))[0],400)
        code,h,b=self.request('/api/command',dict(tree_id=identifier,revision=1,action='delete',id=person,confirm=True))
        self.assertEqual(code,200);self.assertEqual(json.loads(b)['people'],[])
        code,h,b=self.request('/api/trees/open',{'id':'original'})
        self.assertEqual(code,200);self.assertEqual(len(json.loads(b)['people']),8)
        self.assertEqual(self.request('/api/command',dict(tree_id=identifier,revision=0,action='add',first='Wrong'))[0],400)
