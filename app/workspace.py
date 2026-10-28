"""Separate trees, each with its own native database, layout, media and history."""
import copy
import json
import uuid
from pathlib import Path
from .service import Service, atomic_json


class Workspace:
    def __init__(self,data,media,backups,demo=False):
        self.root,self.media_root,self.backup_root=map(Path,(data,media,backups))
        self.root.mkdir(parents=True,exist_ok=True)
        self.demo=demo
        self.file=self.root/'trees.json'
        self.index=json.loads(self.file.read_text('utf-8')) if self.file.exists() else {'active':'original','trees':[{'id':'original','name':'Il mio albero'}]}
        self.services={}
        self.current=self._open(self.index['active'])
        atomic_json(self.file,self.index)

    def _open(self,identifier):
        if identifier not in {t['id'] for t in self.index['trees']}:
            raise ValueError('Albero inesistente.')
        if identifier not in self.services:
            original=identifier=='original'
            data=self.root if original else self.root/'trees'/identifier
            media=self.media_root if original else self.media_root/'_radici_trees'/identifier
            backups=self.backup_root if original else self.backup_root/'_radici_trees'/identifier
            if self.demo:
                from .demo import DemoEngine
                engine=DemoEngine(empty=not original)
                saved=data/'demo.json'
                if saved.exists():engine.data=json.loads(saved.read_text('utf-8'))
            else:
                from .engine import Engine
                engine=Engine(data/'tree',media)
            service=Service(engine,data,media,backups,self.demo)
            if original:
                service.excluded_media_dirs={'_radici_trees'}
            self.services[identifier]=service
        return self.services[identifier]

    def state(self):
        return {**self.current.state(),'tree_id':self.index['active'],'trees':copy.deepcopy(self.index['trees']),'portable':self.__dict__.get('portable',False),'desktop':self.__dict__.get('desktop',False)}

    def check_tree(self,identifier):
        if identifier!=self.index['active']:
            raise ValueError('L’albero aperto è cambiato in un’altra scheda. Ricarica la pagina prima di continuare.')

    def create(self,name):
        name=str(name).strip()
        if not name or len(name)>100:
            raise ValueError('Dai un nome all’albero (da 1 a 100 caratteri).')
        if any(t['name'].casefold()==name.casefold() for t in self.index['trees']):
            raise ValueError('Esiste già un albero con questo nome. Scegline un altro.')
        identifier=uuid.uuid4().hex
        old=copy.deepcopy(self.index)
        self.index['trees'].append({'id':identifier,'name':name})
        try:
            service=self._open(identifier)
            self.index['active']=identifier
            atomic_json(self.file,self.index)
            self.current=service
        except Exception:
            self.index=old
            if identifier in self.services:
                self.services.pop(identifier).engine.close()
            raise
        return self.state()

    def switch(self,identifier):
        service=self._open(identifier)
        updated={**self.index,'active':identifier}
        atomic_json(self.file,updated)
        self.index=updated
        self.current=service
        return self.state()

    def command(self,action,data):
        self.check_tree(data.get('tree_id'))
        self.current.command(action,data)
        return self.state()

    def presentation(self,data):
        self.check_tree(data.get('tree_id'))
        return self.current.presentation(data)

    def close(self):
        for service in self.services.values():
            service.engine.close()

    def __getattr__(self,name):
        return getattr(self.current,name)
