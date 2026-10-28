import copy
import re
import unittest
import xml.etree.ElementTree as ET

from app.geometry import arrange, card_size, card_text, connections, text_width, vertical_metrics
from app.typography import font


def names():
    return {'people': [
        {'id': 'a', 'first': 'Ada', 'surname': 'Rossi', 'years': '1940'},
        {'id': 'b', 'first': 'Maria Costanza Giuseppina', 'surname': 'Della Valle Di Cristofaro Monteverdi', 'years': '1948 – 2020'},
        {'id': 'c', 'first': 'Élisa', 'surname': 'D’Angelo', 'years': ''}], 'families': []}


class CardRenderingTests(unittest.TestCase):
    def assert_in_cell(self, bounds, width, height):
        left, top, right, bottom = bounds
        self.assertGreaterEqual(left, -1e-5)
        self.assertGreaterEqual(top, -1e-5)
        self.assertLessEqual(right, width + 1e-5)
        self.assertLessEqual(bottom, height + 1e-5)

    def test_ui_names_are_centred_full_and_inside_the_shared_cell(self):
        state = names()
        for size in (22, 72):
            width, height = card_size(state, size, 'ui')
            for person in state['people']:
                root = ET.fromstring('<svg>' + card_text(person, size, height, 'ui', width) + '</svg>')
                lines = root.findall('./text[@class="person-name"]')
                visible = ''.join(line.text or '' for line in lines).replace(' ', '')
                full = (person['first'] + person['surname']).replace(' ', '')
                self.assertEqual(visible, full)
                self.assertNotIn('…', visible)
                for line in lines:
                    x, y = float(line.get('x')), float(line.get('y'))
                    self.assertEqual(line.get('text-anchor'), 'middle')
                    self.assertAlmostEqual(x, width / 2)
                    advance = text_width(line.text, size, 'ui')
                    ascent, descent = vertical_metrics(line.text, 'ui')
                    self.assert_in_cell((x - advance/2, y - ascent*size,
                                         x + advance/2, y + descent*size), width, height)

    def test_actual_outlined_glyph_bounds_fit_for_album_fonts_and_long_names(self):
        from fontTools.pens.boundsPen import BoundsPen
        state = names()
        for key in ('classic', 'italic', 'script'):
            loaded = font(key)
            glyphs, cmap = loaded.getGlyphSet(), loaded.getBestCmap()
            advances = loaded['hmtx'].metrics
            for size in (22, 72):
                width, height = card_size(state, size, key)
                for person in state['people']:
                    root = ET.fromstring('<svg>' + card_text(person, size, height, key, width) + '</svg>')
                    lines = root.findall('./g[@role="img"]')
                    visible = ''.join(line.get('aria-label') for line in lines).replace(' ', '')
                    self.assertEqual(visible, (person['first'] + person['surname']).replace(' ', ''))
                    self.assertNotIn('…', visible)
                    for line in lines:
                        transform = re.fullmatch(r'translate\(([-\d.eE]+) ([-\d.eE]+)\) scale\(([-\d.eE]+) ([-\d.eE]+)\)', line.get('transform'))
                        self.assertIsNotNone(transform)
                        tx, ty, sx, sy = map(float, transform.groups())
                        cursor = 0
                        for letter in line.get('aria-label'):
                            glyph = cmap.get(ord(letter), '.notdef')
                            pen = BoundsPen(glyphs)
                            glyphs[glyph].draw(pen)
                            if pen.bounds:
                                x0, y0, x1, y1 = pen.bounds
                                self.assert_in_cell((tx + (cursor+x0)*sx, ty + y1*sy,
                                                     tx + (cursor+x1)*sx, ty + y0*sy), width, height)
                            cursor += advances[glyph][0]

    def test_dates_share_one_baseline_and_absent_dates_render_nothing(self):
        state = names()
        for key in ('ui', 'classic', 'italic', 'script'):
            for size in (22, 72):
                width, height = card_size(state, size, key)
                baselines = []
                for person in state['people']:
                    source = card_text(person, size, height, key, width)
                    root = ET.fromstring('<svg>' + source + '</svg>')
                    dates = root.findall('./text[@class="person-dates"]')
                    self.assertEqual(len(dates), int(bool(person['years'])))
                    self.assertNotIn('Data da aggiungere', source)
                    for date in dates:
                        self.assertEqual(date.text, person['years'])
                        self.assertEqual(float(date.get('x')), width / 2)
                        baselines.append(float(date.get('y')))
                self.assertEqual(set(baselines), {height - 10})

    def test_childless_adjacent_couple_has_one_bridge_and_no_false_descent(self):
        state = {'people': names()['people'][:2],
                 'families': [{'id': 'pair', 'parents': ['a', 'b'], 'children': []}]}
        original = copy.deepcopy(state)
        for direction in ('vertical', 'horizontal'):
            positions, _ = arrange(state, {}, {'direction': direction})
            root = ET.fromstring('<svg>' + connections(state, positions, {'direction': direction, 'print_mode': True}) + '</svg>')
            stems = root.findall('.//path[@class="family-stem"]')
            self.assertEqual(len(stems), 1)
            self.assertEqual(stems[0].get('data-kind'), 'couple-stem')
            self.assertNotIn('Q', stems[0].get('d'))
            self.assertEqual(root.findall('.//path[@data-kind="descent"]'), [])
            self.assertEqual(root.findall('.//circle'), [])
        self.assertEqual(state, original)

    def test_a_child_adds_descent_to_the_couple_bridge_without_duplicate_partners(self):
        state = {'people': names()['people'],
                 'families': [{'id': 'pair', 'parents': ['a', 'b'], 'children': ['c']}]}
        for direction in ('vertical', 'horizontal'):
            positions, _ = arrange(state, {}, {'direction': direction})
            root = ET.fromstring('<svg>' + connections(state, positions, {'direction': direction}) + '</svg>')
            self.assertEqual(len(root.findall('.//path[@data-kind="couple-stem"]')), 1)
            self.assertGreaterEqual(len(root.findall('.//path[@data-kind="descent"]')), 2)
            self.assertEqual(set(positions), {'a', 'b', 'c'})
