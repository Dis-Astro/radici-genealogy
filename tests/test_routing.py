import math
import re
import unittest
import xml.etree.ElementTree as ET

from app.routing import Router
from app.geometry import connections, rounded


def inside(point, card):
    return card['x'] + 1e-6 < point[0] < card['x'] + card['w'] - 1e-6 and card['y'] + 1e-6 < point[1] < card['y'] + card['h'] - 1e-6


class RoutingTests(unittest.TestCase):
    def assert_curve_clear(self, data, cards):
        commands = re.findall(r'([MLQ])([^MLQ]*)', data)
        current = None
        for command, arguments in commands:
            numbers = list(map(float, re.findall(r'-?\d+(?:\.\d+)?(?:e[+-]?\d+)?', arguments, re.I)))
            if command == 'M':
                current = tuple(numbers)
                continue
            endpoint = tuple(numbers[-2:])
            for step in range(101):
                t = step / 100
                if command == 'L':
                    point = tuple(a + (b - a) * t for a, b in zip(current, endpoint))
                else:
                    control = numbers[:2]
                    point = tuple((1-t)**2*a + 2*(1-t)*t*b + t*t*c for a, b, c in zip(current, control, endpoint))
                self.assertFalse(any(inside(point, card) for card in cards.values()), point)
            current = endpoint

    def assert_path(self, route, start, end, cards):
        self.assertEqual(route[0], start)
        self.assertEqual(route[-1], end)
        for a, b in zip(route, route[1:]):
            self.assertTrue(a[0] == b[0] or a[1] == b[1], (a, b))
            for step in range(101):
                point = (a[0] + (b[0] - a[0]) * step / 100, a[1] + (b[1] - a[1]) * step / 100)
                self.assertFalse(any(inside(point, card) for card in cards.values()), point)

    def test_routes_around_intervening_card_instead_of_through_its_name(self):
        cards = {'middle': {'x': 100, 'y': 40, 'w': 160, 'h': 100}}
        start, end = (20, 90), (340, 90)
        route = Router(cards, [start, end]).route(start, end)
        self.assertGreater(len(route), 3)
        self.assert_path(route, start, end, cards)

    def test_many_obstacles_negative_coordinates_and_repeatability(self):
        cards = {'a': {'x': -180, 'y': -100, 'w': 100, 'h': 200},
                 'b': {'x': -30, 'y': 50, 'w': 120, 'h': 190},
                 'c': {'x': 140, 'y': -40, 'w': 120, 'h': 170}}
        start, end = (-260, -20), (340, 190)
        router = Router(cards, [start, end])
        route = router.route(start, end)
        self.assert_path(route, start, end, cards)
        self.assertEqual(route, router.route(start, end))
        reversed_cards = dict(reversed(list(cards.items())))
        self.assertEqual(route, Router(reversed_cards, [start, end]).route(start, end))

    def test_rounding_does_not_cut_through_card_corners(self):
        cards = {'middle': {'x': 100, 'y': 40, 'w': 160, 'h': 100}}
        start, end = (20, 90), (340, 90)
        route = Router(cards, [start, end]).route(start, end)
        self.assert_curve_clear(rounded(route), cards)

    def test_preferred_route_must_still_connect_the_requested_people(self):
        start, end = (0, 0), (100, 100)
        wrong = [(400, 400), (400, 500)]
        route = Router({}, [start, end]).route(start, end, preferred=wrong)
        self.assert_path(route, start, end, {})

    def test_distinct_unions_do_not_share_the_same_junction(self):
        cards = {'parent': {'x': 0, 'y': 0, 'w': 100, 'h': 80}}
        families = []
        for index in range(4):
            child = 'child' + str(index)
            cards[child] = {'x': 200 + index * 130, 'y': 350, 'w': 90, 'h': 50}
            families.append({'id': 'family' + str(index), 'parents': ['parent'], 'children': [child]})
        source = ET.fromstring('<svg>' + connections({'people': [], 'families': families}, cards) + '</svg>')
        junctions = [(float(circle.get('cx')), float(circle.get('cy'))) for circle in source.findall('./g/circle')]
        self.assertEqual(len(junctions), 4)
        for index, first in enumerate(junctions):
            for second in junctions[index+1:]:
                self.assertGreaterEqual(math.dist(first, second), 12)

    def test_complete_family_paths_avoid_all_cards_in_both_directions(self):
        from app.layout import arrange_family
        from test_family_layout import descendants
        state = descendants()
        for direction in ('vertical', 'horizontal'):
            positions, _ = arrange_family(state, {}, {'direction': direction, 'siblings': 3, 'stagger': True})
            source = ET.fromstring('<svg>' + connections(state, positions, {'direction': direction}) + '</svg>')
            paths = source.findall('.//path[@class="family-stem"]')
            self.assertGreater(len(paths), len(state['families']))
            for path in paths:
                self.assert_curve_clear(path.get('d'), positions)
