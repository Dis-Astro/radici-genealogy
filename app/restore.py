"""Offline restore into NEW, empty volumes. No direct database writes."""
import hashlib
import json
import os
import sys
import zipfile
from pathlib import Path, PurePosixPath
from .engine import Engine, validate_xml
from .service import atomic_json


def restore(archive, data, media):
    data, media = Path(data), Path(media)
    if any(data.iterdir()) or any(media.iterdir()):
        raise ValueError('Ripristino solo su volumi dati e media completamente vuoti.')
    with zipfile.ZipFile(archive) as z:
        if len(z.infolist()) > 10000 or sum(i.file_size for i in z.infolist()) > 2*1024**3:
            raise ValueError('Backup oltre i limiti di ripristino: 10000 file / 2 GB.')
        names = z.namelist()
        if len(names) != len(set(names)):
            raise ValueError('Nomi duplicati nel backup.')
        manifest = json.loads(z.read('manifest.json'))
        if manifest.get('version') != 1 or manifest.get('gramps') != '6.0.8':
            raise ValueError('Versione backup non supportata.')
        expected = manifest['sha256']
        if set(names) != set(expected)|{'manifest.json'}:
            raise ValueError('Manifest incompleto.')
        payload = {}
        for name, checksum in expected.items():
            parts = PurePosixPath(name)
            if '\\' in name or ':' in name or parts.is_absolute() or '..' in parts.parts or not (name in ('tree.gramps','workspace.json') or name.startswith('media/')):
                raise ValueError('Percorso non sicuro nel backup.')
            content = z.read(name)
            if hashlib.sha256(content).hexdigest() != checksum:
                raise ValueError('Backup danneggiato: '+name)
            payload[name] = content
        validate_xml(payload['tree.gramps'])
        view = json.loads(payload['workspace.json'])
        from .geometry import finite
        for pos in view['positions'].values():
            finite(pos['x'],-200000,200000)
            finite(pos['y'],-200000,200000)
        engine = Engine(data/'tree')
        try:
            engine.import_empty(payload['tree.gramps'])
        finally:
            engine.close()
        atomic_json(data/'workspace.json',view)
        for name, content in payload.items():
            if name.startswith('media/'):
                target = media.joinpath(*PurePosixPath(name).parts[1:])
                target.parent.mkdir(parents=True,exist_ok=True)
                target.write_bytes(content)


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('Uso: python3 -m app.restore /backups/nome-backup.zip')
    restore(sys.argv[1],os.getenv('DATA_DIR','/data'),os.getenv('MEDIA_DIR','/media'))
    print('Ripristino completato. Avvia il servizio e verifica l’albero.')
