import copy
import json
import tempfile
import unittest
from pathlib import Path
from app.demo import DemoEngine
from app.service import Service


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.engine=DemoEngine()
        self.s=Service(self.engine,self.root/'data',self.root/'media',self.root/'backups',True)

    def tearDown(self):
        self.tmp.cleanup()

    def command(self,action,**data):
        return self.s.command(action,dict(revision=self.s.view['revision'],**data))

    def test_edit_add_delete_keep_existing_positions(self):
        before=copy.deepcopy(self.s.view['positions'])
        self.command('edit',id='p0',first='Gianni',surname='Rossi',gender=2)
        coordinates=lambda positions:{i:{k:p[k] for k in ('x','y','locked')} for i,p in positions.items()}
        self.assertEqual(coordinates(before),coordinates(self.s.view['positions']))
        before=copy.deepcopy(self.s.view['positions'])
        self.command('add',first='Nuovo',relation='child',target='p6',child_type='birth')
        for identifier,pos in before.items():
            self.assertEqual(pos,self.s.view['positions'][identifier])
        added=next(i for i in self.s.view['positions'] if i not in before)
        self.command('delete',id=added,confirm=True)
        self.assertEqual(before,self.s.view['positions'])

    def test_repeated_layout_and_font_change_are_stable(self):
        self.command('layout')
        before=copy.deepcopy(self.s.view['positions'])
        self.command('layout')
        self.assertEqual(before,self.s.view['positions'])
        self.command('layout',layout={'font_size':28})
        after=self.s.view['positions']
        self.assertGreater(after['p0']['w'],before['p0']['w'])
        self.assertEqual(sorted(before,key=lambda i:before[i]['x']),sorted(after,key=lambda i:after[i]['x']))
        self.command('undo')
        self.assertEqual(before,self.s.view['positions'])
        self.command('redo')
        self.assertIn('font-size="28.0"',self.s.state()['card_text']['p0'])

    def test_add_family_undo_redo(self):
        initial=self.s.state()
        after=self.command('add',first='Ada',surname='Rossi',relation='child',target='p6',child_type='adopted')
        self.assertEqual(len(after['people']),9)
        self.assertIn([2,6],[r for f in after['families'] for r in f['relations'].values()])
        self.command('undo')
        self.assertEqual(self.engine.state()['people'],initial['people'])
        self.command('redo')
        self.assertEqual(len(self.engine.state()['people']),9)

    def test_mixed_history_restores_positions_and_genealogy(self):
        initial=copy.deepcopy(self.s.view['positions'])
        self.command('move',id='p0',x=-500,y=-300)
        self.command('add',first='Ada',relation='independent')
        self.command('undo')
        self.assertEqual(len(self.engine.state()['people']),8)
        self.assertEqual(self.s.view['positions']['p0']['x'],-500)
        self.command('undo')
        self.assertEqual(self.s.view['positions'],initial)
        self.command('redo')
        self.command('redo')
        self.assertEqual(len(self.engine.state()['people']),9)

    def test_edit_name_and_undo(self):
        self.command('edit',id='p0',first='Gianni',surname='Rossi',gender=1)
        self.assertEqual(self.engine.state()['people'][0]['first'],'Gianni')
        self.command('undo')
        self.assertEqual(self.engine.state()['people'][0]['first'],'Giovanni')

    def test_direction_settings_undo_and_reopen(self):
        before=copy.deepcopy(self.s.view)
        self.command('layout',layout=dict(direction='horizontal',siblings=3,stagger=True),release_locked=True)
        self.assertEqual(self.s.state()['layout']['direction'],'horizontal')
        self.assertIn(' Q',self.s.state()['connections_svg'])
        self.command('undo')
        self.assertEqual(self.s.view['layout'],before['layout'])
        self.assertEqual(self.s.view['positions'],before['positions'])
        self.command('redo')
        reopened=Service(self.engine,self.root/'data',self.root/'media',self.root/'backups',True)
        self.assertEqual(reopened.view['layout']['direction'],'horizontal')

    def test_paper_optimization_chooses_most_legible_sibling_band(self):
        from test_composition import large_family
        from app.geometry import arrange,sheet
        self.engine.data=large_family()
        self.s.refresh()
        config=dict(format='custom',unit='mm',width=125,height=256)
        before=copy.deepcopy(self.s.view['positions'])
        self.command('layout',paper=config,release_locked=True)
        score=sheet(config,self.s.view['positions'])['scale']
        for count in (2,3,4,6,8):
            candidate,_=arrange(self.engine.state(),{},dict(direction='vertical',siblings=count,stagger=True))
            self.assertGreaterEqual(score+1e-9,sheet(config,candidate)['scale'])
        self.command('undo')
        self.assertEqual(self.s.view['positions'],before)

    def test_stale_tab_rejected_before_mutation(self):
        self.command('layout')
        with self.assertRaises(ValueError):
            self.s.command('add',dict(revision=0,first='Wrong'))
        self.assertEqual(len(self.engine.state()['people']),8)

    def test_failed_add_is_atomic(self):
        initial=self.engine.state()
        with self.assertRaises(ValueError):
            self.command('add',first='Ada',relation='parent',target='p4',family='f0')
        self.assertEqual(self.engine.state(),initial)
        self.assertFalse(self.s.past)

    def test_branch_translation_preserves_internal_distances(self):
        old=copy.deepcopy(self.s.view['positions'])
        self.command('branch',id='p4',dx=0,dy=900)
        for i in ['p4','p6','p7']:
            self.assertEqual(self.s.view['positions'][i]['y'],old[i]['y']+900)
            self.assertTrue(self.s.view['positions'][i]['locked'])
        self.assertEqual(self.s.view['positions']['p5'],old['p5'])

    def test_workspace_persisted_and_export_overflow_blocked(self):
        self.command('move',id='p0',x=-500,y=-500)
        saved=json.loads((self.root/'data/workspace.json').read_text())
        self.assertEqual(saved['positions']['p0']['x'],-500)
        with self.assertRaises(ValueError):
            self.s.print_tree(dict(format='A4',mode='scale',scale=1000),'svg')
