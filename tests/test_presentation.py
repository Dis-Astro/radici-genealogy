"""Read-only family/overview presentation, authenticated and tree-bound."""
import concurrent.futures
import copy
import http.client
import importlib.util
import json
import tempfile
import threading
import unittest
from pathlib import Path

from app.demo import DemoEngine
from app.engine import Engine
from app.geometry import card_size
from app.portable_rpc import OwnerProxy
from app.server import build_server
from app.service import Service
from app.workspace import Workspace

HAS_GRAMPS = importlib.util.find_spec('gramps') is not None
VIEW_KEYS = {'people','families','positions','layout','card_text','connections_svg','family_colors','total_people','view_mode','focus_id'}


def person(identifier, gender=2):
    return dict(id=identifier, gramps_id='I'+identifier, first='Nome '+identifier, surname='Rossi', years='', gender=gender)


def family(identifier, parents, children):
    return dict(id=identifier, gramps_id='F'+identifier, parents=parents, children=children,
                parent_roles={p:i for i,p in enumerate(parents)}, relations={c:[1,1] for c in children})


def fixture():
    return dict(people=[person(p) for p in ['gpa','gma','focus','sibling','partner1','partner2','child1','child2','grandchild','isolated','childpartner']],
                families=[family('parents',['gpa','gma'],['focus','sibling']),
                          family('first',['focus','partner1'],['child1']),
                          family('second',['focus','partner2'],['child2']),
                          family('grandchildren',['child1','childpartner'],['grandchild'])])


class PresentationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.engine=DemoEngine(empty=True);self.engine.data=fixture()
        self.service=Service(self.engine,self.root/'data',self.root/'media',self.root/'backups',True)

    def tearDown(self): self.tmp.cleanup()

    def test_family_contains_only_focus_parents_partners_and_direct_children(self):
        result=self.service.presentation(dict(mode='family',id='focus'))
        self.assertEqual(set(result),VIEW_KEYS)
        self.assertEqual({p['id'] for p in result['people']},{'gpa','gma','focus','partner1','partner2','child1','child2'})
        self.assertEqual({f['id'] for f in result['families']},{'parents','first','second'})
        parent_family=next(f for f in result['families'] if f['id']=='parents')
        self.assertEqual(parent_family['children'],['focus'])
        self.assertEqual(set(parent_family['relations']),{'focus'})
        self.assertEqual((parent_family['visible_children'],parent_family['total_children']),(1,2))
        self.assertTrue(parent_family['partial'])
        self.assertFalse(next(f for f in result['families'] if f['id']=='first')['partial'])
        self.assertEqual(result['total_people'],11);self.assertEqual(result['focus_id'],'focus')
        self.assertEqual(len(result['positions']),7)
        self.assertEqual(len({(p['w'],p['h']) for p in result['positions'].values()}),1)
        self.assertFalse(result['layout']['stagger'])
        self.assertTrue(result['layout']['reading'])
        self.assertEqual(result['layout']['font_type'],'classic')
        expected=card_size(self.engine.state(),22,'classic')
        self.assertTrue(all((p['w'],p['h'])==expected for p in result['positions'].values()))
        self.assertTrue(all('<path' in value for value in result['card_text'].values()))
        self.assertFalse(any(p['locked'] for p in result['positions'].values()))
        self.assertEqual(set(result['card_text']),set(result['positions']))

    def test_focusing_child_includes_their_own_partner_and_child_not_siblings_or_grandparents(self):
        result=self.service.presentation(dict(mode='family',id='child1',direction='horizontal',siblings=3,font_size=28))
        self.assertEqual({p['id'] for p in result['people']},{'child1','focus','partner1','childpartner','grandchild'})
        self.assertEqual({f['id'] for f in result['families']},{'first','grandchildren'})
        self.assertEqual(result['layout']['direction'],'horizontal')
        self.assertEqual(result['layout']['font_size'],28)

    def test_overview_keeps_both_unions_and_isolated_person_without_fake_edges(self):
        result=self.service.presentation(dict(mode='overview',id='focus'))
        self.assertEqual({p['id'] for p in result['people']},{p['id'] for p in fixture()['people']})
        self.assertEqual(len(result['families']),4);self.assertEqual(len(result['positions']),11)
        self.assertTrue(all(not f['partial'] for f in result['families']))
        for f in result['families']:
            self.assertNotIn('isolated',f['parents']+f['children'])
            self.assertEqual(f['visible_children'],f['total_children'])
        result['people'][0]['first']='Changed client payload'
        self.assertNotEqual(self.engine.state()['people'][0]['first'],'Changed client payload')

    def test_isolated_empty_and_no_focus_contexts_are_graceful(self):
        alone=self.service.presentation(dict(mode='family',id='isolated'))
        self.assertEqual([p['id'] for p in alone['people']],['isolated'])
        self.assertEqual(alone['families'],[]);self.assertEqual(alone['connections_svg'],'')
        no_focus=self.service.presentation(dict(mode='family'))
        self.assertEqual(no_focus['people'],[]);self.assertEqual(no_focus['total_people'],11)
        self.assertIsNone(no_focus['focus_id'])
        empty=Service(DemoEngine(empty=True),self.root/'empty',self.root/'empty-media',self.root/'empty-backups',True)
        for mode in ('family','overview'):
            result=empty.presentation(dict(mode=mode))
            self.assertEqual(result['people'],[]);self.assertEqual(result['families'],[])
            self.assertEqual(result['positions'],{});self.assertEqual(result['total_people'],0)
            self.assertEqual(result['connections_svg'],'');self.assertIsNone(result['focus_id'])

    def test_presentation_never_modifies_data_saved_positions_files_or_history(self):
        self.service.command('edit',dict(revision=0,id='focus',first='Prima modifica',surname='Rossi',gender=2))
        self.service.command('edit',dict(revision=1,id='focus',first='Seconda modifica',surname='Rossi',gender=2))
        self.service.command('undo',dict(revision=2))
        self.assertTrue(self.service.past);self.assertTrue(self.service.future)
        self.service.view['positions']['focus']['locked']=True;self.service.refresh()
        before=copy.deepcopy((self.engine.state(),self.service.view,self.service.past,self.service.future))
        files={p:(p.read_bytes(),p.stat().st_mtime_ns) for p in self.root.rglob('*') if p.is_file()}
        for mode in ('family','overview'):
            for direction in ('vertical','horizontal'):
                self.service.presentation(dict(mode=mode,id='focus',direction=direction,font_size=26))
        self.assertEqual((self.engine.state(),self.service.view,self.service.past,self.service.future),before)
        self.assertEqual({p:(p.read_bytes(),p.stat().st_mtime_ns) for p in files},files)

    def test_invalid_options_and_unknown_focus_leave_source_untouched(self):
        before=copy.deepcopy((self.engine.state(),self.service.view,self.service.past,self.service.future))
        for invalid in ({'mode':'all'},{'direction':'auto'},{'font_size':0},{'font_size':float('nan')},{'siblings':4.5},{'id':'missing'},
                        {'viewport_width':99},{'viewport_height':10001},{'viewport_width':float('nan')}):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):self.service.presentation({'mode':'family','id':'focus',**invalid})
        self.assertEqual((self.engine.state(),self.service.view,self.service.past,self.service.future),before)

    def test_family_chooses_sibling_rows_for_actual_viewport_without_changing_direction_or_source(self):
        for index in range(8):
            identifier='extra'+str(index)
            self.engine.data['people'].append(person(identifier))
            self.engine.data['families'][1]['children'].append(identifier)
            self.engine.data['families'][1]['relations'][identifier]=[1,1]
        self.service.refresh()
        before=copy.deepcopy((self.engine.state(),self.service.view,self.service.past,self.service.future))
        def score(result,width,height):
            rectangles=list(result['positions'].values())
            w=max(p['x']+p['w'] for p in rectangles)-min(p['x'] for p in rectangles)
            h=max(p['y']+p['h'] for p in rectangles)-min(p['y'] for p in rectangles)
            return min((width-32)/w,(height-48)/h)
        for width,height,direction in ((720,300,'vertical'),(360,900,'vertical'),(900,400,'horizontal')):
            with self.subTest(width=width,height=height,direction=direction):
                request=dict(mode='family',id='focus',direction=direction,siblings=4,font_size=22)
                adaptive=self.service.presentation({**request,'viewport_width':width,'viewport_height':height})
                scores=[score(self.service.presentation({**request,'siblings':capacity}),width,height) for capacity in (2,3,4,5,6,8)]
                self.assertAlmostEqual(score(adaptive,width,height),max(scores),places=9)
                self.assertEqual(adaptive['layout']['direction'],direction)
        self.assertEqual((self.engine.state(),self.service.view,self.service.past,self.service.future),before)

    def test_overview_keeps_requested_rows_despite_viewport(self):
        request=dict(mode='overview',id='focus',siblings=3)
        normal=self.service.presentation(request)
        resized=self.service.presentation({**request,'viewport_width':360,'viewport_height':300})
        self.assertEqual(normal['positions'],resized['positions'])
        self.assertEqual(resized['layout']['siblings'],3)
        self.assertFalse(resized['layout']['reading'])

    def test_card_measure_is_identical_across_family_overview_and_isolated_contexts(self):
        # A long name elsewhere still determines the common card size when
        # looking at an isolated person or a small family context.
        self.engine.data['people'][0].update(first='Maria Giuseppina Anna',surname='Di Cristofaro Canzanese',years='1920 – 2000')
        expected=card_size(self.engine.state(),22,'classic')
        for mode,identifier in (('family','focus'),('family','child1'),('family','gpa'),('family','isolated'),('overview','focus')):
            with self.subTest(mode=mode,identifier=identifier):
                result=self.service.presentation(dict(mode=mode,id=identifier,font_size=22,_card_dimensions=(1,1)))
                self.assertEqual({(p['w'],p['h']) for p in result['positions'].values()},{expected})
                self.assertEqual(tuple(result['layout']['_card_dimensions']),expected)

    def test_owner_proxy_marshals_presentation_on_owner_and_rechecks_tree_binding(self):
        proxy=OwnerProxy();owner=threading.get_ident();calls=[]
        class Target:
            active='original'
            def check_tree(self,identifier):
                if identifier!=self.active:raise ValueError('tree changed')
            def presentation(self,data):calls.append(threading.get_ident());return {'mode':data['mode']}
        proxy.target=Target()
        with concurrent.futures.ThreadPoolExecutor(1) as pool:
            future=pool.submit(proxy.presentation,dict(mode='overview'))
            while not future.done():proxy.run_one(.01)
            self.assertEqual(future.result(),{'mode':'overview'});self.assertEqual(calls,[owner])
            checked,resume=threading.Event(),threading.Event()
            def delayed():
                proxy.check_tree('original');checked.set();resume.wait(2)
                return proxy.presentation(dict(mode='family',tree_id='original',id='focus'))
            future=pool.submit(delayed)
            while not checked.is_set():proxy.run_one(.01)
            proxy.target.active='another';resume.set()
            while not future.done():proxy.run_one(.01)
            with self.assertRaisesRegex(ValueError,'tree changed'):future.result()
            self.assertEqual(calls,[owner])


class PresentationHttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();root=Path(self.tmp.name)
        self.workspace=Workspace(root/'data',root/'media',root/'backups',True)
        self.server=build_server(self.workspace,'presentation-password',('127.0.0.1',0))
        self.thread=threading.Thread(target=self.server.serve_forever,kwargs={'poll_interval':.02},daemon=True);self.thread.start()
        self.cookie=None;self.csrf=None

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.workspace.close();self.tmp.cleanup()

    def request(self,path,data,headers=None):
        connection=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=5)
        h={'Content-Type':'application/json'}
        if self.cookie:h['Cookie']=self.cookie
        if self.csrf:h['X-CSRF-Token']=self.csrf
        h.update(headers or {})
        try:
            connection.request('POST',path,json.dumps(data),h);response=connection.getresponse()
            return response.status,dict(response.headers),json.loads(response.read())
        finally:connection.close()

    def login(self):
        status,headers,data=self.request('/api/login',dict(password='presentation-password'))
        self.assertEqual(status,200);self.cookie=headers['Set-Cookie'].split(';')[0];self.csrf=data['csrf']

    def test_view_requires_authentication_csrf_same_origin_and_current_tree(self):
        payload=dict(tree_id='original',mode='family',id='p6')
        self.assertEqual(self.request('/api/view',payload)[0],401)
        self.login()
        self.assertEqual(self.request('/api/view',payload,{'X-CSRF-Token':''})[0],403)
        self.assertEqual(self.request('/api/view',payload,{'Origin':'https://other.invalid'})[0],403)
        status,_,result=self.request('/api/view',payload)
        self.assertEqual(status,200);self.assertEqual(set(result),VIEW_KEYS)
        self.assertEqual({p['id'] for p in result['people']},{'p4','p5','p6'})
        self.workspace.create('Other')
        self.assertEqual(self.request('/api/view',payload)[0],400)
        current=dict(tree_id=self.workspace.index['active'],mode='overview')
        self.assertEqual(self.request('/api/view',current)[2]['people'],[])


@unittest.skipUnless(HAS_GRAMPS,'Run with official Gramps 6.0.8 runtime')
class NativePresentationTests(unittest.TestCase):
    def test_native_two_unions_data_and_real_undo_are_unchanged_by_both_views(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);engine=Engine(root/'data/tree')
            try:
                grandparent=engine.add(dict(first='Nonna',birth='1920'))
                focus=engine.add(dict(first='Anna',relation='child',target=grandparent,child_type='birth'))
                engine.add(dict(first='Fratello',relation='child',target=grandparent))
                first=engine.add(dict(first='Mario',relation='partner',target=focus))
                second=engine.add(dict(first='Luca',relation='partner',target=focus))
                state=engine.state()
                one=next(f['id'] for f in state['families'] if set(f['parents'])=={focus,first})
                two=next(f['id'] for f in state['families'] if set(f['parents'])=={focus,second})
                child=engine.add(dict(first='Elisa',relation='child',target=focus,family=one))
                engine.add(dict(first='Paolo',relation='child',target=focus,family=two))
                grandchild=engine.add(dict(first='Nipote',relation='child',target=child))
                isolated=engine.add(dict(first='Isolata'))
                service=Service(engine,root/'data',root/'media',root/'backups')
                service.command('edit',dict(revision=0,id=focus,first='Anna Maria',surname='',gender=2))
                before=copy.deepcopy((engine.state(),service.view,service.past,service.future))
                saved=(service.file.read_bytes(),service.file.stat().st_mtime_ns)
                count_events=engine.db.get_number_of_events()
                family_view=service.presentation(dict(mode='family',id=focus))
                self.assertEqual(len(family_view['people']),6)
                self.assertNotIn(grandchild,{p['id'] for p in family_view['people']})
                self.assertNotIn(isolated,{p['id'] for p in family_view['people']})
                overview=service.presentation(dict(mode='overview',id=focus,direction='horizontal'))
                self.assertEqual(len(overview['people']),9)
                self.assertEqual((engine.state(),service.view,service.past,service.future),before)
                self.assertEqual((service.file.read_bytes(),service.file.stat().st_mtime_ns),saved)
                self.assertEqual(engine.db.get_number_of_events(),count_events)
                service.command('undo',dict(revision=service.view['revision']))
                self.assertEqual(next(p for p in engine.state()['people'] if p['id']==focus)['first'],'Anna')
            finally:engine.close()
