import itertools
import math
import unittest
from app.demo import DemoEngine
from app.geometry import arrange, overlaps, place, sheet, svg, finite


class GeometryTests(unittest.TestCase):
    def setUp(self):
        self.state = DemoEngine().state()
        self.positions, self.cyclic = arrange(self.state,{})

    def test_names_are_continuous_without_person_codes(self):
        from app.geometry import card_text
        text=card_text({'first':'Anna','surname':'Conti','gramps_id':'I0002','years':'1938'})
        self.assertIn('Anna Conti',text)
        self.assertNotIn('I0002',text)
        small=sheet({'font_size':14},self.positions)
        large=sheet({'font_size':28},self.positions)
        self.assertAlmostEqual(large['font_pt'],small['font_pt']*2)
        output=svg(self.state,self.positions,{'font_size':28,'font_type':'ui'})
        self.assertIn('font-size="28.0"',output)

    def test_full_long_names_expand_cards_and_print_without_family_codes(self):
        import xml.etree.ElementTree as ET
        from app.geometry import resize_positions,card_size
        self.state['people'][0]['first']='Giovanni Alessandro Massimiliano'
        self.state['people'][0]['surname']='Della Valle Monteverdi WWWWWWWWWWWWWWWWWWWWWWWWWWW'
        for direction in ('vertical','horizontal'):
            settings={'font_size':14,'direction':direction}
            small,_=arrange(self.state,{},settings)
            large=resize_positions(self.state,small,{'font_size':28})
            self.assertGreater(large['p0']['w'],small['p0']['w'])
            self.assertGreater(large['p0']['h'],small['p0']['h'])
            for a,b in itertools.combinations(large.values(),2):self.assertFalse(overlaps(a,b))
            output=svg(self.state,small,{'font_size':28},settings=settings)
            root=ET.fromstring(output)
            visible=' '.join(n.attrib.get('aria-label','') for n in root.iter() if n.attrib.get('role')=='img')+' '.join(n.text or '' for n in root.iter('{http://www.w3.org/2000/svg}text'))
            self.assertNotIn('F0001',visible)
            self.assertNotIn('…',visible)
            self.assertIn('Massimiliano',visible)
            self.assertIn('Monteverdi',visible)
            self.assertEqual(visible.count('W'),27)
            self.assertIn('family-stem',output)

    def test_layout_is_acyclic_and_collision_free(self):
        self.assertFalse(self.cyclic)
        self.assertEqual(len(self.positions),8)
        for a,b in itertools.combinations(self.positions.values(),2):
            self.assertFalse(overlaps(a,b))
        for f in self.state['families']:
            for p in f['parents']:
                for c in f['children']:
                    self.assertLess(self.positions[p]['y'],self.positions[c]['y'])

    def test_locked_position_is_preserved_and_avoided(self):
        fixed = {'p6':{'x':0,'y':0,'locked':True}}
        positions,_ = arrange(self.state,fixed)
        self.assertEqual({k:positions['p6'][k] for k in fixed['p6']},fixed['p6'])
        for i,p in positions.items():
            if i!='p6':
                self.assertFalse(overlaps(p,positions['p6']))

    def test_manual_drop_avoids_collisions(self):
        positions = place(self.positions,'p7',0,0)
        self.assertTrue(positions['p7']['locked'])
        self.assertFalse(any(overlaps(positions['p7'],v) for i,v in positions.items() if i!='p7'))

    def test_cycle_terminates_and_reports_nodes(self):
        self.state['families'].append(dict(id='bad',parents=['p6'],children=['p0']))
        positions, cyclic = arrange(self.state,{})
        self.assertIn('p0',cyclic)
        self.assertEqual(len(positions),8)

    def test_units_and_custom_sizes(self):
        mm=sheet(dict(format='custom',width=125,height=256,unit='mm',margin=10,safety=3),self.positions)
        cm=sheet(dict(format='custom',width=12.5,height=25.6,unit='cm',margin=1,safety=.3),self.positions)
        self.assertEqual(mm,cm)
        large=sheet(dict(format='custom',width=125,height=256,unit='cm'),self.positions)
        self.assertEqual((large['width'],large['height']),(1250,2560))

    def test_standard_orientation_and_fit(self):
        s=sheet(dict(format='A3',orientation='landscape'),self.positions)
        self.assertEqual((s['width'],s['height']),(420,297))
        self.assertFalse(s['overflow'])
        s=sheet(dict(format='A4',mode='scale',scale=1000),self.positions)
        self.assertTrue(s['overflow'])

    def test_invalid_geometry_rejected(self):
        for value in [float('nan'),float('inf'),-100001]:
            with self.assertRaises(ValueError):
                finite(value,-100000,100000)
        with self.assertRaises(ValueError):
            sheet(dict(format='A4',margin=105),self.positions)
        with self.assertRaises(ValueError):
            sheet(dict(unit='inch'),self.positions)

    def test_print_svg_escape_and_physical_dimensions(self):
        self.state['people'][0]['first']='<script>&"'
        out=svg(self.state,self.positions,dict(format='A4'))
        self.assertIn('width="210mm"',out)
        self.assertIn('height="297mm"',out)
        self.assertNotIn('<script>',out)
        self.assertIn('&lt;script&gt;',out)
        self.assertNotIn('stroke-dasharray="2 2"',out)
        self.assertIn('stroke-dasharray="2 2"',svg(self.state,self.positions,dict(format='A4'),True))

    def test_pdf_is_exact_page_size(self):
        try:
            import cairosvg
        except (ImportError,OSError):
            self.skipTest('CairoSVG o Cairo nativo assente: eseguire in Docker')
        from app.geometry import pdf
        data=pdf(self.state,self.positions,dict(format='custom',width=125,height=256))
        self.assertTrue(data.startswith(b'%PDF-'))
        # Cairo may compress PDF objects; read the page rather than matching bytes.
        import io
        try:
            from pypdf import PdfReader
        except ImportError:
            from PyPDF2 import PdfReader
        page=PdfReader(io.BytesIO(data)).pages[0]
        self.assertAlmostEqual(float(page.mediabox.width),125*72/25.4,places=3)
        self.assertAlmostEqual(float(page.mediabox.height),256*72/25.4,places=3)
