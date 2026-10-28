"""Only official Gramps object/transaction/import/export APIs touch genealogy."""
import gzip
import io
import os
import shutil
import tempfile
import uuid
from pathlib import Path
from xml.etree import ElementTree as ET


def validate_xml(data):
    if data.startswith(b'\x1f\x8b'):
        with gzip.GzipFile(fileobj=io.BytesIO(data)) as f:
            data = f.read(32*1024*1024+1)
    if len(data) > 32*1024*1024:
        raise ValueError("XML troppo grande: massimo 32 MB decompressi.")
    # Official exports contain a simple external DOCTYPE. No entities or subsets.
    if b'<!ENTITY' in data.upper() or b'<![' in data.upper():
        raise ValueError("Entità e sottoinsiemi XML non ammessi.")
    root = ET.fromstring(data)
    if root.tag != '{http://gramps-project.org/xml/1.7.2/}database':
        raise ValueError("Serve un export Gramps XML 1.7.2 (.gramps o .xml), non GEDCOM o .gpkg.")
    return data


def _family_roles(family):
    roles = family.get('parent_roles')
    return roles if roles is not None else {p: index for index, p in enumerate(family['parents'])}


def _add_plan(state, data):
    """Validate the whole relationship before writing any person or family."""
    people = {p['id']: p for p in state['people']}
    families = {f['id']: f for f in state['families']}
    relation = data.get('relation', 'independent')
    if relation not in ('independent', 'parent', 'child', 'partner'):
        raise ValueError('Relazione non valida.')
    target, existing = data.get('target'), data.get('existing_id')
    if relation == 'independent': target = None
    if relation != 'independent' and (not isinstance(target, str) or target not in people):
        raise ValueError('Seleziona la persona di riferimento.')
    if existing:
        if not isinstance(existing, str) or existing not in people:
            raise ValueError('La persona da collegare non esiste in questo albero.')
        if relation == 'independent':
            raise ValueError('Questa persona è già presente: scegli il legame da aggiungere.')
        if existing == target:
            raise ValueError('Una persona non può essere collegata a sé stessa.')
        person = None
    else:
        first, surname = str(data.get('first', '')).strip(), str(data.get('surname', '')).strip()
        try: gender = int(data.get('gender', 2))
        except (ValueError, TypeError): raise ValueError('Sesso non valido.') from None
        year = str(data.get('birth', '')).strip()
        if not first or len(first) > 100 or len(surname) > 100:
            raise ValueError('Inserisci il nome (massimo 100 caratteri).')
        if gender not in (0, 1, 2):
            raise ValueError('Sesso non valido.')
        if year and (not year.isdigit() or not 1 <= int(year) <= 9999):
            raise ValueError('Anno di nascita non valido.')
        person = dict(first=first, surname=surname, gender=gender, birth=year)
    family_id = data.get('family')
    if family_id and (not isinstance(family_id, str) or family_id not in families):
        raise ValueError('Famiglia inesistente.')
    new_family = data.get('new_family', False)
    if not isinstance(new_family, bool):
        raise ValueError('La scelta della nuova famiglia non è valida.')
    if family_id and new_family:
        raise ValueError('Scegli una famiglia esistente oppure una nuova famiglia.')
    if relation == 'independent' and (family_id or new_family):
        raise ValueError('Famiglia non applicabile.')
    family = families.get(family_id)
    if relation in ('child', 'parent') and not family and not new_family:
        key = 'parents' if relation == 'child' else 'children'
        choices = [f for f in state['families'] if target in f[key]]
        if len(choices) > 1:
            raise ValueError('Questa persona ha più famiglie: scegli con quale unione collegare il legame.')
        family = choices[0] if choices else None
    if family:
        key = 'children' if relation == 'parent' else 'parents'
        if target not in family[key]:
            raise ValueError('La persona di riferimento non appartiene alla famiglia scelta nel ruolo richiesto.')
        if relation in ('parent', 'partner') and len(family['parents']) >= 2:
            raise ValueError('Questa famiglia ha già due genitori o coniugi: scegli una nuova unione.')
        if existing and existing in family['parents'] + family['children']:
            raise ValueError('Questa persona è già collegata alla famiglia scelta.')
    reltype = data.get('child_type', 'unknown')
    if reltype not in ('unknown', 'birth', 'adopted'):
        raise ValueError('Tipo di filiazione non valido.')
    default_slot = 'mother' if people.get(target, {}).get('gender') == 0 else 'father'
    if relation == 'parent':
        default_slot = 'mother' if family and 0 in _family_roles(family).values() else 'father'
        if not family and (people[existing].get('gender', 2) if existing else person['gender']) == 0:
            default_slot = 'mother'
    slot = data.get('slot', default_slot)
    if slot not in ('father', 'mother'):
        raise ValueError('Scegli il ruolo del genitore.')
    if family and relation == 'parent' and (0 if slot == 'father' else 1) in _family_roles(family).values():
        raise ValueError('Questo ruolo di genitore è già occupato nella famiglia.')
    if family and relation == 'partner':
        slot = 'father' if _family_roles(family)[target] == 0 else 'mother'
    if existing and relation == 'partner' and any(target in f['parents'] and existing in f['parents'] for f in state['families']):
        raise ValueError('Queste due persone sono già collegate come coniugi o compagni.')
    if existing:
        if relation == 'child':
            edges = [(p, existing) for p in (family['parents'] if family else [target])]
        elif relation == 'parent':
            edges = [(existing, child) for child in (family['children'] if family else [target])]
        else:
            edges = [(existing, child) for child in family['children']] if family else []
        graph = {p: set() for p in people}
        for f in state['families']:
            for parent in f['parents']: graph.setdefault(parent, set()).update(f['children'])
        for parent, child in edges:
            pending, visited = [child], set()
            while pending:
                item = pending.pop()
                if item == parent:
                    raise ValueError('Questo legame renderebbe una persona antenata di sé stessa. Controlla la famiglia scelta.')
                if item not in visited:
                    visited.add(item); pending.extend(graph.get(item, ()))
            graph.setdefault(parent, set()).add(child)
    return dict(relation=relation, target=target, existing_id=existing,
                family=family['id'] if family else None, slot=slot,
                child_type=reltype, person=person)


class Engine:
    def __init__(self, directory, media_path='/media'):
        from gramps.version import VERSION
        if VERSION != '6.0.8':
            raise RuntimeError('Richiesto esattamente Gramps 6.0.8')
        from gramps.plugins.db.dbapi.sqlite import SQLite
        self.root = Path(directory)
        self.media_path = str(media_path)
        self.root.mkdir(parents=True, exist_ok=True)
        self.db = SQLite()
        self.db.load(str(self.root))
        self.db.set_mediapath(self.media_path)

    def state(self):
        people, families = [], []
        for p in self.db.iter_people():
            n = p.get_primary_name()
            birth, death = '', ''
            for ref, label in ((p.get_birth_ref(), 'birth'), (p.get_death_ref(), 'death')):
                if ref:
                    e = self.db.get_event_from_handle(ref.ref)
                    if e:
                        year = e.get_date_object().get_year()
                        if label == 'birth':
                            birth = str(year) if year else ''
                        else:
                            death = str(year) if year else ''
            people.append({'id': p.handle, 'gramps_id': p.gramps_id,
                           'first': n.get_first_name(), 'surname': n.get_surname(),
                           'primary_surname': n.get_primary_surname().get_surname(),
                           'years': f'{birth or "?"} – {death}' if death else birth or '',
                           'gender': p.get_gender()})
        for f in self.db.iter_families():
            families.append({'id': f.handle, 'gramps_id': f.gramps_id,
                             'parents': [h for h in (f.get_father_handle(), f.get_mother_handle()) if h],
                             'children': [r.ref for r in f.get_child_ref_list()],
                             'parent_roles': {h:slot for h,slot in ((f.get_father_handle(),0),(f.get_mother_handle(),1)) if h},
                             'relations': {r.ref: [int(r.get_father_relation()), int(r.get_mother_relation())] for r in f.get_child_ref_list()}})
        people.sort(key=lambda p:(p['gramps_id'],p['id']))
        families.sort(key=lambda f:(f['gramps_id'],f['id']))
        return {'people': people, 'families': families}

    def add(self, data):
        from gramps.gen.db import DbTxn
        from gramps.gen.lib import Person, Name, Surname, Family, ChildRef, ChildRefType, Event, EventType, EventRef, Date, FamilyRelType
        plan = _add_plan(self.state(), data)
        relation, target, slot = plan['relation'], plan['target'], plan['slot']
        family = self.db.get_family_from_handle(plan['family']) if plan['family'] else None
        anchor = self.db.get_person_from_handle(target) if relation != 'independent' else None
        p = self.db.get_person_from_handle(plan['existing_id']) if plan['existing_id'] else Person()
        values = plan['person']
        types = {'unknown': ChildRefType.UNKNOWN, 'birth': ChildRefType.BIRTH, 'adopted': ChildRefType.ADOPTED}
        if values:
            p.set_gender(values['gender'])
            n, sn = Name(), Surname()
            n.set_first_name(values['first']); sn.set_surname(values['surname']); n.add_surname(sn)
            p.set_primary_name(n)
        with DbTxn('Aggiungi persona e parentela - Radici', self.db) as txn:
            if values:
                self.db.add_person(p, txn)
                if values['birth']:
                    e, date, ref = Event(), Date(), EventRef()
                    e.set_type(EventType.BIRTH)
                    date.set_yr_mon_day(int(values['birth']), 0, 0); e.set_date_object(date)
                    self.db.add_event(e, txn)
                    ref.set_reference_handle(e.handle); p.add_event_ref(ref); p.set_birth_ref(ref)
            if relation != 'independent':
                is_new = family is None
                if is_new:
                    family = Family(); family.set_relationship(FamilyRelType.UNKNOWN)
                    self.db.add_family(family, txn)
                if relation == 'partner':
                    getattr(family, f'set_{slot}_handle')(anchor.handle)
                    getattr(family, f'set_{"mother" if slot == "father" else "father"}_handle')(p.handle)
                    anchor.add_family_handle(family.handle); p.add_family_handle(family.handle)
                    for ref in family.get_child_ref_list():
                        getattr(ref, f'set_{"mother" if slot == "father" else "father"}_relation')(ChildRefType.UNKNOWN)
                elif relation == 'child':
                    if is_new:
                        getattr(family, f'set_{slot}_handle')(anchor.handle)
                        anchor.add_family_handle(family.handle)
                    ref = ChildRef(); ref.set_reference_handle(p.handle)
                    ref.set_father_relation(types[plan['child_type']] if family.get_father_handle() else ChildRefType.UNKNOWN)
                    ref.set_mother_relation(types[plan['child_type']] if family.get_mother_handle() else ChildRefType.UNKNOWN)
                    family.add_child_ref(ref); p.add_parent_family_handle(family.handle)
                elif relation == 'parent':
                    getattr(family, f'set_{slot}_handle')(p.handle)
                    p.add_family_handle(family.handle)
                    if is_new:
                        ref = ChildRef(); ref.set_reference_handle(anchor.handle)
                        ref.set_father_relation(ChildRefType.UNKNOWN); ref.set_mother_relation(ChildRefType.UNKNOWN)
                        family.add_child_ref(ref); anchor.add_parent_family_handle(family.handle)
                    for ref in family.get_child_ref_list():
                        if ref.ref == anchor.handle:
                            getattr(ref, f'set_{slot}_relation')(types[plan['child_type']])
                self.db.commit_family(family, txn); self.db.commit_person(anchor, txn)
            self.db.commit_person(p, txn)
        return p.handle

    def unlink(self, data):
        from gramps.gen.db import DbTxn
        from gramps.gen.lib import ChildRefType
        if data.get('confirm') is not True:
            raise ValueError('Conferma la rimozione del solo legame familiare.')
        person = self.db.get_person_from_handle(data.get('id'))
        family = self.db.get_family_from_handle(data.get('family'))
        if not person or not family:
            raise ValueError('Persona o famiglia inesistente.')
        slots = [slot for slot in ('father', 'mother') if getattr(family, f'get_{slot}_handle')() == person.handle]
        child = any(ref.ref == person.handle for ref in family.get_child_ref_list())
        if not slots and not child:
            raise ValueError('Questa persona non appartiene alla famiglia scelta.')
        with DbTxn('Rimuovi solo legame familiare - Radici', self.db) as txn:
            for slot in slots: getattr(family, f'set_{slot}_handle')(None)
            for ref in family.get_child_ref_list():
                for slot in slots: getattr(ref, f'set_{slot}_relation')(ChildRefType.UNKNOWN)
            if slots: person.remove_family_handle(family.handle)
            if child:
                family.remove_child_handle(person.handle)
                person.remove_parent_family_handle(family.handle)
            self.db.commit_family(family, txn); self.db.commit_person(person, txn)
        return person.handle

    def edit(self, data):
        from gramps.gen.db import DbTxn
        p = self.db.get_person_from_handle(data.get('id'))
        if not p:
            raise ValueError('Persona inesistente.')
        first, surname = str(data.get('first','')).strip(), str(data.get('surname','')).strip()
        gender = int(data.get('gender',2))
        if not first or len(first)>100 or len(surname)>100 or gender not in (0,1,2):
            raise ValueError('Controlla nome, cognome e sesso nel registro.')
        n = p.get_primary_name()
        n.set_first_name(first)
        n.get_primary_surname().set_surname(surname)
        p.set_gender(gender)
        with DbTxn('Modifica nome - Radici',self.db) as txn:
            self.db.commit_person(p,txn)

    def export(self):
        from gramps.cli.user import User
        from gramps.plugins.export.exportxml import export_data
        def fail(title, message=''):
            raise ValueError(f'{title}: {message}')
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'tree.gramps'
            if not export_data(self.db, str(path), User(error=fail)):
                raise ValueError('Esportazione Gramps fallita.')
            return path.read_bytes()

    def delete(self, data):
        from gramps.gen.db import DbTxn
        person = self.db.get_person_from_handle(data.get('id'))
        if not person:
            raise ValueError('Persona inesistente.')
        # Upstream cleans family roles, child references, associations and
        # backlinks. Events/sources/media are retained, not recursively deleted.
        with DbTxn('Elimina persona - Radici',self.db) as txn:
            self.db.delete_person_from_database(person,txn)

    def import_empty(self, data):
        from gramps.cli.user import User
        from gramps.plugins.importer.importxml import importData
        if any(getattr(self.db, 'get_number_of_'+kind)() for kind in ('people','families','events','places','sources','citations','repositories','media','notes','tags')):
            raise ValueError('Importazione disponibile solo su archivio vuoto. Usa un nuovo volume per un altro albero.')
        xml = validate_xml(data)
        def fail(title, message=''):
            raise ValueError(f'{title}: {message}')
        staging = self.root.parent/('staging-'+uuid.uuid4().hex)
        staged = Engine(staging,self.media_path)
        try:
            staged.db.set_feature('skip-import-additions', True)
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp)/'import.xml'
                path.write_bytes(xml)
                if importData(staged.db, str(path), User(error=fail)) is None:
                    raise ValueError('Importazione non riuscita.')
            staged.db.set_mediapath(self.media_path)
            staged.close()
            self.close()
            old = self.root.with_name('previous-'+uuid.uuid4().hex)
            os.replace(self.root, old)
            try:
                os.replace(staging, self.root)
            except Exception:
                os.replace(old, self.root)
                self.__init__(self.root,self.media_path)
                raise
            self.__init__(self.root,self.media_path)
            # Previous empty DB is retained for recovery, never overwritten.
        finally:
            if staged.db.is_open():
                staged.close()
            if staging.exists():
                shutil.rmtree(staging)

    def undo(self):
        self.db.undo()

    def redo(self):
        self.db.redo()

    def close(self):
        if self.db.is_open():
            self.db.close()
