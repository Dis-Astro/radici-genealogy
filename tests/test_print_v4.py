"""Print V4 regressions: physical points, separate reflow and paper fitting."""
import copy
import importlib.util
import re
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from app.demo import DemoEngine
from app.engine import Engine
from app.geometry import arrange, bounds, prepare_print, sheet
from app.service import Service

HAS_GRAMPS = importlib.util.find_spec('gramps') is not None


def family_album():
    people = [dict(id='p0', gramps_id='I0001', first='Anna', surname='Rossi', years='1940', gender=0),
              dict(id='p1', gramps_id='I0002', first='Mario', surname='Bianchi', years='1938', gender=1)]
    children = ['c' + str(i) for i in range(41)]
    people.extend(dict(id=identifier, gramps_id='I'+str(i+3).zfill(4), first='Figlio '+str(i+1), surname='Bianchi', years='', gender=2) for i,identifier in enumerate(children))
    people.extend(dict(id='isolated'+str(i), gramps_id='I'+str(44+i).zfill(4), first='Persona isolata '+str(i), surname='', years='', gender=2) for i in range(2))
    return dict(people=people, families=[dict(id='union', gramps_id='F0001', parents=['p0','p1'], children=children, parent_roles={'p0':1,'p1':0}, relations={child:[1,1] for child in children})])


def scattered_locked(state):
    positions, _ = arrange(state, {})
    for index, identifier in enumerate(positions):
        positions[identifier].update(x=index*1700, y=(index%4)*1800, locked=index<43)
    return positions


def content_scale(document):
    root = ET.fromstring(document)
    for group in root.iter('{http://www.w3.org/2000/svg}g'):
        transform = group.attrib.get('transform', '')
        match = re.search(r'\bscale\(([-+.\deE]+)\)', transform)
        if match: return float(match.group(1))
    raise AssertionError('Physical sheet has no drawing scale')


class PrintV4Tests(unittest.TestCase):
    def test_readable_22_to_26_is_exact_physical_points_in_rendered_svg(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            service = Service(DemoEngine(), root/'data', root/'media', root/'backup', True)
            results = []
            for requested in (22, 26):
                config = dict(format='custom', width=1500, height=1500, unit='mm', margin=10, safety=3,
                              font_size=32, text_pt=requested, mode='readable', composition='compact', direction='vertical')
                preview = service.print_tree(config, 'preview')
                info = preview['sheet']
                self.assertAlmostEqual(info['font_pt'], requested, places=8)
                self.assertFalse(info['overflow'])
                actual_points = content_scale(preview['svg'])*32*72/25.4
                self.assertAlmostEqual(actual_points, requested, places=8)
                results.append(actual_points)
            self.assertAlmostEqual(results[1]/results[0], 26/22, places=10)

    def test_compact_print_ignores_43_locks_includes_isolated_people_and_is_read_only(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); engine = DemoEngine(empty=True); engine.data = family_album()
            service = Service(engine, root/'data', root/'media', root/'backup', True)
            service.view['positions'] = scattered_locked(engine.state()); service.refresh()
            self.assertEqual(sum(p['locked'] for p in service.view['positions'].values()), 43)
            service.past = [dict(kind='view', positions=copy.deepcopy(service.view['positions']), layout=copy.deepcopy(service.view['layout']))]
            service.future = copy.deepcopy(service.past)
            snapshot = copy.deepcopy((engine.state(), service.view, service.past, service.future))
            saved = {p: p.read_bytes() for p in (service.file, service.data/'demo.json')}
            config = dict(format='A3', mode='fit', composition='compact', direction='vertical', font_size=32, text_pt=26)
            positions, _ = prepare_print(engine.state(), service.view['positions'], config, service.view['layout'])
            self.assertEqual(set(positions), {p['id'] for p in engine.state()['people']})
            self.assertFalse(any(p['locked'] for p in positions.values()))
            self.assertLess(bounds(positions)[2], bounds(service.view['positions'])[2]/5)
            preview = service.print_tree(config, 'preview')
            self.assertEqual(preview['sheet']['people'], 45)
            labels = {element.attrib.get('aria-label') for element in ET.fromstring(preview['svg']).iter()}
            self.assertIn('Persona isolata 0', labels); self.assertIn('Persona isolata 1', labels)
            self.assertEqual((engine.state(), service.view, service.past, service.future), snapshot)
            for path, content in saved.items(): self.assertEqual(path.read_bytes(), content)

    def test_100_by_150_fit_contains_everything_and_reports_reduced_effective_font(self):
        state = family_album(); positions = scattered_locked(state)
        for orientation in ('portrait', 'landscape'):
            with self.subTest(orientation=orientation):
                config = dict(format='custom', width=100, height=150, unit='mm', orientation=orientation,
                              margin=5, safety=2, mode='fit', text_pt=26, font_size=32,
                              composition='compact', direction='auto', title='La nostra famiglia')
                prepared, _ = prepare_print(state, positions, config)
                info = sheet(config, prepared)
                self.assertFalse(info['overflow'])
                self.assertGreater(info['font_pt'], 0); self.assertLess(info['font_pt'], 26)
                x, y, width, height = bounds(prepared); inset = info['margin']+info['safety']
                self.assertGreaterEqual(info['tx']+x*info['scale'], inset-1e-6)
                self.assertGreaterEqual(info['ty']+y*info['scale'], inset+14-1e-6)
                self.assertLessEqual(info['tx']+(x+width)*info['scale'], info['width']-inset+1e-6)
                self.assertLessEqual(info['ty']+(y+height)*info['scale'], info['height']-inset+1e-6)
                self.assertEqual((info['width'],info['height']), (100,150) if orientation=='portrait' else (150,100))

    def test_auto_print_direction_uses_best_fitting_explicit_direction(self):
        state = family_album(); positions = scattered_locked(state)
        config = dict(format='custom', width=500, height=280, margin=10, safety=3, mode='fit',
                      composition='compact', font_size=32, text_pt=26, direction='auto', font_type='italic', theme='heritage')
        automatic, style = prepare_print(state, positions, config, dict(direction='vertical', font_size=22))
        automatic_scale = sheet(config, automatic)['scale']
        explicit = {}
        for direction in ('vertical', 'horizontal'):
            prepared, _ = prepare_print(state, positions, {**config, 'direction':direction})
            explicit[direction] = sheet(config, prepared)['scale']
        self.assertAlmostEqual(automatic_scale, max(explicit.values()), places=10)
        self.assertAlmostEqual(automatic_scale, explicit[style['direction']], places=10)
        self.assertIn(style['direction'], ('vertical','horizontal'))
        self.assertEqual(style['font_size'], 32); self.assertEqual(style['font_type'], 'italic')
        self.assertEqual(style['theme'], 'heritage'); self.assertTrue(style['print_mode'])


@unittest.skipUnless(HAS_GRAMPS, 'Run with official Gramps 6.0.8 runtime')
class NativePrintV4Tests(unittest.TestCase):
    def test_compact_print_preserves_native_data_saved_view_and_real_undo(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); engine = Engine(root/'data/tree')
            try:
                anna = engine.add(dict(first='Anna', birth='1940', gender=0))
                mario = engine.add(dict(first='Mario', relation='partner', target=anna, gender=1))
                child = engine.add(dict(first='Elisa', relation='child', target=anna, child_type='birth'))
                isolated = engine.add(dict(first='Isolata'))
                service = Service(engine, root/'data', root/'media', root/'backup')
                service.command('edit', dict(revision=0, id=anna, first='Anna Maria', surname='', gender=0))
                snapshot = copy.deepcopy((engine.state(), service.view, service.past, service.future))
                stored = service.file.read_bytes(); event_count = engine.db.get_number_of_events()
                preview = service.print_tree(dict(format='custom', width=1500, height=1500, font_size=32, text_pt=26,
                                                  mode='readable', composition='compact', direction='auto'), 'preview')
                self.assertEqual(preview['sheet']['people'], 4)
                self.assertAlmostEqual(preview['sheet']['font_pt'], 26, places=8)
                self.assertEqual((engine.state(), service.view, service.past, service.future), snapshot)
                self.assertEqual(service.file.read_bytes(), stored)
                self.assertEqual(engine.db.get_number_of_events(), event_count)
                service.command('undo', dict(revision=service.view['revision']))
                self.assertEqual(next(p for p in engine.state()['people'] if p['id']==anna)['first'], 'Anna')
                self.assertEqual(set(p['id'] for p in engine.state()['people']), {anna,mario,child,isolated})
            finally: engine.close()
