"""Responsive HTTP sockets; every Gramps operation stays on its owning thread."""
import queue
import threading
import time
import sys
from http.server import ThreadingHTTPServer
from types import SimpleNamespace


class ResponsiveServer(ThreadingHTTPServer):
    daemon_threads=True
    block_on_close=False
    request_queue_size=32

    def __init__(self,*args,**kwargs):
        self.slots=threading.BoundedSemaphore(16)
        super().__init__(*args,**kwargs)

    def get_request(self):
        connection,address=super().get_request()
        connection.settimeout(5)
        return connection,address

    def process_request(self,request,address):
        if not self.slots.acquire(False):
            self.shutdown_request(request)
            return
        try:super().process_request(request,address)
        except BaseException:
            self.slots.release()
            raise

    def process_request_thread(self,request,address):
        try:super().process_request_thread(request,address)
        finally:self.slots.release()

    def handle_error(self,request,address):
        if isinstance(sys.exception(),(ConnectionError,TimeoutError)):return
        super().handle_error(request,address)


class OwnerProxy:
    demo=False
    services={}
    backup_error=None

    def __init__(self):
        self.jobs=queue.Queue(maxsize=48)
        self.stop=threading.Event()
        self.backup_requested=threading.Event()
        self.local=threading.local()
        self.target=None
        self.created=time.monotonic()
        self.phase='starting'
        self.message='Apertura dell’archivio…'
        self.ready=False
        self.alive=True
        self.engine=SimpleNamespace(export=lambda:self.call('engine.export'))

    def status(self):
        return {'ready':self.ready,'phase':self.phase,'message':self.message,
                'seconds':round(time.monotonic()-self.created,2),'closing':self.stop.is_set()}

    def control(self,action):
        if action=='shutdown':
            self.phase='closing';self.message='Chiusura dell’archivio…';self.ready=False
            self.stop.set()
        elif action=='backup':self.backup_requested.set()
        else:raise ValueError('Comando non valido.')

    def call(self,name,*args,**kwargs):
        if not self.alive or self.stop.is_set():raise ValueError('Radici si sta chiudendo.')
        bound=getattr(self.local,'tree_id',None)
        job={'name':name,'args':args,'kwargs':kwargs,'bound':bound,'done':threading.Event()}
        try:self.jobs.put_nowait(job)
        except queue.Full:raise ValueError('Operazione in corso. Attendi qualche istante.') from None
        while not job['done'].wait(.2):
            if not self.alive:raise ValueError('Il motore di Radici non è disponibile.')
        if 'error' in job:raise job['error']
        return job['result']

    def run_one(self,timeout=.1):
        try:job=self.jobs.get(timeout=timeout)
        except queue.Empty:return
        try:
            if self.stop.is_set():raise ValueError('Radici si sta chiudendo.')
            if job['bound'] is not None:self.target.check_tree(job['bound'])
            function=self.target
            for part in job['name'].split('.'):function=getattr(function,part)
            job['result']=function(*job['args'],**job['kwargs'])
        except BaseException as error:job['error']=error
        finally:job['done'].set()

    def finish(self):
        """Release queued HTTP callers without starting further database work."""
        self.alive=False
        while True:
            try:job=self.jobs.get_nowait()
            except queue.Empty:break
            job['error']=ValueError('Radici si sta chiudendo.')
            job['done'].set()

    def check_tree(self,identifier):
        self.local.tree_id=identifier
        return self.call('check_tree',identifier)

    def state(self):return self.call('state')
    def command(self,*a,**k):return self.call('command',*a,**k)
    def create(self,*a,**k):return self.call('create',*a,**k)
    def switch(self,*a,**k):return self.call('switch',*a,**k)
    def backup(self,*a,**k):return self.call('backup',*a,**k)
    def import_tree(self,*a,**k):return self.call('import_tree',*a,**k)
    def print_tree(self,*a,**k):return self.call('print_tree',*a,**k)
    def presentation(self,*a,**k):return self.call('presentation',*a,**k)
