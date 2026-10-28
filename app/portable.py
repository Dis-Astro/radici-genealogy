"""Windows removable-drive host. All genealogy access uses the official Engine."""
import json
import hashlib
import threading
import os
import secrets
import sys
import time
import traceback
import uuid
import zipfile
from pathlib import Path


def backup_signature(root):
    digest=hashlib.sha256()
    for file in sorted((root/'Dati').rglob('*')):
        if 'Origine-prototipo' in file.parts or not file.is_file():continue
        if file.name in ('trees.json','workspace.json'):
            digest.update(file.relative_to(root).as_posix().encode());digest.update(file.read_bytes())
        elif file.name=='sqlite.db':
            stat=file.stat();digest.update((file.relative_to(root).as_posix()+str(stat.st_size)+str(stat.st_mtime_ns)).encode())
    for file in sorted((root/'Foto').rglob('*')):
        if file.is_file() and not file.is_symlink():
            stat=file.stat();digest.update((file.relative_to(root).as_posix()+str(stat.st_size)+str(stat.st_mtime_ns)).encode())
    return digest.hexdigest()


class BackupCancelled(Exception):
    pass


def complete_backup(workspace, root, force=True, cancelled=None):
    from .service import atomic_json
    def check_cancel():
        if cancelled and cancelled():raise BackupCancelled()
    check_cancel()
    signature=backup_signature(root)
    record=root/'Backup/ultima-copia.json'
    if not force and record.exists():
        try:previous=json.loads(record.read_text('utf-8'))
        except (OSError,ValueError):previous={}
        if not isinstance(previous,dict):previous={}
        if previous.get('signature')==signature and (root/'Backup'/previous.get('file','')).is_file():return previous['file']
    target=root/'Backup'/('Radici-completa-'+time.strftime('%Y%m%d-%H%M%S-')+uuid.uuid4().hex[:5]+'.zip')
    temporary=target.with_suffix('.partial')
    try:
        with zipfile.ZipFile(temporary,'w',zipfile.ZIP_DEFLATED,compresslevel=1) as archive:
            archive.writestr('alberi.json',json.dumps(workspace.index,ensure_ascii=False))
            for tree in workspace.index['trees']:
                check_cancel()
                service=workspace._open(tree['id'])
                archive.writestr(tree['id']+'/albero.gramps',service.engine.export())
                archive.writestr(tree['id']+'/posizioni.json',json.dumps(service.view,ensure_ascii=False))
            for path in (root/'Foto').rglob('*'):
                check_cancel()
                if path.is_file() and not path.is_symlink():
                    info=zipfile.ZipInfo.from_file(path,path.relative_to(root).as_posix())
                    info.compress_type=zipfile.ZIP_STORED if path.suffix.lower() in {'.jpg','.jpeg','.png','.webp','.gif','.pdf','.mp4','.mp3','.zip','.gramps'} else zipfile.ZIP_DEFLATED
                    with path.open('rb') as source,archive.open(info,'w',force_zip64=True) as destination:
                        while chunk:=source.read(256*1024):
                            check_cancel();destination.write(chunk)
        check_cancel()
        with temporary.open('r+b') as stream:os.fsync(stream.fileno())
        os.replace(temporary,target)
        atomic_json(record,{'signature':backup_signature(root),'file':target.name})
        return target.name
    finally:temporary.unlink(missing_ok=True)


def close_workspace(workspace, proxy):
    """Edits are already committed; close only the databases actually opened."""
    started=time.monotonic()
    proxy.ready=False;proxy.phase='closing';proxy.message='Chiusura dell’archivio…'
    proxy.finish()
    if workspace is not None:workspace.close()
    proxy.phase='closed';proxy.message='Archivio chiuso. Puoi rimuovere la chiavetta.'
    print('Archivi chiusi in',round(time.monotonic()-started,3),'secondi',flush=True)


def main():
    from .server import build_server
    from .workspace import Workspace
    from .portable_rpc import OwnerProxy,ResponsiveServer
    import faulthandler
    root=Path(os.environ['RADICI_PORTABLE_ROOT']);control=root/'Impostazioni'
    desktop=os.environ.get('RADICI_DESKTOP')=='1'
    proxy=OwnerProxy();ready=control/'pronto.txt';service=None
    server=build_server(proxy,secrets.token_urlsafe(32),('127.0.0.1',0),
                        bootstrap_token=secrets.token_urlsafe(32),portable_export_dir=root/'Stampe',
                        server_type=ResponsiveServer,portable_control=proxy)
    url='http://127.0.0.1:'+str(server.server_address[1])+'/?avvio='+server.bootstrap_token
    ready.write_text(url,encoding='utf-8')
    listener=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.1},daemon=True)
    listener.start()
    try:
        proxy.phase='database';proxy.message='Apertura dell’archivio sul PC…' if desktop else 'Apertura dell’archivio sulla chiavetta…'
        service=Workspace(root/'Dati',root/'Foto',root/'Backup',False)
        service.portable=True;service.desktop=desktop;proxy.target=service;proxy.ready=True
        proxy.phase='ready';proxy.message='Pronto. Le modifiche confermate si salvano subito sul PC.' if desktop else 'Pronto. Le modifiche confermate si salvano subito sulla chiavetta.'
        faulthandler.cancel_dump_traceback_later()
        print('Avvio completato in',round(time.monotonic()-proxy.created,3),'secondi',flush=True)
        next_flags=0
        while not proxy.stop.is_set():
            proxy.run_one(.2)
            if time.monotonic()>=next_flags:
                next_flags=time.monotonic()+2
                if (control/'chiudi.flag').exists():break
                if (control/'backup.flag').exists():proxy.backup_requested.set()
            if proxy.backup_requested.is_set():
                proxy.backup_requested.clear();(control/'backup.flag').unlink(missing_ok=True)
                proxy.phase='backup';proxy.message='Copia di sicurezza in corso…'
                try:
                    name=complete_backup(service,root,cancelled=proxy.stop.is_set)
                    proxy.message='Copia creata nella cartella Backup: '+name
                except BackupCancelled:
                    proxy.message='Copia interrotta per chiudere. I dati dell’albero sono già salvati.'
                except Exception:
                    traceback.print_exc();proxy.message='Copia non riuscita. Controlla lo spazio sulla chiavetta.'
                if not proxy.stop.is_set():proxy.phase='ready'
        proxy.phase='closing';proxy.message='Salvataggio finale in corso…'
    except BaseException:
        proxy.phase='error';proxy.message='Avvio non riuscito. Consulta il registro di Radici.'
        traceback.print_exc()
        raise
    finally:
        faulthandler.dump_traceback_later(15,repeat=False,file=sys.stderr)
        try:close_workspace(service,proxy)
        finally:
            faulthandler.cancel_dump_traceback_later()
            server.shutdown();server.server_close();listener.join(timeout=2)
            ready.unlink(missing_ok=True);(control/'chiudi.flag').unlink(missing_ok=True)


if __name__=='__main__':main()
