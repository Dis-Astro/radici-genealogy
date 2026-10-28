"""Several unions and correcting links, against demo and official Gramps APIs."""
import importlib.util
import tempfile
import unittest
from pathlib import Path
from app.demo import DemoEngine
from app.engine import Engine

HAS_GRAMPS = importlib.util.find_spec('gramps') is not None


class RelationshipCases:
    def family(self, *parents):
        return next(f for f in self.engine.state()['families'] if set(f['parents']) == set(parents))

    def test_two_partners_keep_separate_unions_and_require_child_choice(self):
        anna = self.engine.add(dict(first='Anna', gender=0))
        first = self.engine.add(dict(first='Primo', gender=1, relation='partner', target=anna))
        second = self.engine.add(dict(first='Secondo', gender=1, relation='partner', target=anna))
        one, two = self.family(anna, first), self.family(anna, second)
        before = self.engine.state()
        with self.assertRaisesRegex(ValueError, 'più famiglie'):
            self.engine.add(dict(first='Bambino', relation='child', target=anna))
        self.assertEqual(self.engine.state(), before)
        child = self.engine.add(dict(first='Lina', relation='child', target=anna, family=two['id'], child_type='birth'))
        self.assertEqual(self.family(anna, first)['children'], [])
        self.assertEqual(self.family(anna, second)['children'], [child])
        self.assertEqual(self.family(anna, second)['relations'][child], [1, 1])
        self.assertNotEqual(one['id'], two['id'])

    def test_existing_partner_reuses_person_and_rejects_duplicate_union(self):
        anna = self.engine.add(dict(first='Anna', gender=0))
        mario = self.engine.add(dict(first='Mario', surname='Rossi', birth='1940', gender=1))
        before = self.engine.state()
        result = self.engine.add(dict(relation='partner', target=anna, existing_id=mario, first='DA NON USARE', birth='9999'))
        self.assertEqual(result, mario)
        self.assertEqual(len(self.engine.state()['people']), 2)
        self.assertEqual(next(p for p in self.engine.state()['people'] if p['id'] == mario)['first'], 'Mario')
        linked = self.engine.state()
        with self.assertRaises(ValueError):
            self.engine.add(dict(relation='partner', target=anna, existing_id=mario))
        self.assertEqual(self.engine.state(), linked)
        self.engine.undo(); self.assertEqual(self.engine.state(), before)
        self.engine.redo(); self.assertEqual(self.engine.state(), linked)

    def test_single_union_is_used_for_child_and_existing_children_are_not_duplicated(self):
        anna = self.engine.add(dict(first='Anna'))
        mario = self.engine.add(dict(first='Mario', relation='partner', target=anna))
        child = self.engine.add(dict(first='Elisa', birth='1960'))
        person = next(p for p in self.engine.state()['people'] if p['id'] == child)
        self.engine.add(dict(relation='child', target=anna, existing_id=child, child_type='adopted'))
        family = self.family(anna, mario)
        self.assertEqual(family['children'], [child]); self.assertEqual(family['relations'][child], [2, 2])
        self.assertEqual(len(self.engine.state()['people']), 3)
        self.assertEqual(next(p for p in self.engine.state()['people'] if p['id'] == child), person)
        before = self.engine.state()
        with self.assertRaises(ValueError):
            self.engine.add(dict(relation='child', target=anna, existing_id=child))
        self.assertEqual(self.engine.state(), before)

    def test_linking_existing_ancestor_as_child_is_rejected_atomically(self):
        ancestor = self.engine.add(dict(first='Nonno'))
        child = self.engine.add(dict(first='Figlio', relation='child', target=ancestor))
        before = self.engine.state()
        with self.assertRaisesRegex(ValueError, 'antenata di sé stessa'):
            self.engine.add(dict(relation='child', target=child, existing_id=ancestor))
        self.assertEqual(self.engine.state(), before)
        with self.assertRaises(ValueError):
            self.engine.add(dict(relation='partner', target=child, existing_id=child))
        self.assertEqual(self.engine.state(), before)

    def test_explicit_new_family_and_filling_one_parent_union_preserve_child_unknown_role(self):
        anna = self.engine.add(dict(first='Anna', gender=0))
        child = self.engine.add(dict(first='Elisa', relation='child', target=anna, child_type='birth'))
        family = self.family(anna)
        self.assertEqual(family['relations'][child], [6, 1])
        mario = self.engine.add(dict(first='Mario', relation='partner', target=anna, family=family['id']))
        self.assertEqual(len(self.engine.state()['families']), 1)
        self.assertEqual(self.family(anna, mario)['relations'][child], [6, 1])
        lone_child = self.engine.add(dict(first='Seconda', relation='child', target=anna, new_family=True))
        self.assertEqual(self.family(anna)['children'], [lone_child])
        self.assertEqual(len(self.engine.state()['families']), 2)

    def test_unlink_child_keeps_person_and_other_links_and_is_undoable(self):
        anna = self.engine.add(dict(first='Anna'))
        child = self.engine.add(dict(first='Mario', birth='1940', relation='child', target=anna, child_type='birth'))
        family = self.family(anna)
        before = self.engine.state()
        with self.assertRaises(ValueError):
            self.engine.unlink(dict(id=child, family=family['id']))
        self.assertEqual(self.engine.state(), before)
        self.engine.unlink(dict(id=child, family=family['id'], confirm=True))
        self.assertEqual(len(self.engine.state()['people']), 2)
        self.assertEqual(self.family(anna)['children'], [])
        self.assertEqual(next(p for p in self.engine.state()['people'] if p['id'] == child)['years'], '1940')
        after = self.engine.state()
        self.engine.undo(); self.assertEqual(self.engine.state(), before)
        self.engine.redo(); self.assertEqual(self.engine.state(), after)
        # The same person can now be attached correctly as a partner.
        self.engine.add(dict(relation='partner', target=anna, family=family['id'], existing_id=child))
        self.assertEqual(len(self.engine.state()['people']), 2)
        self.assertEqual(set(self.family(anna, child)['parents']), {anna, child})

    def test_unlink_parent_does_not_delete_child_or_other_parent(self):
        anna = self.engine.add(dict(first='Anna', gender=0))
        mario = self.engine.add(dict(first='Mario', relation='partner', target=anna))
        child = self.engine.add(dict(first='Elisa', relation='child', target=anna, child_type='birth'))
        family = self.family(anna, mario); before = self.engine.state()
        self.engine.unlink(dict(id=mario, family=family['id'], confirm=True))
        self.assertEqual(len(self.engine.state()['people']), 3)
        self.assertEqual(self.family(anna)['children'], [child])
        self.assertEqual(self.family(anna)['relations'][child], [6, 1])
        self.engine.undo(); self.assertEqual(self.engine.state(), before)

    def test_wrong_family_and_occupied_parent_roles_do_not_modify_records(self):
        anna = self.engine.add(dict(first='Anna'))
        child = self.engine.add(dict(first='Elisa', relation='child', target=anna))
        family = self.family(anna); before = self.engine.state()
        with self.assertRaises(ValueError):
            self.engine.add(dict(first='Altro', relation='child', target=child, family=family['id']))
        with self.assertRaises(ValueError):
            self.engine.add(dict(first='Altro', relation='parent', target=child, family=family['id'], slot='father'))
        self.assertEqual(self.engine.state(), before)
        mother = self.engine.add(dict(first='Maria', relation='parent', target=child))
        self.assertEqual(set(self.family(anna, mother)['parents']), {anna, mother})
        self.assertEqual(len(self.engine.state()['families']), 1)


class DemoRelationshipTests(RelationshipCases, unittest.TestCase):
    def setUp(self): self.engine = DemoEngine(empty=True)


@unittest.skipUnless(HAS_GRAMPS, 'Run with official Gramps 6.0.8 runtime')
class NativeRelationshipTests(RelationshipCases, unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        self.engine = Engine(self.root/'tree')

    def tearDown(self):
        self.engine.close(); self.tmp.cleanup()

    def test_native_unlink_reciprocal_refs_export_and_undo(self):
        parent = self.engine.add(dict(first='Anna'))
        child = self.engine.add(dict(first='Mario', birth='1940', relation='child', target=parent))
        family = self.family(parent); before = self.engine.state()
        self.assertIn(family['id'], self.engine.db.get_person_from_handle(child).get_parent_family_handle_list())
        self.engine.unlink(dict(id=child, family=family['id'], confirm=True))
        self.assertNotIn(family['id'], self.engine.db.get_person_from_handle(child).get_parent_family_handle_list())
        self.assertEqual(self.engine.db.get_family_from_handle(family['id']).get_child_ref_list(), [])
        other = Engine(self.root/'imported')
        try:
            other.import_empty(self.engine.export())
            self.assertEqual(len(other.state()['people']), 2)
            self.assertEqual(other.state()['families'][0]['children'], [])
            self.assertEqual(other.db.get_number_of_events(), 1)
        finally: other.close()
        self.engine.undo(); self.assertEqual(self.engine.state(), before)

    def test_native_two_union_backrefs_and_parent_unlink(self):
        anna = self.engine.add(dict(first='Anna', gender=0))
        mario = self.engine.add(dict(first='Mario'))
        other = self.engine.add(dict(first='Luca'))
        self.engine.add(dict(relation='partner', target=anna, existing_id=mario))
        self.engine.add(dict(relation='partner', target=anna, existing_id=other))
        family = self.family(anna, mario)
        self.assertEqual(len(self.engine.db.get_person_from_handle(anna).get_family_handle_list()), 2)
        self.engine.unlink(dict(id=mario, family=family['id'], confirm=True))
        self.assertNotIn(family['id'], self.engine.db.get_person_from_handle(mario).get_family_handle_list())
        self.assertEqual(len(self.engine.db.get_person_from_handle(anna).get_family_handle_list()), 2)
        self.assertIsNone(self.engine.db.get_family_from_handle(family['id']).get_father_handle())
