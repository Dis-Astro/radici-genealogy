import copy
import itertools
import unittest
from app.geometry import arrange, overlaps, connections, family_color, rounded, svg
from app.demo import DemoEngine


def large_family(count=12):
    people=[dict(id=f'p{i:02}',gramps_id=f'I{i+1:04}',first='Persona '+str(i),surname='Rossi',years='1948',gender=2) for i in range(count+3)]
    children=[p['id'] for p in people[2:-1]]
    families=[dict(id='f1',gramps_id='F0001',parents=['p00','p01'],children=children,relations={c:[1,1] for c in children}),
              dict(id='f2',gramps_id='F0002',parents=[children[-1]],children=[people[-1]['id']],relations={people[-1]['id']:[2,6]})]
    return dict(people=people,families=families)


class CompositionTests(unittest.TestCase):
    def test_both_directions_no_collisions_with_twelve_children(self):
        state=large_family()
        for direction in ['vertical','horizontal']:
            with self.subTest(direction=direction):
                positions,cycles=arrange(state,{},dict(direction=direction,siblings=4,stagger=True))
                self.assertFalse(cycles)
                for a,b in itertools.combinations(positions.values(),2):self.assertFalse(overlaps(a,b))
                depth='y' if direction=='vertical' else 'x'
                for f in state['families']:
                    self.assertGreater(min(positions[c][depth] for c in f['children']),max(positions[p][depth] for p in f['parents']))
                childdepth={positions[c][depth] for c in state['families'][0]['children']}
                self.assertGreater(len(childdepth),3)
                last=state['people'][-1]['id']
                self.assertGreater(positions[last][depth],max(positions[c][depth] for c in state['families'][0]['children']))

    def test_reflow_is_deterministic_and_respects_locked_nodes(self):
        state=large_family()
        fixed={'p04':dict(x=-400,y=-200,locked=True)}
        one,_=arrange(state,fixed,dict(direction='horizontal'))
        two,_=arrange(state,fixed,dict(direction='horizontal'))
        self.assertEqual(one,two)
        self.assertEqual({k:one['p04'][k] for k in fixed['p04']},fixed['p04'])

    def test_curves_bundles_and_family_labels_replace_parent_child_mesh(self):
        state=large_family()
        positions,_=arrange(state,{})
        paths=connections(state,positions)
        self.assertIn(' Q',paths)
        self.assertIn('F0001',paths)
        self.assertIn('F0002',paths)
        self.assertEqual(paths.count('class="family-link"'),2)
        self.assertLess(paths.count('class="family-stem"'),2*12+2)
        self.assertEqual(family_color(state['families'][0]),family_color(copy.deepcopy(state['families'][0])))
        self.assertNotEqual(family_color(state['families'][0]),family_color(state['families'][1]))

    def test_settings_propagate_to_print_and_invalid_values_fail(self):
        state=large_family(5)
        settings=dict(direction='horizontal',siblings=3,stagger=True)
        positions,_=arrange(state,{},settings)
        out=svg(state,positions,dict(format='A3'),settings=settings)
        self.assertNotIn('>F0001</text>',out)
        self.assertIn('family-stem',out)
        with self.assertRaises(ValueError):arrange(state,{},dict(direction='diagonal'))
        with self.assertRaises(ValueError):arrange(state,{},dict(siblings=1000))
