"""Entry point executed by the private CPython runtime shipped in Gramps AIO."""
import os
import sys
from pathlib import Path
import importlib.abc
import importlib.machinery
import importlib.util

sys.dont_write_bytecode=True
root=Path(os.environ['RADICI_PORTABLE_ROOT'])
program=Path(os.environ.get('RADICI_PROGRAM_ROOT',str(root/'Programma')))
runtime=program/'Runtime'
dll_directories=[os.add_dll_directory(str(runtime)),os.add_dll_directory(str(runtime/'lib'))]


class FrozenExtensions(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        for suffix in importlib.machinery.EXTENSION_SUFFIXES:
            candidate=runtime/'lib'/(fullname+suffix)
            if candidate.is_file():return importlib.util.spec_from_file_location(fullname,candidate)


sys.meta_path.insert(0,FrozenExtensions())
sys.path.insert(0,str(program/'Librerie'))
sys.path.insert(0,str(program))
os.environ['GRAMPS_RESOURCES']=str(runtime/'share')
os.environ['GRAMPSHOME']=str(root/'Impostazioni'/'Gramps')
os.environ['GI_TYPELIB_PATH']=str(runtime/'lib'/'girepository-1.0')
from xml.sax.saxutils import escape
font_config=root/'Impostazioni'/'fonts.conf'
font_config.write_text('<fontconfig><dir>'+escape(str(program/'app/fonts'))+'</dir><dir>WINDOWSFONTDIR</dir><cachedir>'+escape(str(root/'Temp/font-cache'))+'</cachedir></fontconfig>',encoding='utf-8')
os.environ['FONTCONFIG_FILE']=str(font_config)
log=root/'Registri'/'radici.log'
if log.exists() and log.stat().st_size>1024*1024:os.replace(log,log.with_suffix('.log.1'))
sys.stdout=open(log,'a',encoding='utf-8',buffering=1)
sys.stderr=sys.stdout
import faulthandler
faulthandler.enable(file=sys.stderr)
faulthandler.dump_traceback_later(25,repeat=False,file=sys.stderr)

if os.environ.get('RADICI_TEST_SCRIPT'):
    faulthandler.cancel_dump_traceback_later()
    import runpy
    runpy.run_path(os.environ['RADICI_TEST_SCRIPT'],run_name='__main__')
else:
    from app.portable import main
    main()
