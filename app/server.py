"""Single-threaded local HTTP service: Gramps SQLite stays in its owner thread."""
import base64
import hashlib
import hmac
import json
import mimetypes
import os
import secrets
import signal
import time
import uuid
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
from .service import Service

STATIC = Path(__file__).parent/'static'


def build_server(service, password, address=('127.0.0.1', 8787), allowed_hosts=None, bootstrap_token=None, portable_export_dir=None, server_type=HTTPServer, portable_control=None):
    if len(password) < 12:
        raise ValueError('La password deve avere almeno 12 caratteri.')
    salt = secrets.token_bytes(16)
    expected = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1)
    sessions, failures = {}, []
    allowed_hosts = allowed_hosts or {'127.0.0.1','localhost','::1'}

    class Handler(BaseHTTPRequestHandler):
        server_version = 'Radici/0.1'

        def log_message(self, fmt, *args):
            # No request URLs, tokens, names or genealogy in logs.
            pass

        def send(self, status, body=b'', content_type='application/json; charset=utf-8', headers=None):
            if isinstance(body, (dict,list)):
                body = json.dumps(body, ensure_ascii=False).encode()
            if isinstance(body,str):
                body = body.encode()
            self.send_response(status)
            self.send_header('Content-Type',content_type)
            self.send_header('Content-Length',str(len(body)))
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Referrer-Policy','no-referrer')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            for k,v in (headers or {}).items():
                self.send_header(k,v)
            self.end_headers()
            try:self.wfile.write(body)
            except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError):pass

        def valid_host(self):
            try:
                return urlsplit('http://'+self.headers.get('Host','')).hostname in allowed_hosts
            except ValueError:
                return False

        def session(self):
            try:
                cookies = SimpleCookie(self.headers.get('Cookie',''))
                token = cookies.get(cookie_name)
                entry = sessions.get(token.value) if token else None
                if entry and entry['expires'] > time.monotonic():
                    return entry
            except Exception:
                pass
            return None

        def do_GET(self):
            if not self.valid_host():
                return self.send(403,{'error':'Host non consentito.'})
            path = urlsplit(self.path).path
            if path=='/' and bootstrap_token:
                supplied=parse_qs(urlsplit(self.path).query).get('avvio',[''])[0]
                if supplied and hmac.compare_digest(supplied,bootstrap_token):
                    token,csrf=secrets.token_urlsafe(32),secrets.token_urlsafe(32)
                    sessions[token]={'csrf':csrf,'expires':time.monotonic()+8*3600}
                    return self.send(303,b'',headers={'Location':'/','Set-Cookie':f'{cookie_name}={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800'})

            if path=='/api/portable/status' and portable_control:
                if not hmac.compare_digest(self.headers.get('X-Radici-Control',''),bootstrap_token):
                    return self.send(403,{'error':'Accesso non consentito.'})
                return self.send(200,portable_control.status())
            if path == '/health':
                return self.send(200,{'status':'ok','engine':'demo' if service.demo else 'Gramps 6.0.8', 'backup_ok':not bool(service.backup_error)})
            if path == '/api/session':
                entry = self.session()
                return self.send(200, {'authenticated':bool(entry),'csrf':entry['csrf'] if entry else None,'demo':service.demo,'portable':bool(portable_export_dir),'desktop':os.environ.get('RADICI_DESKTOP')=='1'})
            if path.startswith('/api/'):
                if not self.session():
                    return self.send(401,{'error':'Accedi per aprire il tuo albero.'})
                if path == '/api/state':
                    return self.send(200,service.state())
                if path == '/api/export':
                    try:
                        result=service.engine.export()
                        if portable_export_dir:
                            name='albero-'+time.strftime('%Y%m%d-%H%M%S-')+uuid.uuid4().hex[:5]+'.gramps'
                            (Path(portable_export_dir)/name).write_bytes(result)
                            return self.send(200,{'saved':name})
                        return self.send(200,result,'application/x-gramps',{'Content-Disposition':'attachment; filename="albero.gramps"'})
                    except ValueError as e:
                        return self.send(400,{'error':str(e)})
                return self.send(404,{'error':'Risorsa non trovata.'})
            files = {'/':'index.html','/app.js':'app.js','/style.css':'style.css'}
            if path not in files:
                return self.send(404,{'error':'Risorsa non trovata.'})
            file = STATIC/files[path]
            return self.send(200,file.read_bytes(),mimetypes.guess_type(file.name)[0]+'; charset=utf-8')

        def do_POST(self):
            try:
                length = int(self.headers.get('Content-Length','0'))
                if not 0 < length <= 12*1024*1024:
                    return self.send(413,{'error':'Richiesta troppo grande (massimo 12 MB).'} )
                # Consume the bounded request before rejecting its headers. Closing
                # a socket with unread POST bytes can reset the response on Windows.
                # No JSON is interpreted and no action runs before the checks below.
                raw = self.rfile.read(length)
                if not self.valid_host():
                    return self.send(403,{'error':'Host non consentito.'})
                # Same-origin policy also rejects cross-site form posts and DNS rebinding.
                origin = self.headers.get('Origin')
                if origin and origin != 'http://'+self.headers.get('Host'):
                    return self.send(403,{'error':'Origine non consentita.'})
                if self.headers.get('Content-Type','').split(';')[0] != 'application/json':
                    return self.send(415,{'error':'Richiesto JSON.'})
                data = json.loads(raw)
                if not isinstance(data,dict):
                    raise ValueError('Richiesta non valida.')
                path = urlsplit(self.path).path
                if path=='/api/portable/control' and portable_control:
                    if not hmac.compare_digest(self.headers.get('X-Radici-Control',''),bootstrap_token):
                        return self.send(403,{'error':'Accesso non consentito.'})
                    portable_control.control(data.get('action'))
                    return self.send(202,{'accepted':True})
                if path == '/api/login':
                    now = time.monotonic()
                    failures[:] = [t for t in failures if now-t < 60]
                    if len(failures) >= 10:
                        return self.send(429,{'error':'Troppi tentativi. Attendi un minuto.'})
                    value = str(data.get('password',''))
                    if len(value) > 1024 or not hmac.compare_digest(hashlib.scrypt(value.encode(),salt=salt,n=16384,r=8,p=1),expected):
                        failures.append(now)
                        return self.send(401,{'error':'Password non corretta.'})
                    for token in list(sessions):
                        if sessions[token]['expires'] <= now:
                            del sessions[token]
                    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
                    sessions[token] = {'csrf':csrf,'expires':now+8*3600}
                    return self.send(200,{'csrf':csrf},headers={'Set-Cookie':f'{cookie_name}={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800'})
                entry = self.session()
                if not entry:
                    return self.send(401,{'error':'La sessione è scaduta: accedi di nuovo.'})
                if not hmac.compare_digest(self.headers.get('X-CSRF-Token',''),entry['csrf']):
                    return self.send(403,{'error':'Token di sicurezza non valido. Ricarica la pagina.'})
                if path == '/api/logout':
                    entry['expires'] = 0
                    return self.send(200,{},headers={'Set-Cookie':f'{cookie_name}=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0'})
                if path == '/api/command':
                    return self.send(200, service.command(data.get('action'),data))
                if path == '/api/trees/new':
                    return self.send(200,service.create(data.get('name','')))
                if path == '/api/trees/open':
                    return self.send(200,service.switch(data.get('id')))
                if hasattr(service,'check_tree'):
                    service.check_tree(data.get('tree_id'))
                if path == '/api/view':
                    return self.send(200,service.presentation(data))
                if path == '/api/backup':
                    return self.send(200,{'name':service.backup()})
                if path == '/api/import':
                    content = base64.b64decode(data['file'],validate=True)
                    service.import_tree(content,data.get('revision'))
                    return self.send(200,service.state())
                if path == '/api/print':
                    fmt = data.get('output','preview')
                    if fmt not in ('preview','pdf','svg','svgzip'):
                        raise ValueError('Esportazione non valida.')
                    result = service.print_tree(data,fmt)
                    if fmt == 'preview':
                        return self.send(200,result)
                    if portable_export_dir and data.get('save_local'):
                        name=('album-' if data.get('document')=='album' else 'albero-')+time.strftime('%Y%m%d-%H%M%S-')+uuid.uuid4().hex[:5]+'.'+('zip' if fmt=='svgzip' else fmt)
                        destination=Path(portable_export_dir)/name
                        temporary=destination.with_suffix('.partial')
                        with temporary.open('wb') as stream:
                            stream.write(result);stream.flush();os.fsync(stream.fileno())
                        os.replace(temporary,destination)
                        return self.send(200,{'saved':name})
                    extension='zip' if fmt=='svgzip' else fmt
                    return self.send(200,result,'application/pdf' if fmt == 'pdf' else 'application/zip' if fmt=='svgzip' else 'image/svg+xml',{'Content-Disposition':f'attachment; filename="albero.{extension}"'})
                return self.send(404,{'error':'Azione non trovata.'})
            except (ValueError,KeyError,TypeError) as e:
                return self.send(400,{'error':str(e)})
            except Exception:
                import traceback
                traceback.print_exc()
                return self.send(500,{'error':'Operazione non riuscita. I dettagli sono nel registro del servizio.'})

    class Server(server_type):
        def service_actions(self):
            loaded=list(service.services.values()) if hasattr(service,'services') else [service]
            for current in loaded:
                if not current.demo and time.monotonic()-current.last_backup > float(os.getenv('BACKUP_HOURS','24'))*3600:
                    try:
                        current.backup()
                    except Exception:
                        current.backup_error = 'Backup automatico non riuscito. Controlla spazio e permessi.'
                        current.last_backup = time.monotonic()-float(os.getenv('BACKUP_HOURS','24'))*3600+300

    server=Server(address,Handler)
    # Localhost cookies are shared across ports: keep simultaneous copies apart.
    cookie_name='radici_'+str(server.server_address[1])
    server.bootstrap_token=bootstrap_token
    return server


def main():
    demo = os.getenv('RADICI_DEMO') == '1'
    root = Path(os.getenv('DATA_DIR','/data'))
    if demo:
        password = 'radici-demo-2026'
    else:
        password = Path(os.getenv('PASSWORD_FILE','/run/secrets/app_password')).read_text().strip()
    from .workspace import Workspace
    service = Workspace(root,os.getenv('MEDIA_DIR','/media'),os.getenv('BACKUP_DIR','/backups'),demo)
    server = build_server(service,password,(os.getenv('BIND','0.0.0.0'),int(os.getenv('PORT','8787'))))
    def stop(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM,stop)
    print('Radici pronto: http://127.0.0.1:8787',flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        service.close()


if __name__ == '__main__':
    main()
