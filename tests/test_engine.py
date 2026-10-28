"""Integration suite: runs ONLY against real upstream 6.0.8, never a mock."""
import importlib.util
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from app.engine import Engine, validate_xml
from app.service import Service

HAS_GRAMPS = importlib.util.find_spec('gramps') is not None


class XmlValidationTests(unittest.TestCase):
    def test_rejects_entities_wrong_format_and_expansion(self):
        for xml in [b'<wrong/>',b'<!DOCTYPE x [<!ENTITY x "bad">]><x/>',b'not xml']:
            with self.assertRaises(Exception):
                validate_xml(xml)


@unittest.skipUnless(HAS_GRAMPS,'Gramps + GI non disponibili sul sistema host: eseguire in Docker')
class OfficialEngineTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.engine=Engine(self.root/'data/tree')

    def tearDown(self):
        if self.engine.db.is_open():self.engine.close()
        self.tmp.cleanup()

    def test_relationships_reciprocal_and_undo_atomic(self):
        p=self.engine.add(dict(first='Anna',surname='Rossi',birth='1948'))
        a=self.engine.add(dict(first='Maria',relation='parent',target=p,child_type='adopted'))
        state=self.engine.state()
        family=state['families'][0]
        self.assertEqual(family['relations'][p],[2,6])
        f=self.engine.db.get_family_from_handle(family['id'])
        self.assertIn(f.handle,self.engine.db.get_person_from_handle(p).get_parent_family_handle_list())
        self.assertIn(f.handle,self.engine.db.get_person_from_handle(a).get_family_handle_list())
        self.engine.undo()
        self.assertEqual(len(self.engine.state()['people']),1)
        self.assertEqual(len(self.engine.state()['families']),0)
        self.engine.redo()
        self.assertEqual(len(self.engine.state()['people']),2)
        with self.assertRaises(ValueError):
            self.engine.add(dict(first='Occupied',relation='parent',target=p,family=f.handle,slot='father'))
        self.assertEqual(len(self.engine.state()['people']),2)
        self.engine.add(dict(first='Secondo',gender=1,relation='parent',target=p,family=f.handle,slot='mother',child_type='birth'))
        self.assertEqual(self.engine.state()['families'][0]['relations'][p],[2,1])

    def test_roundtrip_preserves_notes_citations_places_media(self):
        from gramps.gen.db import DbTxn
        from gramps.gen.lib import Note, Source, Citation, Place, Media
        person=self.engine.add(dict(first='Élisa',surname='D’Angelo',birth='1948'))
        with DbTxn('Extra objects',self.engine.db) as txn:
            note=Note();note.set('Nota da conservare');self.engine.db.add_note(note,txn)
            source=Source();source.set_title('Registro originale');self.engine.db.add_source(source,txn)
            citation=Citation();citation.set_reference_handle(source.handle);self.engine.db.add_citation(citation,txn)
            place=Place();place.set_title('Roma');self.engine.db.add_place(place,txn)
            media=Media();media.set_path('famiglia/foto.jpg');self.engine.db.add_media(media,txn)
            p=self.engine.db.get_person_from_handle(person);p.add_note(note.handle);p.add_citation(citation.handle);self.engine.db.commit_person(p,txn)
        blob=self.engine.export()
        other=Engine(self.root/'other')
        try:
            other.import_empty(blob)
            self.assertEqual(other.db.get_number_of_people(),1)
            self.assertEqual(other.db.get_number_of_notes(),1)
            self.assertEqual(other.db.get_number_of_citations(),1)
            self.assertEqual(other.db.get_number_of_sources(),1)
            self.assertEqual(other.db.get_number_of_places(),1)
            self.assertEqual(other.db.get_number_of_media(),1)
            self.assertEqual(next(other.db.iter_notes()).get(),'Nota da conservare')
            self.assertEqual(next(other.db.iter_media()).get_path(),'famiglia/foto.jpg')
            self.assertEqual(other.state()['people'][0]['first'],'Élisa')
            self.assertEqual(len(next(other.db.iter_people()).get_citation_list()),1)
            self.assertEqual(other.state()['people'][0]['years'],'1948')
        finally:other.close()

    def test_restart_and_mixed_service_undo(self):
        s=Service(self.engine,self.root/'data',self.root/'media',self.root/'backups')
        s.command('add',dict(revision=0,first='Anna',relation='independent'))
        s.command('undo',dict(revision=1))
        self.assertEqual(self.engine.db.get_number_of_people(),0)
        s.command('redo',dict(revision=2))
        self.engine.close();self.engine=Engine(self.root/'data/tree')
        self.assertEqual(self.engine.db.get_number_of_people(),1)

    def test_backup_and_restore_full_archive(self):
        from app.restore import restore
        self.engine.add(dict(first='Anna'))
        s=Service(self.engine,self.root/'data',self.root/'media',self.root/'backups')
        (self.root/'media/foto.jpg').write_bytes(b'example-image')
        archive=self.root/'backups'/s.backup()
        target,media=self.root/'restored',self.root/'restored-media'
        target.mkdir();media.mkdir()
        restore(archive,target,media)
        restored=Engine(target/'tree')
        try:self.assertEqual(restored.db.get_number_of_people(),1)
        finally:restored.close()
        self.assertEqual((media/'foto.jpg').read_bytes(),b'example-image')
        self.assertEqual(json.loads((target/'workspace.json').read_text())['positions'],s.view['positions'])

    def test_invalid_import_keeps_original_empty_archive(self):
        with self.assertRaises(Exception):self.engine.import_empty(b'<invalid/>')
        self.assertEqual(self.engine.db.get_number_of_people(),0)
        self.engine.add(dict(first='Still writable'))
        with self.assertRaises(ValueError):self.engine.import_empty(self.engine.export())

    def test_native_delete_cleans_references_and_undo_restores_family(self):
        p=self.engine.add(dict(first='Anna'))
        child=self.engine.add(dict(first='Ada',relation='child',target=p,child_type='birth'))
        before=self.engine.state()
        self.engine.delete({'id':p})
        self.assertEqual(self.engine.db.get_number_of_people(),1)
        self.assertEqual(self.engine.state()['people'][0]['id'],child)
        self.assertFalse(list(self.engine.db.find_backlink_handles(p)))
        self.engine.undo()
        self.assertEqual(self.engine.state(),before)

    def test_native_multi_tree_databases_are_isolated(self):
        from app.workspace import Workspace
        workspace=Workspace(self.root/'workspace',self.root/'media',self.root/'backups')
        try:
            original=workspace.state()['tree_id']
            workspace.command('add',dict(tree_id=original,revision=0,first='Anna'))
            new=workspace.create('Secondo albero')['tree_id']
            self.assertEqual(workspace.state()['people'],[])
            workspace.command('add',dict(tree_id=new,revision=0,first='Ada'))
            workspace.switch(original)
            self.assertEqual(workspace.state()['people'][0]['first'],'Anna')
            workspace.close()
            workspace=Workspace(self.root/'workspace',self.root/'media',self.root/'backups')
            self.assertEqual(workspace.state()['people'][0]['first'],'Anna')
            workspace.switch(new)
            self.assertEqual(workspace.state()['people'][0]['first'],'Ada')
        finally:workspace.close()
