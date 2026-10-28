import copy
import itertools
import unittest

from app import geometry
from app.layout import arrange_family


def sample():
    return {'people': [
        {'id': 'a', 'first': 'Ada', 'surname': 'Rossi', 'years': ''},
        {'id': 'b', 'first': 'Maria Costanza', 'surname': 'Di Cristofaro', 'years': '1940'},
        {'id': 'c', 'first': 'Giovanni Alessandro Massimiliano', 'surname': 'Della Valle Monteverdi', 'years': ''},
        {'id': 'd', 'first': 'Élisa', 'surname': 'D’Angelo', 'years': '1960 – 2020'},
        {'id': 'e', 'first': 'Carlo', 'surname': 'Rossi', 'years': ''}],
        'families': [{'id': 'f1', 'parents': ['a', 'b'], 'children': ['c', 'd', 'e']}]}


class UniformCardTests(unittest.TestCase):
    def assert_clear(self, positions):
        for a, b in itertools.combinations(positions.values(), 2):
            self.assertFalse(geometry.overlaps(a, b), (a, b))

    def test_all_cards_have_the_same_dimensions_for_every_font_and_direction(self):
        state = sample()
        for font in ('ui', 'classic', 'italic', 'script'):
            for direction in ('vertical', 'horizontal'):
                for size in (14, 22, 48):
                    with self.subTest(font=font, direction=direction, size=size):
                        positions, cycles = arrange_family(state, {}, {'font_type': font, 'direction': direction, 'font_size': size})
                        self.assertFalse(cycles)
                        expected = geometry.card_size(state, size, font)
                        self.assertEqual({(p['w'], p['h']) for p in positions.values()}, {expected})
                        for person in state['people']:
                            self.assertEqual(geometry.card_dimensions(person, size, font, state), expected)
                        self.assert_clear(positions)

    def test_very_long_names_wrap_without_lost_letters_or_ellipsis(self):
        state = sample()
        state['people'][2].update(first='Alessandro' * 9, surname='WWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWW')
        for font in ('ui', 'classic', 'italic', 'script'):
            width, height = geometry.card_size(state, 22, font)
            self.assertLessEqual(width, 320)
            self.assertGreaterEqual(width, 260)
            for person in state['people']:
                lines = geometry.name_lines(person, 22, font, width)
                expected = (person['first'] + person['surname']).replace(' ', '')
                self.assertEqual(''.join(lines).replace(' ', ''), expected)
                self.assertNotIn('…', ''.join(lines))
                self.assertTrue(all(geometry.text_width(line, 22, font) <= width - geometry._card_padding(22) + 1e-6 for line in lines))
                self.assertGreaterEqual(height, geometry.card_height(person, 22, font, width))

    def test_legacy_name_lines_call_remains_supported(self):
        self.assertEqual(geometry.name_lines({'first': 'Ada', 'surname': 'Rossi'}), ['Ada Rossi'])
        self.assertEqual(geometry.name_lines({'first': '', 'surname': ''}), ['Nome da aggiungere'])

    def test_common_date_row_only_reserves_space_when_dates_exist(self):
        state = sample()
        for person in state['people']:
            person['years'] = ''
        width, no_dates = geometry.card_size(state)
        state['people'][0]['years'] = '1940'
        dated_width, with_dates = geometry.card_size(state)
        self.assertEqual(width, dated_width)
        self.assertAlmostEqual(with_dates - no_dates, 22 * .65 + 10, delta=1)
        positions, _ = arrange_family(state, {})
        self.assertEqual(len({p['h'] for p in positions.values()}), 1)

    def test_old_position_migration_does_not_move_any_person(self):
        state = sample()
        old = {person['id']: {'x': index * 510 - 200, 'y': (index % 2) * 410,
                             'w': 490, 'h': 90, 'locked': index % 2 == 0}
               for index, person in enumerate(state['people'])}
        snapshot = copy.deepcopy(old)
        resized = geometry.resize_positions(state, old, {'font_size': 22})
        self.assertEqual(old, snapshot)
        for identifier, position in old.items():
            self.assertEqual((resized[identifier]['x'], resized[identifier]['y']), (position['x'], position['y']))
        self.assertEqual(len({(p['w'], p['h']) for p in resized.values()}), 1)

    def test_manual_locks_stay_at_exact_coordinates_even_after_font_changes(self):
        state = sample()
        positions, _ = arrange_family(state, {}, {'font_size': 14})
        for index, position in enumerate(positions.values()):
            position.update(x=125 + index * 950, y=-80 + index * 330, locked=True)
        resized = geometry.resize_positions(state, positions, {'font_size': 48, 'font_type': 'script'})
        for identifier in positions:
            self.assertEqual((resized[identifier]['x'], resized[identifier]['y']),
                             (positions[identifier]['x'], positions[identifier]['y']))
            self.assertTrue(resized[identifier]['locked'])

    def test_editing_a_name_at_the_same_font_does_not_translate_positions(self):
        state = sample()
        state['people'][2].update(first='Giovanni', surname='Rossi')
        positions, _ = arrange_family(state, {})
        state['people'][2].update(first='Giovanni Alessandro Massimiliano', surname='Della Valle Monteverdi')
        resized = geometry.resize_positions(state, positions, {'font_size': 22})
        for identifier in positions:
            self.assertEqual((resized[identifier]['x'], resized[identifier]['y']),
                             (positions[identifier]['x'], positions[identifier]['y']))
        self.assertEqual(len({(p['w'], p['h']) for p in resized.values()}), 1)

    def test_arrangement_avoids_manual_obstacles_with_shared_dimensions(self):
        state = sample()
        fixed = {'c': {'x': -430, 'y': -140, 'locked': True},
                 'e': {'x': 630, 'y': 900, 'locked': True}}
        for direction in ('vertical', 'horizontal'):
            positions, _ = arrange_family(state, fixed, {'direction': direction})
            self.assertEqual(len({(p['w'], p['h']) for p in positions.values()}), 1)
            for identifier, position in fixed.items():
                self.assertEqual((positions[identifier]['x'], positions[identifier]['y']), (position['x'], position['y']))
            self.assert_clear(positions)

    def test_reading_rows_of_ten_children_do_not_slide_sideways(self):
        for parent_count in (1, 2):
            parents = ['p' + str(i) for i in range(parent_count)]
            children = ['c' + str(i) for i in range(10)]
            state = {'people': [{'id': i, 'first': 'Persona', 'surname': i, 'years': ''}
                                for i in parents + children],
                     'families': [{'id': 'root', 'parents': parents, 'children': children}]}
            for direction in ('vertical', 'horizontal'):
                positions, _ = arrange_family(state, {}, {'direction': direction, 'reading': True,
                                                          'siblings': 3, 'stagger': False,
                                                          'font_type': 'classic'})
                cross, depth, dim = ('x', 'y', 'w') if direction == 'vertical' else ('y', 'x', 'h')
                rows = {}
                for child in children:
                    position = positions[child]
                    rows.setdefault(position[depth], []).append(position)
                self.assertEqual(sorted(len(row) for row in rows.values()), [1, 3, 3, 3])
                for row in rows.values():
                    row.sort(key=lambda p: p[cross])
                    for left, right in zip(row, row[1:]):
                        self.assertAlmostEqual(right[cross] - left[cross], left[dim] + geometry.GAP + .01)
                width = max(p[cross] + p[dim] for p in positions.values()) - min(p[cross] for p in positions.values())
                self.assertLessEqual(width, 3 * next(iter(positions.values()))[dim] + 2 * (geometry.GAP + .01) + 1e-6)
                self.assert_clear(positions)
