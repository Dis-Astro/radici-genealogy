import copy
import itertools
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from app.demo import DemoEngine
from app.geometry import (arrange, card_height, card_size, place, sheet, svg,
                          overlaps, family_alignment, resize_positions, print_settings,
                          connections)
from app.service import Service


class AlbumTests(unittest.TestCase):
    def setUp(self):
        self.state=DemoEngine().state()

    def test_large_fonts_use_uniform_compact_cells_without_collisions(self):
        self.state['people'][0]['years']=''
        for direction in ('vertical','horizontal'):
            for size in (36,72,144):
                positions,_=arrange(self.state,{},dict(font_size=size,direction=direction))
                for a,b in itertools.combinations(positions.values(),2):
                    self.assertFalse(overlaps(a,b))
                self.assertEqual({(p['w'],p['h']) for p in positions.values()},
                                 {card_size(self.state,size)})
                self.assertEqual(positions['p0']['h'],positions['p1']['h'])
                self.assertGreater(positions['p0']['w'],size*4)
        self.assertLess(card_height({'first':'Ada','surname':'','years':''},22),60)

    def test_snap_junction_and_opt_out_and_no_collision(self):
        positions={
            'a':dict(x=0,y=0,w=120,h=50,locked=False),
            'b':dict(x=160,y=0,w=120,h=50,locked=False),
            'c':dict(x=85,y=200,w=120,h=50,locked=False)}
        state={'families':[dict(parents=['a','b'],children=['c'])]}
        targets=family_alignment(state,positions,'c')
        snapped=place(positions,'c',85,200,extra_targets=targets)
        self.assertEqual(snapped['c']['x'],80)
        self.assertEqual(place(positions,'c',85,200,snap=False)['c']['x'],85)
        self.assertFalse(any(overlaps(snapped['c'],q) for i,q in snapped.items() if i!='c'))

    def test_exactly_aligned_pair_has_straight_connectors(self):
        self.state['people']=self.state['people'][:2]
        self.state['people'][0]['years']=''
        self.state['families']=[dict(id='f',parents=['p0'],children=['p1'],relations={'p1':[1,1]})]
        for direction in ('vertical','horizontal'):
            settings=dict(direction=direction)
            positions,_=arrange(self.state,{},settings)
            paths=connections(self.state,positions,settings)
            self.assertNotIn(' Q',paths)

    def test_actual_point_size_overflow_and_suggested_paper(self):
        positions,_=arrange(self.state,{},dict(font_size=72))
        config=dict(format='custom',width=50,height=50,font_size=72,text_pt=24,mode='readable')
        info=sheet(config,positions)
        self.assertTrue(info['overflow'])
        self.assertGreaterEqual(info['font_pt'],24-1e-6)
        config.update(width=info['recommended_width'],height=info['recommended_height'])
        self.assertFalse(sheet(config,positions)['overflow'])

    def test_small_custom_sheet_fit_always_contains_tree_despite_font_target(self):
        from app.geometry import bounds
        positions,_=arrange(self.state,{},dict(font_size=72))
        for font in ('classic','script'):
            for orientation in ('portrait','landscape'):
                for unit,w,h in [('mm',100,150),('cm',10,15)]:
                    config=dict(format='custom',width=w,height=h,unit=unit,orientation=orientation,
                                font_size=72,text_pt=24,mode='fit',font_type=font,
                                title='La mia famiglia',margin=1 if unit=='cm' else 10,safety=.3 if unit=='cm' else 3)
                    resized=resize_positions(self.state,positions,print_settings(config))
                    info=sheet(config,resized)
                    self.assertFalse(info['overflow'])
                    self.assertLess(info['font_pt'],24)
                    x,y,bw,bh=bounds(resized)
                    inset=info['margin']+info['safety']
                    self.assertGreaterEqual(info['tx']+x*info['scale'],inset-1e-6)
                    self.assertGreaterEqual(info['ty']+y*info['scale'],inset+14-1e-6)
                    self.assertLessEqual(info['tx']+(x+bw)*info['scale'],info['width']-inset+1e-6)
                    self.assertLessEqual(info['ty']+(y+bh)*info['scale'],info['height']-inset+1e-6)
                    self.assertEqual((info['width'],info['height']),(100,150) if orientation=='portrait' else (150,100))

    def test_scale_mode_keeps_exact_scale_despite_font_target(self):
        positions,_=arrange(self.state,{})
        info=sheet(dict(mode='scale',scale=10,text_pt=96),positions)
        self.assertAlmostEqual(info['scale'],.1*25.4/96)

    def test_album_styles_keep_names_omit_codes_and_have_no_external_fonts(self):
        positions,_=arrange(self.state,{})
        for theme,font in [('classic','classic'),('heritage','script'),('essential','italic')]:
            config=dict(theme=theme,font_type=font,font_size=72,title='La famiglia & i ricordi')
            output=svg(self.state,positions,config)
            root=ET.fromstring(output)
            labels=[e.attrib.get('aria-label') for e in root.iter()]
            self.assertIn('Giovanni Rossi',labels)
            self.assertIn('La famiglia & i ricordi',labels)
            visible=' '.join(e.text or '' for e in root.iter('{http://www.w3.org/2000/svg}text'))
            self.assertNotIn('F0001',visible)
            self.assertNotIn('@font-face',output)
            self.assertNotIn('https://',output)
            self.assertIn('<path',output)

    def test_print_branch_is_read_only_and_keeps_partner(self):
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp)
            service=Service(DemoEngine(),base/'data',base/'media',base/'backups',True)
            before=copy.deepcopy(service.state())
            result=service.print_tree(dict(root_id='p4',theme='classic',font_size=72), 'preview')
            self.assertIn('Carlo Rossi',result['svg'])
            self.assertIn('Elena Ferrari',result['svg'])
            self.assertIn('Sofia Rossi',result['svg'])
            self.assertNotIn('Giovanni Rossi',result['svg'])
            self.assertEqual(service.state(),before)
            service.command('layout',dict(revision=service.view['revision'],layout={'font_size':96}))
            self.assertEqual(service.view['layout']['font_size'],96)

