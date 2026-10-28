import copy
import tempfile
import unittest
from pathlib import Path
from app.workspace import Workspace


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.w=Workspace(self.root/'data',self.root/'media',self.root/'backups',True)

    def tearDown(self):
        self.w.close();self.tmp.cleanup()

    def command(self,action,**data):
        return self.w.command(action,dict(tree_id=self.w.state()['tree_id'],revision=self.w.state()['revision'],**data))

    def test_new_tree_is_empty_and_old_tree_is_preserved(self):
        original=self.w.state()
        created=self.w.create('Famiglia di mia madre')
        self.assertEqual(created['people'],[])
        self.assertEqual(len(created['trees']),2)
        self.command('add',first='Ada',relation='independent')
        self.w.switch(original['tree_id'])
        self.assertEqual(self.w.state()['people'],original['people'])
        self.w.switch(created['tree_id'])
        self.assertEqual(self.w.state()['people'][0]['first'],'Ada')

    def test_separate_history_and_workspace_locations(self):
        original=self.w.index['active']
        self.command('edit',id='p0',first='Gianni',surname='Rossi',gender=1)
        self.w.create('Secondo albero')
        self.assertFalse(self.w.state()['undo'])
        self.assertNotEqual(self.w.current.media,self.w.services[original].media)
        self.assertIn('_radici_trees',self.w.services[original].excluded_media_dirs)
        self.command('add',first='Ada')
        self.w.switch(original)
        self.command('undo')
        self.assertEqual(self.w.state()['people'][0]['first'],'Giovanni')

    def test_cross_tree_stale_request_cannot_delete_person(self):
        original=self.w.state()
        self.w.create('Nuovo')
        with self.assertRaisesRegex(ValueError,'albero aperto'):
            self.w.command('delete',dict(tree_id=original['tree_id'],revision=0,id='p0',confirm=True))
        self.w.switch(original['tree_id'])
        self.assertEqual(len(self.w.state()['people']),8)

    def test_invalid_or_duplicate_names_and_unknown_ids_do_not_switch(self):
        for name in ['', ' '*3, 'x'*101,'IL MIO ALBERO']:
            with self.assertRaises(ValueError):self.w.create(name)
        with self.assertRaises(ValueError):self.w.switch('../../other')
        self.assertEqual(self.w.index['active'],'original')
        self.assertEqual(len(self.w.index['trees']),1)

    def test_catalog_and_layout_survive_reopening(self):
        created=self.w.create('Secondo')
        self.command('layout',layout={'direction':'horizontal'})
        self.w.close()
        self.w=Workspace(self.root/'data',self.root/'media',self.root/'backups',True)
        self.assertEqual(self.w.state()['tree_id'],created['tree_id'])
        self.assertEqual(self.w.state()['layout']['direction'],'horizontal')

    def test_demo_people_and_family_links_survive_restart(self):
        tree=self.w.create('Persistente')['tree_id']
        self.command('add',first='Ada',surname='Rossi',relation='independent')
        parent=self.w.state()['people'][0]['id']
        self.command('add',first='Lina',surname='Rossi',relation='child',target=parent,child_type='birth')
        before=self.w.state()
        self.w.close()
        self.w=Workspace(self.root/'data',self.root/'media',self.root/'backups',True)
        after=self.w.state()
        self.assertEqual(after['tree_id'],tree)
        self.assertEqual(after['people'],before['people'])
        self.assertEqual(after['families'],before['families'])
        self.assertEqual(after['positions'],before['positions'])
        self.command('delete',id=parent,confirm=True)
        self.command('undo')
        self.w.close()
        self.w=Workspace(self.root/'data',self.root/'media',self.root/'backups',True)
        self.assertEqual(self.w.state()['people'],before['people'])

    def test_delete_requires_confirmation_and_undo_recovers_links(self):
        before=self.w.state()
        with self.assertRaises(ValueError):self.command('delete',id='p4')
        after=self.command('delete',id='p4',confirm=True)
        self.assertEqual(len(after['people']),7)
        self.assertFalse(any('p4' in f['parents']+f['children'] for f in after['families']))
        self.assertTrue(any(p['id']=='p6' for p in after['people']))
        self.command('undo')
        self.assertEqual(self.w.state()['people'],before['people'])
        self.assertEqual(self.w.state()['families'],before['families'])

    def test_real_mode_delete_stops_if_backup_fails(self):
        self.w.current.demo=False
        def fail():raise ValueError('Backup non riuscito')
        self.w.current.backup=fail
        with self.assertRaisesRegex(ValueError,'Backup non riuscito'):
            self.command('delete',id='p4',confirm=True)
        self.assertEqual(len(self.w.state()['people']),8)
