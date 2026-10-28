import copy
import io
import unittest
import zipfile
import xml.etree.ElementTree as ET
from app.album import album,plan_album,page_svg,wrap,PT
from app.crossings import overpasses,bridge_svg
from app.typography import width,vertical_metrics


def family_state():
    people=[dict(id=str(i),first='Persona '+str(i),surname='Della Famiglia',years='1900' if i%2 else '') for i in range(17)]
    people[6].update(first='Maria Costanza',surname='Di Cristofaro')
    return dict(people=people,families=[
        dict(id='first',parents=['0','1'],children=[str(i) for i in range(2,12)],relations={'2':[2,2],'3':[6,6]}),
        dict(id='second',parents=['0','12'],children=['13','14']),
        dict(id='next',parents=['2','15'],children=[])])


class AlbumPageTests(unittest.TestCase):
    def test_complete_coverage_continuation_and_separate_unions_without_mutation(self):
        state=family_state();before=copy.deepcopy(state);plan=plan_album(state,{})
        self.assertEqual(state,before)
        seen=set()
        for p in plan['pages']:
            if p['kind'] not in ('family','isolated'):continue
            seen.update(p['parents']+p['children'])
            self.assertLessEqual(len(p['parents'])+len(p['children']),6)
            self.assertEqual(len(p['parents']+p['children']),len(set(p['parents']+p['children'])))
        self.assertEqual(seen,{p['id'] for p in state['people']})
        first=[p for p in plan['pages'] if p.get('family',{}).get('id')=='first']
        self.assertGreater(len(first),1)
        self.assertEqual([i for p in first for i in p['children']],list(map(str,range(2,12))))
        self.assertTrue(all(p['parents']==['0','1'] for p in first))
        second=next(p for p in plan['pages'] if p.get('family',{}).get('id')=='second')
        self.assertEqual(second['parents'],['0','12']);self.assertEqual(second['children'],['13','14'])
        self.assertEqual(state,before)

    def test_real_name_ink_stays_within_uniform_cards_and_names_are_complete(self):
        state=family_state();plan=plan_album(state,{'album_text_pt':16})
        for p in state['people']:
            lines=plan['name_lines'][p['id']]
            self.assertEqual(''.join(lines).replace(' ',''),(p['first']+p['surname']).replace(' ',''))
            self.assertTrue(all(width(line,plan['name_size'],'classic')<=plan['card_w']-6+.0001 for line in lines))
            block=sum((sum(vertical_metrics(line,'classic'))+.18)*plan['name_size'] for line in lines)
            self.assertLess(1.8+block,plan['card_h']-5-2)
        for p in plan['pages']:
            if p['kind'] not in ('family','isolated'):continue
            tree=ET.fromstring(page_svg(plan,p))
            boxes=tree.findall('.//{*}g[@data-album-person]/{*}rect')
            self.assertTrue(boxes)
            self.assertEqual({(float(b.get('width')),float(b.get('height'))) for b in boxes},{(plan['card_w'],plan['card_h'])})
            self.assertTrue(all(float(b.get('y'))+float(b.get('height'))<=82.01 for b in boxes))

    def test_pdf_and_svg_pages_have_exact_photo_dimensions(self):
        from pypdf import PdfReader
        state=family_state();plan=plan_album(state,{})
        content=album(state,{},'pdf');reader=PdfReader(io.BytesIO(content))
        self.assertEqual(len(reader.pages),len(plan['pages']))
        for page in reader.pages:
            self.assertAlmostEqual(float(page.mediabox.width),150/PT,places=3)
            self.assertAlmostEqual(float(page.mediabox.height),100/PT,places=3)
        with zipfile.ZipFile(io.BytesIO(album(state,{},'svgzip'))) as archive:
            names=[n for n in archive.namelist() if n.endswith('.svg')]
            self.assertEqual(len(names),len(reader.pages))
            for name in names:
                root=ET.fromstring(archive.read(name))
                self.assertEqual(root.get('width'),'150mm');self.assertEqual(root.get('height'),'100mm')

    def test_adopted_and_unconfirmed_relations_keep_distinct_marks(self):
        plan=plan_album(family_state(),{})
        page=next(p for p in plan['pages'] if '2' in p.get('children',[]) and p['kind']=='family')
        tree=ET.fromstring(page_svg(plan,page))
        self.assertEqual(tree.find('.//{*}path[@data-child="2"]').get('stroke-dasharray'),'1.1 .7')
        self.assertEqual(tree.find('.//{*}path[@data-child="3"]').get('stroke-dasharray'),'.3 .7')

    def test_large_type_is_never_silently_reduced(self):
        with self.assertRaisesRegex(ValueError,'non entrano'):plan_album(family_state(),{'album_text_pt':72})
        with self.assertRaises(ValueError):plan_album(family_state(),{'album_text_pt':11})
        with self.assertRaises(ValueError):album(family_state(),{'album_page':1.5},'preview')

    def test_empty_and_single_person_without_invented_links(self):
        with self.assertRaises(ValueError):plan_album(dict(people=[],families=[]),{})
        state=dict(people=[dict(id='a',first='Anna',surname='Rossi')],families=[])
        plan=plan_album(state,{})
        page=next(p for p in plan['pages'] if p['kind']=='isolated')
        self.assertEqual(page['children'],['a'])
        root=ET.fromstring(page_svg(plan,page))
        self.assertEqual(len(root.findall('.//{*}g[@data-album-person]')),1)
        self.assertFalse(root.findall('.//{*}path[@data-child]'))


class CrossingsTests(unittest.TestCase):
    def test_true_crossing_has_bridge_but_same_union_has_no_false_overpass(self):
        records=[dict(family='a',points=[(0,50),(100,50)]),dict(family='b',points=[(50,0),(50,100)])]
        result=overpasses(records)
        self.assertEqual(len(result),1);self.assertEqual((result[0]['x'],result[0]['y']),(50,50))
        self.assertIn('data-crossing="overpass"',bridge_svg(result[0],'#123','#fff',1,3))
        records[1]['family']='a';self.assertEqual(overpasses(records),[])

    def test_bridge_avoids_corners_duplicate_coordinates_and_cards(self):
        records=[dict(family='a',points=[(0,50),(100,50)]),dict(family='b',points=[(50,0),(50,100)]),dict(family='c',points=[(50,0),(50,100)])]
        self.assertEqual(len(overpasses(records)),1)
        self.assertEqual(overpasses(records,clear=lambda p:False),[])
        records[0]['points']=[(45,50),(100,50)]
        self.assertEqual(overpasses(records),[])
