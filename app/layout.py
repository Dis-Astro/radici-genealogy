"""Deterministic family-unit layout; each person appears exactly once.

Partner-connected people form an indivisible unit.  Child rows wrap units,
so a child and their partner stay together.  Genealogical data is read only;
manual positions are obstacles, never rewritten by the layout.
"""
import math
from collections import defaultdict, deque
from statistics import median


def _pack(intervals, gap, limit=None):
    """Least-squares centres with fixed ordering and minimum separation."""
    if not intervals:
        return []
    offsets, offset = [], 0.
    for width, _ in intervals:
        offsets.append(offset + width / 2)
        offset += width + gap
    pools = []
    for index, ((_, centre), start) in enumerate(zip(intervals, offsets)):
        pools.append([index, index + 1, centre - start, 1])
        while len(pools) > 1 and pools[-2][2] > pools[-1][2]:
            right, left = pools.pop(), pools.pop()
            weight = left[3] + right[3]
            pools.append([left[0], right[1], (left[2] * left[3] + right[2] * right[3]) / weight, weight])
    result = [0.] * len(intervals)
    for first, end, value, _ in pools:
        for index in range(first, end):
            result[index] = value + offsets[index] - intervals[index][0] / 2
    if limit is not None and result[-1] + intervals[-1][0] - result[0] > limit:
        # Anchors from separate wrapped rows must not stretch this row forever.
        width = sum(item[0] for item in intervals) + gap * (len(intervals) - 1)
        start = sum(item[1] for item in intervals) / len(intervals) - width / 2
        result = []
        for size, _ in intervals:
            result.append(start)
            start += size + gap
    return result


def arrange_family(state, positions, settings=None):
    # Lazy: geometry exposes this function through its public arrange wrapper.
    from . import geometry as geometry
    settings = settings or {}
    direction = settings.get('direction', 'vertical')
    if direction not in ('vertical', 'horizontal'):
        raise ValueError('Scegli sviluppo verticale oppure orizzontale.')
    capacity = int(geometry.finite(settings.get('siblings', 4), 2, 8))
    size = geometry.finite(settings.get('font_size', 22), 10, 1000)
    font = settings.get('font_type', 'ui')
    vertical = direction == 'vertical'
    gap = geometry.GAP + .01  # Rounding must not turn a clear edge into a collision.
    partner_gap, family_gap, generation_gap, band_gap = gap, gap * 1.5, 88., 48.
    if settings.get('reading'):
        # Respect the same clearance used by the final obstacle pass; smaller
        # row gaps would make that pass push an entire row sideways.
        family_gap, generation_gap, band_gap = gap, 48., gap
    stagger_room = 28. if settings.get('stagger', True) else 0.
    people = {person['id']: person for person in state['people']}
    key = lambda identifier: (str(people[identifier].get('gramps_id') or identifier), str(identifier))
    ids = sorted(people, key=key)
    if not ids:
        return {}, []
    common_size = settings.get('_card_dimensions') or geometry.card_size(state, size, font)
    sizes = {i: common_size for i in ids}
    grid_w, grid_h = max(s[0] for s in sizes.values()), max(s[1] for s in sizes.values())

    def cross_size(identifier):
        return sizes[identifier][0 if vertical else 1]

    def depth_size(identifier):
        return sizes[identifier][1 if vertical else 0]

    def rect(identifier, u, v, locked=False, previous=None):
        return {**(previous or {}), 'x': u if vertical else v, 'y': v if vertical else u,
                'w': sizes[identifier][0], 'h': sizes[identifier][1], 'locked': locked,
                'grid_w': grid_w, 'grid_h': grid_h, 'text_size': size, 'text_font': font}

    def uv(position):
        return (position['x'], position['y']) if vertical else (position['y'], position['x'])

    families = []
    for family in sorted(state['families'], key=lambda f: (str(f.get('gramps_id') or f['id']), str(f['id']))):
        parents = list(dict.fromkeys(p for p in family['parents'] if p in people))
        children = list(dict.fromkeys(c for c in family['children'] if c in people))
        families.append((family['id'], parents, children))
    representative = {i: i for i in ids}

    def find(identifier):
        while representative[identifier] != identifier:
            representative[identifier] = representative[representative[identifier]]
            identifier = representative[identifier]
        return identifier

    def union(a, b):
        a, b = find(a), find(b)
        if a != b:
            first, second = sorted((a, b), key=key)
            representative[second] = first

    partners = {i: set() for i in ids}
    for _, parents, _ in families:
        for a, b in zip(parents, parents[1:]):
            union(a, b)
            partners[a].add(b)
            partners[b].add(a)
    members = defaultdict(list)
    for identifier in ids:
        members[find(identifier)].append(identifier)
    # Greedy adjacency in a partner chain: no duplicate card for later unions.
    for unit, candidates in members.items():
        unused = set(candidates)
        first = min(candidates, key=lambda i: (len(partners[i]) != 1, key(i)))
        ordered = [first]
        unused.remove(first)
        while unused:
            adjacent = partners[ordered[-1]] & unused
            chosen = min(adjacent or unused, key=key)
            ordered.append(chosen)
            unused.remove(chosen)
        members[unit] = ordered
    units = sorted(members, key=key)
    unit_of = {i: unit for unit, group in members.items() for i in group}
    unit_width = {unit: sum(cross_size(i) for i in group) + partner_gap * (len(group) - 1)
                  for unit, group in members.items()}
    unit_depth = {unit: max(depth_size(i) for i in group) for unit, group in members.items()}
    incoming, outgoing, adjacent = ({u: set() for u in units} for _ in range(3))
    child_families = defaultdict(list)
    individual_children = defaultdict(set)
    self_cycles = set()
    for index, (_, parents, children) in enumerate(families):
        parent_units = sorted({unit_of[p] for p in parents}, key=key)
        for child_index, child in enumerate(children):
            target = unit_of[child]
            if parents:
                child_families[target].append((index, child_index))
            for source in parent_units:
                individual_children[source].add(child)
                if source == target:
                    self_cycles.add(source)
                    continue
                incoming[target].add(source)
                outgoing[source].add(target)
                adjacent[source].add(target)
                adjacent[target].add(source)
    degree = {u: len(incoming[u]) for u in units}
    queue = deque(u for u in units if not degree[u])
    ranks = {u: 0 for u in queue}
    while queue:
        source = queue.popleft()
        for target in sorted(outgoing[source], key=key):
            ranks[target] = max(ranks.get(target, 0), ranks[source] + 1)
            degree[target] -= 1
            if not degree[target]:
                queue.append(target)
    unresolved = {u for u in units if degree[u]}
    final_rank = max(ranks.values(), default=0) + 1
    for unit in sorted(unresolved, key=key):
        ranks[unit] = final_rank
    cyclic = sorted((i for u in unresolved | self_cycles for i in members[u]), key=key)
    components, unused = [], set(units)
    while unused:
        first = min(unused, key=key)
        component, todo = [], [first]
        unused.remove(first)
        while todo:
            unit = todo.pop()
            component.append(unit)
            for other in sorted(adjacent[unit] & unused, key=key, reverse=True):
                unused.remove(other)
                todo.append(other)
        components.append(sorted(component, key=key))

    plan, locations, component_boxes = {}, {}, []
    for component in components:
        own = set(component)
        roots = [u for u in component if not incoming[u]]
        is_forest = len(roots) == 1 and not own.intersection(unresolved | self_cycles) and all(len(incoming[u]) <= 1 for u in component)
        if is_forest:
            # Most family albums are trees of couples.  Lay out a whole branch
            # (couple + their descendants) before packing the next sibling.
            # Global generation rows separate these small branches into long,
            # confusing wires; local blocks keep every child's family nearby.
            blocks = {}
            for unit in sorted(component, key=lambda u: (-ranks[u], key(u))):
                children = sorted(outgoing[unit], key=lambda u: (min(child_families[u], default=(-1, -1)), key(u)))
                if not children:
                    blocks[unit] = (unit_width[unit], unit_depth[unit], {unit: [0., 0.]})
                    continue
                limit = max(max(blocks[c][0] for c in children),
                            median(blocks[c][0] for c in children) * capacity + family_gap * (capacity - 1))
                shelves, shelf, used = [], [], 0.
                for child in children:
                    addition = blocks[child][0] + (family_gap if shelf else 0.)
                    if shelf and (len(shelf) == capacity or used + addition > limit):
                        shelves.append(shelf)
                        shelf, used = [], 0.
                    shelf.append(child)
                    used += blocks[child][0] + (family_gap if len(shelf) > 1 else 0.)
                if shelf:
                    shelves.append(shelf)
                widths = [sum(blocks[c][0] for c in row) + family_gap * (len(row) - 1) for row in shelves]
                width = max(unit_width[unit], max(widths))
                local = {unit: [(width - unit_width[unit]) / 2, 0.]}
                depth = unit_depth[unit] + generation_gap
                for row, row_width in zip(shelves, widths):
                    u = (width - row_width) / 2
                    extent = 0.
                    for column, child in enumerate(row):
                        child_width, child_depth, child_plan = blocks[child]
                        shift = (column % 2) * stagger_room if len(children) > 3 else 0.
                        for descendant, (cu, cv) in child_plan.items():
                            local[descendant] = [u + cu, depth + cv + shift]
                        u += child_width + family_gap
                        extent = max(extent, child_depth + shift)
                    depth += extent + band_gap
                blocks[unit] = (width, depth - band_gap, local)
            width, depth, local = blocks[roots[0]]
            plan.update(local)
            component_boxes.append({'units': component, 'width': width, 'depth': depth,
                                    'min_u': 0., 'min_v': 0.})
            continue
        start = 0.
        layers, row_limits = [], {}
        for rank in sorted({ranks[u] for u in component}):
            layer = [u for u in component if ranks[u] == rank]
            max_depth = max(unit_depth[u] for u in layer)
            grouped = defaultdict(list)
            for unit in layer:
                primary = min(child_families[unit], default=(-1, -1))
                grouped[primary[0]].append(unit)
            cohorts = []
            for family_index, group in grouped.items():
                group.sort(key=lambda u: (min(child_families[u], default=(-1, -1)), key(u)))
                parent_units = set().union(*(incoming[u] & own for u in group))
                anchors = [plan[u][0] + unit_width[u] / 2 for u in sorted(parent_units, key=key) if u in plan]
                desired = sum(anchors) / len(anchors) if anchors else 0.
                width_limit = max(max(unit_width[u] for u in group), median(unit_width[u] for u in group) * capacity + gap * (capacity - 1))
                bands, band, width = [], [], 0.
                for unit in group:
                    addition = unit_width[unit] + (gap if band else 0)
                    if band and (len(band) == capacity or width + addition > width_limit):
                        bands.append(band)
                        band, width = [], 0.
                    band.append(unit)
                    width += unit_width[unit] + (gap if len(band) > 1 else 0)
                if band:
                    bands.append(band)
                stagger = 28. if settings.get('stagger', True) and family_index != -1 and len(group) > 3 else 0.
                widths = [sum(unit_width[u] for u in b) + gap * (len(b) - 1) for b in bands]
                parent_depth = min((plan[u][1] for u in parent_units if u in plan), default=0.)
                cohorts.append({'units': group, 'bands': bands, 'widths': widths,
                                'width': max(widths), 'centre': desired, 'stagger': stagger,
                                'family': family_index, 'parent_depth': parent_depth})
            cohorts.sort(key=lambda c: (c['parent_depth'], c['centre'], c['family'], key(c['units'][0])))
            # A generation's many different families also wrap as whole blocks.
            # Wrapping only a single family's children still makes a giant line
            # when ten siblings each have their own two or three children.
            limit = max(max(c['width'] for c in cohorts) * 2 + family_gap,
                        median(unit_width[u] for u in layer) * capacity + gap * (capacity - 1))
            shelves, shelf, used = [], [], 0.
            for cohort in cohorts:
                addition = cohort['width'] + (family_gap if shelf else 0.)
                if shelf and used + addition > limit:
                    shelves.append(shelf)
                    shelf, used = [], 0.
                shelf.append(cohort)
                used += cohort['width'] + (family_gap if len(shelf) > 1 else 0.)
            if shelf:
                shelves.append(shelf)
            end = start
            band_base = 0
            for shelf in shelves:
                lefts = _pack([(c['width'], c['centre']) for c in shelf], family_gap, limit)
                for cohort, left in zip(shelf, lefts):
                    for band_index, (band, width) in enumerate(zip(cohort['bands'], cohort['widths'])):
                        u = left + (cohort['width'] - width) / 2
                        # A whole couple moves together; siblings never split partners.
                        for column, unit in enumerate(band):
                            band_number = band_base + band_index
                            v = start + band_number * (max_depth + band_gap + stagger_room) + (column % 2) * cohort['stagger']
                            plan[unit] = [u, v]
                            locations[unit] = (rank, band_number)
                            row_limits[(rank, band_number)] = limit
                            u += unit_width[unit] + gap
                            end = max(end, v + unit_depth[unit])
                band_base += max(len(c['bands']) for c in shelf)
            layers.append(layer)
            start = end + generation_gap
        # Pull each parent unit towards the actual children, preserving row order.
        for layer in reversed(layers):
            rows = defaultdict(list)
            for unit in layer:
                rows[locations[unit]].append(unit)
            for row in rows.values():
                row.sort(key=lambda u: (plan[u][0], key(u)))
                intervals = []
                for unit in row:
                    targets = []
                    for child in sorted(individual_children[unit], key=key):
                        target = unit_of[child]
                        if ranks[target] <= ranks[unit] or target not in plan:
                            continue
                        child_offset = sum(cross_size(i) + partner_gap for i in members[target][:members[target].index(child)])
                        targets.append(plan[target][0] + child_offset + cross_size(child) / 2)
                    centre = sum(targets) / len(targets) if targets else plan[unit][0] + unit_width[unit] / 2
                    intervals.append((unit_width[unit], centre))
                for unit, left in zip(row, _pack(intervals, gap, row_limits[locations[row[0]]])):
                    plan[unit][0] = left
        min_u = min(plan[u][0] for u in component)
        min_v = min(plan[u][1] for u in component)
        width = max(plan[u][0] + unit_width[u] for u in component) - min_u
        depth = max(plan[u][1] + unit_depth[u] for u in component) - min_v
        component_boxes.append({'units': component, 'width': width, 'depth': depth,
                                'min_u': min_u, 'min_v': min_v})

    # Pack disconnected branches and isolated people into nearby shelves.
    area = sum((c['width'] + family_gap) * (c['depth'] + family_gap) for c in component_boxes)
    limit = max(max(c['width'] for c in component_boxes), math.sqrt(area) * 1.12)
    shelves = []
    for component in sorted(component_boxes, key=lambda c: (-c['depth'], -c['width'], key(c['units'][0]))):
        shelf = next((s for s in shelves if s['used'] + component['width'] <= limit + .001 and component['depth'] <= s['depth']), None)
        if shelf is None:
            shelf = {'v': sum(s['depth'] + family_gap for s in shelves), 'depth': component['depth'], 'used': 0.}
            shelves.append(shelf)
        du, dv = shelf['used'] - component['min_u'], shelf['v'] - component['min_v']
        shelf['used'] += component['width'] + family_gap
        for unit in component['units']:
            plan[unit][0] += du
            plan[unit][1] += dv

    result = {i: rect(i, *uv(positions[i]), True, positions[i]) for i in ids if positions.get(i, {}).get('locked')}

    def clear(identifier, u, v, previous=None):
        """Nearest clear position on the same generation, left or right."""
        candidate = rect(identifier, u, v, False, previous)
        obstacles = []
        for other in result.values():
            ou, ov = uv(other)
            od = other['h'] if vertical else other['w']
            if v < ov + od + gap and ov < v + depth_size(identifier) + gap:
                oc = other['w'] if vertical else other['h']
                obstacles.append((ou - cross_size(identifier) - gap, ou + oc + gap))
        choices = {u}
        for left, right in obstacles:
            choices.add(left)
            choices.add(right)
        for cross in sorted(choices, key=lambda value: (abs(value - u), value < u, value)):
            candidate = rect(identifier, cross, v, False, previous)
            if not any(geometry.overlaps(candidate, other) for other in result.values()):
                return candidate
        raise ValueError('Non riesco a trovare uno spazio libero per questa persona.')

    # A fixed member anchors their whole branch near its existing coordinates.
    for component in component_boxes:
        offsets_u, offsets_v = [], []
        for unit in component['units']:
            offset = 0.
            for identifier in members[unit]:
                if identifier in result:
                    u, v = uv(result[identifier])
                    offsets_u.append(u - plan[unit][0] - offset)
                    offsets_v.append(v - plan[unit][1] - unit_depth[unit] + depth_size(identifier))
                offset += cross_size(identifier) + partner_gap
        if offsets_u:
            du, dv = median(offsets_u), median(offsets_v)
            for unit in component['units']:
                plan[unit][0] += du
                plan[unit][1] += dv
    ordered_units = sorted(units, key=lambda u: (not any(i in result for i in members[u]), ranks[u], plan[u][1], plan[u][0], key(u)))
    for unit in ordered_units:
        u, v = plan[unit]
        fixed = [i for i in members[unit] if i in result]
        if fixed:
            anchor = fixed[0]
            offset = sum(cross_size(i) + partner_gap for i in members[unit][:members[unit].index(anchor)])
            au, av = uv(result[anchor])
            u, v = au - offset, av + depth_size(anchor) - unit_depth[unit]
        # Find a clear translation for the entire free unit before placing cards.
        if not fixed:
            forbidden = []
            for other in result.values():
                ou, ov = uv(other)
                oc, od = (other['w'], other['h']) if vertical else (other['h'], other['w'])
                if v < ov + od + gap and ov < v + unit_depth[unit] + gap:
                    forbidden.append((ou - unit_width[unit] - gap, ou + oc + gap))
            choices = {u, *(edge for interval in forbidden for edge in interval)}
            u = min((value for value in choices if all(value <= left or value >= right for left, right in forbidden)),
                    key=lambda value: (abs(value - u), value < u, value))
        offset = 0.
        for identifier in members[unit]:
            if identifier not in result:
                result[identifier] = clear(identifier, u + offset, v + unit_depth[unit] - depth_size(identifier), positions.get(identifier))
            offset += cross_size(identifier) + partner_gap
    return {i: result[i] for i in ids}, cyclic
