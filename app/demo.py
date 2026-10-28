"""Explicit, ephemeral demo adapter. Never used by Docker's normal command."""
import copy
import uuid
from .engine import _add_plan, _family_roles


class DemoEngine:
    def __init__(self, empty=False):
        names = [('Giovanni','Rossi','1932 – 2011'), ('Maria','Bianchi','1936'),
                 ('Pietro','Ferrari','1934 – 2016'), ('Anna','Conti','1938'),
                 ('Carlo','Rossi','1961'), ('Elena','Ferrari','1964'),
                 ('Sofia','Rossi','1990'), ('Luca','Rossi','1993')]
        self.data = {'people': [dict(id=f'p{i}', gramps_id=f'I{i+1:04}', first=a, surname=b, years=c, gender=2) for i,(a,b,c) in enumerate(names)],
                     'families': [dict(id='f0', gramps_id='F0001', parents=['p0','p1'], children=['p4'], relations={'p4':[1,1]}),
                                  dict(id='f1', gramps_id='F0002', parents=['p2','p3'], children=['p5'], relations={'p5':[1,1]}),
                                  dict(id='f2', gramps_id='F0003', parents=['p4','p5'], children=['p6','p7'], relations={'p6':[1,1], 'p7':[1,1]})]}
        self.past, self.future = [], []
        if empty:
            self.data={'people':[],'families':[]}

    def state(self):
        state = copy.deepcopy(self.data)
        for person in state['people']:
            if person.get('years') in ('Date da aggiungere', 'Data da aggiungere'):
                person['years'] = ''
        for family in state['families']:
            family.setdefault('parent_roles', _family_roles(family))
        return state

    def add(self, data):
        plan = _add_plan(self.state(), data)
        old = self.state()
        try:
            identifier = plan['existing_id'] or uuid.uuid4().hex
            values = plan['person']
            if values:
                self.data['people'].append(dict(id=identifier, gramps_id=f'I{len(self.data["people"])+1:04}', first=values['first'], surname=values['surname'], years=values['birth'], gender=values['gender']))
            relation, target = plan['relation'], plan['target']
            if relation != 'independent':
                family = next((f for f in self.data['families'] if f['id'] == plan['family']), None)
                is_new = family is None
                if is_new:
                    family = dict(id=uuid.uuid4().hex, gramps_id='F'+str(len(self.data['families'])+1).zfill(4), parents=[], children=[], relations={}, parent_roles={})
                    self.data['families'].append(family)
                family.setdefault('parent_roles', _family_roles(family))
                family.setdefault('relations', {})
                role = 0 if plan['slot'] == 'father' else 1
                kind = dict(unknown=6, birth=1, adopted=2)[plan['child_type']]
                if relation == 'partner':
                    family['parents'] = [target, identifier]
                    family['parent_roles'] = {target: role, identifier: 1-role}
                    for child in family['children']:
                        family['relations'].setdefault(child, [6, 6])[1-role] = 6
                elif relation == 'child':
                    if is_new:
                        family['parents'].append(target); family['parent_roles'][target] = role
                    family['children'].append(identifier)
                    roles = family['parent_roles'].values()
                    family['relations'][identifier] = [kind if index in roles else 6 for index in (0, 1)]
                elif relation == 'parent':
                    family['parents'].append(identifier); family['parent_roles'][identifier] = role
                    if is_new:
                        family['children'].append(target); family['relations'][target] = [6, 6]
                    family['relations'].setdefault(target, [6, 6])[role] = kind
                family['parents'].sort(key=lambda p: family['parent_roles'][p])
            self.past.append(old); self.future.clear()
            return identifier
        except Exception:
            self.data = old
            raise

    def unlink(self, data):
        if data.get('confirm') is not True:
            raise ValueError('Conferma la rimozione del solo legame familiare.')
        identifier = data.get('id')
        family = next((f for f in self.data['families'] if f['id'] == data.get('family')), None)
        if not family or identifier not in {p['id'] for p in self.data['people']}:
            raise ValueError('Persona o famiglia inesistente.')
        if identifier not in family['parents'] + family['children']:
            raise ValueError('Questa persona non appartiene alla famiglia scelta.')
        self.past.append(self.state()); self.future.clear()
        family.setdefault('parent_roles', _family_roles(family))
        role = family['parent_roles'].pop(identifier, None)
        family['parents'] = [p for p in family['parents'] if p != identifier]
        family['children'] = [p for p in family['children'] if p != identifier]
        family.setdefault('relations', {}).pop(identifier, None)
        if role is not None:
            for child in family['children']: family['relations'].setdefault(child, [6, 6])[role] = 6
        return identifier

    def undo(self):
        self.future.append(self.state())
        self.data = self.past.pop()

    def edit(self,d):
        p=next((p for p in self.data['people'] if p['id']==d.get('id')),None)
        if not p or not str(d.get('first','')).strip():
            raise ValueError('Inserisci un nome valido.')
        self.past.append(self.state());self.future.clear()
        p.update(first=d['first'].strip(),surname=d.get('surname',''),gender=int(d.get('gender',2)))

    def redo(self):
        self.past.append(self.state())
        self.data = self.future.pop()

    def delete(self,d):
        identifier=d.get('id')
        if identifier not in {p['id'] for p in self.data['people']}:
            raise ValueError('Persona inesistente.')
        self.past.append(self.state());self.future.clear()
        self.data['people']=[p for p in self.data['people'] if p['id']!=identifier]
        for f in self.data['families']:
            f['parents']=[p for p in f['parents'] if p!=identifier]
            f['children']=[p for p in f['children'] if p!=identifier]
            f.get('relations',{}).pop(identifier,None)
            f.get('parent_roles',{}).pop(identifier,None)
        self.data['families']=[f for f in self.data['families'] if f['parents'] or f['children']]

    def export(self):
        raise ValueError('La demo non contiene un database Gramps. Avvia Docker per import/export e backup reali.')

    import_empty = lambda self, data: self.export()
    close = lambda self: None
