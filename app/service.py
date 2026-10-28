import copy
import hashlib
import json
import os
import time
import uuid
import zipfile
from pathlib import Path
from .geometry import arrange, place, finite, sheet, svg, pdf, connections, family_color, card_text, card_size, resize_positions, card_height, print_settings, family_alignment, prepare_print


def atomic_json(path, value):
    content=json.dumps(value,ensure_ascii=False).encode('utf-8')
    if path.exists() and path.read_bytes()==content:return
    temp = path.with_suffix('.tmp')
    with temp.open('wb') as f:
        f.write(content)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp, path)


class Service:
    def __init__(self, engine, data, media, backups, demo=False):
        self.engine, self.demo = engine, demo
        self.data, self.media, self.backups = map(Path, (data, media, backups))
        for p in (self.data, self.media, self.backups):
            p.mkdir(parents=True, exist_ok=True)
        self.file = self.data/'workspace.json'
        self.view = json.loads(self.file.read_text('utf-8')) if self.file.exists() else {'positions': {}, 'revision': 0}
        self.view.setdefault('layout',{'direction':'vertical','siblings':4,'stagger':True})
        self.past, self.future = [], []
        self.backup_error = None
        self.last_backup = time.monotonic()
        self.refresh()

    def refresh(self):
        state = self.engine.state()
        ids = {p['id'] for p in state['people']}
        self.view['positions'] = {k:v for k,v in self.view['positions'].items() if k in ids}
        if ids-set(self.view['positions']):
            self.view['positions'], _ = arrange(state, self.view['positions'],self.view['layout'])
        self.view["positions"] = resize_positions(state,self.view["positions"],self.view["layout"])
        if self.demo:atomic_json(self.data/'demo.json',state)
        atomic_json(self.file, self.view)

    def state(self):
        state = self.engine.state()
        links=connections(state,self.view['positions'],self.view['layout'])
        return {**state, **copy.deepcopy(self.view), 'demo': self.demo,
                'locked_count':sum(bool(p.get('locked')) for p in self.view['positions'].values()),
                'card_text':{p['id']:card_text(p,self.view['layout'].get('font_size',22),self.view['positions'][p['id']]['h'],
                                             'ui',self.view['positions'][p['id']]['w']) for p in state['people']},
                'connections_svg':links,
                'layout_warning':'Alcune posizioni rendono difficili i collegamenti. Usa Riordina oppure stampa un solo ramo.' if 'data-routing-warning' in links else None,
                'family_colors':{f['id']:family_color(f) for f in state['families']},
                'undo': bool(self.past), 'redo': bool(self.future), 'backup_error': self.backup_error}

    def presentation(self, data):
        """Build a separate, temporary reading view; never save or edit the tree."""
        mode = data.get('mode', 'family')
        if mode not in ('family', 'overview'):
            raise ValueError('Scegli la vista famiglia oppure la panoramica.')
        direction = data.get('direction', 'vertical')
        if direction not in ('vertical', 'horizontal'):
            raise ValueError('Scegli sviluppo verticale oppure orizzontale.')
        siblings = finite(data.get('siblings', 3 if mode == 'overview' else 4), 2, 8)
        if not siblings.is_integer():
            raise ValueError('Il numero di figli per riga deve essere intero.')
        size = finite(data.get('font_size', 22), 10, 1000)
        layout = dict(direction=direction, siblings=int(siblings), font_size=size,
                      stagger=False, font_type='classic', reading=mode == 'family')
        viewport = {key: finite(data[key], 100, 10000) if data.get(key) is not None else None
                    for key in ('viewport_width', 'viewport_height')}
        original = copy.deepcopy(self.engine.state())
        # Every reading context uses the same measure from the whole tree.
        # The client cannot supply this internal override or change saved cards.
        layout['_card_dimensions'] = card_size(original, size, 'classic')
        people = {person['id']: person for person in original['people']}
        identifier = data.get('id') or None
        if identifier is not None and (not isinstance(identifier, str) or identifier not in people):
            raise ValueError('Seleziona una persona presente in questo albero.')
        if mode == 'overview':
            visible = set(people)
            chosen = original['families']
        else:
            visible = {identifier} if identifier else set()
            chosen = []
            for family in original['families']:
                if identifier and identifier in family['children']:
                    visible.update(family['parents']); chosen.append(family)
                elif identifier and identifier in family['parents']:
                    visible.update(family['parents']); visible.update(family['children'])
                    chosen.append(family)
        visible.intersection_update(people)
        families = []
        for source in chosen:
            # A parent's family contributes only the focused child, even when
            # another visible person happens to be that child's sibling.
            children = [child for child in source['children'] if child in visible
                        and (mode == 'overview' or identifier in source['parents'] or child == identifier)]
            parents = [parent for parent in source['parents'] if parent in visible]
            family = {**source, 'parents': parents, 'children': children,
                      'visible_children': len(children), 'total_children': len(source['children']),
                      'partial': len(children) != len(source['children']) or len(parents) != len(source['parents'])}
            if 'parent_roles' in source:
                family['parent_roles'] = {key: value for key, value in source['parent_roles'].items() if key in parents}
            if 'relations' in source:
                family['relations'] = {key: value for key, value in source['relations'].items() if key in children}
            families.append(family)
        state = {'people': [person for person in original['people'] if person['id'] in visible],
                 'families': families}
        positions, _ = arrange(state, {}, layout)
        if mode == 'family' and positions and all(value is not None for value in viewport.values()):
            candidates = []
            for capacity in (2, 3, 4, 5, 6, 8):
                candidate_layout = {**layout, 'siblings': capacity}
                candidate, _ = arrange(state, {}, candidate_layout)
                width = max(p['x'] + p['w'] for p in candidate.values()) - min(p['x'] for p in candidate.values())
                height = max(p['y'] + p['h'] for p in candidate.values()) - min(p['y'] for p in candidate.values())
                scale = min((viewport['viewport_width'] - 32) / max(1, width),
                            (viewport['viewport_height'] - 48) / max(1, height))
                candidates.append((scale, -abs(capacity - siblings), -capacity, candidate, candidate_layout))
            *_, positions, layout = max(candidates, key=lambda candidate: candidate[:3])
        return {**state, 'positions': positions, 'layout': layout,
                'card_text': {person['id']: card_text(person, size, positions[person['id']]['h'],
                                                   'classic', positions[person['id']]['w']) for person in state['people']},
                'connections_svg': connections(state, positions, layout),
                'family_colors': {family['id']: family_color(family) for family in families},
                'total_people': len(original['people']), 'view_mode': mode, 'focus_id': identifier}

    def check_revision(self, data):
        if data.get('revision') != self.view['revision']:
            raise ValueError('L’albero è cambiato in un’altra scheda. Ricarica la pagina prima di continuare.')

    def command(self, action, data):
        self.check_revision(data)
        old = copy.deepcopy(self.view['positions'])
        old_layout = copy.deepcopy(self.view['layout'])
        kind = 'view'
        if action in ('add','edit','delete','unlink'):
            if action=='delete':
                if data.get('confirm') is not True:
                    raise ValueError('Conferma la cancellazione della persona selezionata.')
                if data.get('id') not in {p['id'] for p in self.engine.state()['people']}:
                    raise ValueError('Persona inesistente.')
                if not self.demo:
                    self.backup()
            getattr(self.engine,action)(data)
            kind = 'genealogy'
            # Existing cards stay put when adding/editing/deleting people.
            current = self.engine.state()
            keep = {i:{**pos,'locked':True} for i,pos in old.items()}
            positions,_ = arrange(current,keep,self.view['layout'])
            for i,pos in positions.items():
                if i in old:
                    pos['locked'] = old[i].get('locked',False)
            self.view['positions'] = positions
        elif action == 'layout':
            settings = {**self.view['layout'],**data.get('layout',{})}
            if set(settings)-{'direction','siblings','stagger','font_size'}:
                raise ValueError('Opzione di composizione sconosciuta.')
            settings['font_size'] = finite(settings.get('font_size',22),10,1000)
            source = {i:{**p,'locked':False} for i,p in old.items()} if data.get('release_locked') else old
            positions,_ = arrange(self.engine.state(),source,settings)
            if data.get('layout') and not data.get('release_locked') and all(settings.get(k)==old_layout.get(k) for k in ('direction','siblings','stagger')):
                positions = old
            if data.get('paper'):
                # Keep the chosen direction; optimize sibling bands for page fit.
                paper={**data['paper'],'mode':'fit'}
                candidates=[]
                for count in (2,3,4,6,8):
                    candidate_settings={**settings,'siblings':count,'font_size':finite(paper.get('font_size',settings.get('font_size',22)),10,1000)}
                    candidate,_=arrange(self.engine.state(),source,candidate_settings)
                    candidates.append((sheet(paper,candidate)['scale'],candidate,candidate_settings))
                _,positions,settings=max(candidates,key=lambda candidate:candidate[0])
            self.view['positions'],self.view['layout'] = positions,settings
        elif action in ('move', 'lock', 'branch'):
            identifier = data.get('id')
            if identifier not in old:
                raise ValueError('Persona inesistente.')
            if action == 'move':
                self.view['positions'] = place(old, identifier, data.get('x'), data.get('y'),snap=data.get('snap',True),extra_targets=family_alignment(self.engine.state(),old,identifier,self.view['layout'].get('direction')=='horizontal'))
            elif action == 'lock':
                self.view['positions'][identifier]['locked'] = bool(data.get('locked'))
            else:
                dx, dy = finite(data.get('dx'), -10000, 10000), finite(data.get('dy'), -10000, 10000)
                descendants = {identifier}
                changed = True
                families = self.engine.state()['families']
                while changed:
                    before = len(descendants)
                    for f in families:
                        if descendants.intersection(f['parents']):
                            descendants.update(f['children'])
                    changed = len(descendants) != before
                # The entire branch translates rigidly. Reject collisions with outsiders.
                from .geometry import overlaps
                moved = {i:{**old[i],'x':old[i]['x']+dx,'y':old[i]['y']+dy,'locked':True} for i in descendants}
                if any(overlaps(v,q) for v in moved.values() for i,q in old.items() if i not in descendants):
                    raise ValueError('Il ramo si sovrapporrebbe ad altre persone: scegli più spazio.')
                self.view['positions'].update(moved)
        elif action in ('undo','redo'):
            source, dest = (self.past,self.future) if action == 'undo' else (self.future,self.past)
            if not source:
                raise ValueError('Non ci sono azioni da annullare o ripetere.')
            item = source[-1]
            if item['kind'] == 'genealogy':
                getattr(self.engine, action)()
            source.pop()
            dest.append({'kind':item['kind'], 'positions':old,'layout':old_layout})
            self.view['positions'] = item['positions']
            self.view['layout'] = item.get('layout',old_layout)
        else:
            raise ValueError('Azione sconosciuta.')
        if action not in ('undo','redo'):
            self.past.append({'kind':kind, 'positions':old,'layout':old_layout})
            self.past = self.past[-50:]
            self.future.clear()
        self.view['revision'] += 1
        self.refresh()
        return self.state()

    def backup(self):
        tree = self.engine.export()
        name = time.strftime('radici-%Y%m%d-%H%M%S-')+uuid.uuid4().hex[:6]+'.zip'
        target = self.backups/name
        temp = target.with_suffix('.partial')
        checksums = {}
        try:
            with zipfile.ZipFile(temp, 'w', zipfile.ZIP_DEFLATED) as z:
                def write(name, content):
                    checksums[name] = hashlib.sha256(content).hexdigest()
                    z.writestr(name, content)
                write('tree.gramps', tree)
                write('workspace.json', json.dumps(self.view, ensure_ascii=False).encode())
                for f in sorted(self.media.rglob('*')):
                    if f.relative_to(self.media).parts[0] in getattr(self,'excluded_media_dirs',set()):
                        continue
                    if f.is_file() and not f.is_symlink() and self.media.resolve() in f.resolve().parents:
                        write('media/'+f.relative_to(self.media).as_posix(), f.read_bytes())
                z.writestr('manifest.json', json.dumps({'version':1,'gramps':'6.0.8','sha256':checksums}))
            os.replace(temp, target)
            self.backup_error = None
            self.last_backup = time.monotonic()
            keep = max(2, int(os.getenv('BACKUP_KEEP','14')))
            for obsolete in sorted(self.backups.glob('radici-*.zip'), key=lambda p:p.stat().st_mtime, reverse=True)[keep:]:
                obsolete.unlink()
            return name
        finally:
            temp.unlink(missing_ok=True)

    def import_tree(self, data, revision):
        self.check_revision({'revision':revision})
        self.backup()
        self.engine.import_empty(data)
        self.view['positions'] = {}
        self.view['revision'] += 1
        self.past.clear()
        self.future.clear()
        self.refresh()

    def print_tree(self, config, fmt):
        state = self.engine.state()
        if config.get('document')=='album':
            from .album import album
            return album(state,config,fmt)
        if config.get('document','single')!='single':raise ValueError('Tipo di stampa non valido.')
        original_positions=self.view['positions']
        root=config.get('root_id')
        if root:
            ids={p['id'] for p in state['people']}
            if root not in ids:raise ValueError('Seleziona la persona da cui inizia il ramo.')
            descendants={root}; changed=True
            while changed:
                before=len(descendants)
                for f in state['families']:
                    if descendants.intersection(f['parents']):descendants.update(f['children'])
                changed=len(descendants)>before
            families=[f for f in state['families'] if descendants.intersection(f['parents'])]
            included=descendants | {p for f in families for p in f['parents']}
            state={**state,'people':[p for p in state['people'] if p['id'] in included],
                   'families':[{**f,'parents':[p for p in f['parents'] if p in included],
                                'children':[p for p in f['children'] if p in included]} for f in families]}
            original_positions={i:p for i,p in original_positions.items() if i in included}
        positions,style = prepare_print(state,original_positions,config,self.view['layout'])
        s = sheet(config, positions)
        if s['overflow'] and fmt in ('pdf','svg'):
            raise ValueError('Il foglio è troppo piccolo per questi caratteri. Stampa un solo ramo o scegli un formato più grande.')
        if fmt == 'preview':
            preview=svg(state,original_positions,config,True,self.view['layout'])
            return {'svg':preview, 'sheet':{**s,'routing_warning':'data-routing-warning' in preview,'composition':config.get('composition','as_seen'),'direction':style.get('direction','vertical'),'people':len(state['people'])}}
        return pdf(state,original_positions,config,self.view['layout']) if fmt == 'pdf' else svg(state,original_positions,config,settings=self.view['layout']).encode()
