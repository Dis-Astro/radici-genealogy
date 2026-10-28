import copy
import itertools
import random
import unittest

from app import geometry
from app.layout import arrange_family


def person(identifier, first=None, surname='Rossi'):
    return {'id': identifier, 'gramps_id': 'I' + identifier, 'first': first or identifier,
            'surname': surname, 'years': '', 'gender': 2}


def family(identifier, parents, children):
    return {'id': identifier, 'gramps_id': 'F' + identifier,
            'parents': parents, 'children': children}


def descendants():
    people = [person('a', 'Anna'), person('b', 'Giovanni Alessandro')]
    children = ['c' + str(i) for i in range(8)]
    families = [family('root', ['a', 'b'], children)]
    for index, child in enumerate(children):
        partner = 's' + str(index)
        grandchildren = ['n' + str(index) + str(i) for i in range(3)]
        people.extend([person(child, 'Figlio ' + str(index)), person(partner, 'Compagno ' + str(index))])
        people.extend(person(i, 'Nipote ' + i) for i in grandchildren)
        families.append(family(str(index), [child, partner], grandchildren))
    return {'people': people, 'families': families}


class FamilyLayoutTests(unittest.TestCase):
    def assert_clear(self, positions):
        for (aid, a), (bid, b) in itertools.combinations(positions.items(), 2):
            self.assertFalse(geometry.overlaps(a, b), (aid, bid, a, b))

    def assert_couple(self, positions, a, b, direction):
        cross, depth, cd, dd = ('x', 'y', 'w', 'h') if direction == 'vertical' else ('y', 'x', 'h', 'w')
        first, second = sorted((positions[a], positions[b]), key=lambda p: p[cross])
        self.assertAlmostEqual(second[cross] - first[cross] - first[cd], geometry.GAP + .01, places=5)
        self.assertAlmostEqual(first[depth] + first[dd], second[depth] + second[dd], places=5)

    def test_wraps_whole_couples_and_keeps_each_family_beyond_its_parents(self):
        state = descendants()
        for direction in ('vertical', 'horizontal'):
            with self.subTest(direction=direction):
                positions, cyclic = arrange_family(state, {}, {'direction': direction, 'siblings': 3, 'stagger': True})
                self.assertFalse(cyclic)
                self.assertEqual(set(positions), {p['id'] for p in state['people']})
                self.assert_clear(positions)
                for f in state['families']:
                    self.assert_couple(positions, *f['parents'], direction)
                depth, dim = ('y', 'h') if direction == 'vertical' else ('x', 'w')
                children = state['families'][0]['children']
                self.assertGreater(len({positions[c][depth] for c in children}), 3)
                for f in state['families'][1:]:
                    self.assertGreater(min(positions[c][depth] for c in f['children']),
                                       max(positions[p][depth] + positions[p][dim] for p in f['parents']))

    def test_same_output_after_reloading_or_reordering_records(self):
        state = descendants()
        expected, _ = arrange_family(state, {}, {'siblings': 4})
        shuffled = copy.deepcopy(state)
        random.Random(572).shuffle(shuffled['people'])
        random.Random(215).shuffle(shuffled['families'])
        actual, _ = arrange_family(shuffled, expected, {'siblings': 4})
        self.assertEqual(actual, expected)

    def test_grandchildren_of_many_families_wrap_as_family_blocks(self):
        state = descendants()
        positions, _ = arrange_family(state, {}, {'direction': 'vertical', 'siblings': 3, 'stagger': False})
        grandchildren = [c for f in state['families'][1:] for c in f['children']]
        self.assertGreater(len({positions[c]['y'] for c in grandchildren}), 1)
        width = max(p['x'] + p['w'] for p in positions.values()) - min(p['x'] for p in positions.values())
        unwrapped = sum(positions[c]['w'] + geometry.GAP for c in grandchildren)
        self.assertLess(width, unwrapped / 2)
        self.assert_clear(positions)

    def test_subtree_blocks_keep_children_near_their_own_parents(self):
        state = descendants()
        for direction in ('vertical', 'horizontal'):
            positions, _ = arrange_family(state, {}, {'direction': direction, 'siblings': 3, 'stagger': False})
            depth, dim = ('y', 'h') if direction == 'vertical' else ('x', 'w')
            for f in state['families'][1:]:
                first_child = min(positions[c][depth] for c in f['children'])
                parents_end = max(positions[p][depth] + positions[p][dim] for p in f['parents'])
                self.assertGreater(first_child, parents_end)
                self.assertLessEqual(first_child - parents_end, 100)

    def test_multiple_unions_share_one_person_and_keep_partners_close(self):
        state = {'people': [person(i) for i in ['a', 'b', 'c', 'd', 'e']],
                 'families': [family('one', ['a', 'b'], ['d']), family('two', ['a', 'c'], ['e'])]}
        for direction in ('vertical', 'horizontal'):
            positions, _ = arrange_family(state, {}, {'direction': direction})
            self.assertEqual(len(positions), 5)
            self.assert_clear(positions)
            for partner in ('b', 'c'):
                self.assert_couple(positions, 'a', partner, direction)

    def test_shared_ancestry_uses_dag_without_duplicating_a_spouse(self):
        state = {'people': [person(i) for i in 'abcdefgh'],
                 'families': [family('one', ['a', 'b'], ['e', 'f']),
                              family('two', ['c', 'd'], ['g']),
                              family('three', ['e', 'g'], ['h'])]}
        for direction in ('vertical', 'horizontal'):
            positions, cyclic = arrange_family(state, {}, {'direction': direction})
            self.assertFalse(cyclic)
            self.assertEqual(len(positions), 8)
            self.assert_clear(positions)
            self.assert_couple(positions, 'e', 'g', direction)
            depth = 'y' if direction == 'vertical' else 'x'
            for f in state['families']:
                self.assertGreater(min(positions[c][depth] for c in f['children']),
                                   max(positions[p][depth] for p in f['parents']))

    def test_shared_dimensions_and_manual_obstacles_are_preserved(self):
        state = descendants()
        fixed = {'c1': {'x': -350, 'y': 180, 'locked': True},
                 'n70': {'x': 710, 'y': 20, 'locked': True}}
        for direction in ('vertical', 'horizontal'):
            positions, _ = arrange_family(state, fixed, {'direction': direction, 'font_size': 28})
            for identifier in fixed:
                self.assertEqual({key: positions[identifier][key] for key in fixed[identifier]}, fixed[identifier])
            for p in state['people']:
                expected = geometry.card_dimensions(p, 28, 'ui', state=state)
                self.assertEqual((positions[p['id']]['w'], positions[p['id']]['h']), expected)
            self.assertEqual(positions['a']['w'], positions['b']['w'])
            self.assert_clear(positions)

    def test_disconnected_people_use_compact_rows_instead_of_one_long_line(self):
        state = {'people': [person(str(i), 'Persona ' + str(i)) for i in range(24)], 'families': []}
        for direction in ('vertical', 'horizontal'):
            positions, _ = arrange_family(state, {}, {'direction': direction})
            self.assert_clear(positions)
            x0 = min(p['x'] for p in positions.values())
            x1 = max(p['x'] + p['w'] for p in positions.values())
            width = x1 - x0
            self.assertLess(width, sum(p['w'] + geometry.GAP for p in positions.values()) / 2)
            self.assertGreater(len({p['y'] for p in positions.values()}), 1)

    def test_cycle_is_visible_without_duplicate_people_or_endless_layout(self):
        state = {'people': [person(i) for i in 'abcd'],
                 'families': [family('one', ['a', 'b'], ['c']), family('two', ['c'], ['a', 'd'])]}
        positions, cyclic = arrange_family(state, {})
        self.assertEqual(len(positions), 4)
        self.assertIn('a', cyclic)
        self.assert_clear(positions)

    def test_invalid_settings_and_empty_tree(self):
        empty = {'people': [], 'families': []}
        self.assertEqual(arrange_family(empty, {}), ({}, []))
        with self.assertRaises(ValueError):
            arrange_family(empty, {}, {'direction': 'diagonal'})
        with self.assertRaises(ValueError):
            arrange_family(empty, {}, {'siblings': 0})
