"""Package Radici for Store signing, without creating or trusting certificates."""
import argparse
import binascii
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import xml.etree.ElementTree as ET
import zipfile
import zlib

if __package__:
    from . import build_windows as desktop
else:
    import build_windows as desktop

ROOT = desktop.ROOT
WORK = desktop.WORK
STAGE = WORK / 'msix-stage'
OUTPUT = WORK / 'store-output'
VERSION = '5.0.1.0'
NS = {
    '': 'http://schemas.microsoft.com/appx/manifest/foundation/windows10',
    'uap': 'http://schemas.microsoft.com/appx/manifest/uap/windows10',
    'uap10': 'http://schemas.microsoft.com/appx/manifest/uap/windows10/10',
    'desktop6': 'http://schemas.microsoft.com/appx/manifest/desktop/windows10/6',
    'virtualization': 'http://schemas.microsoft.com/appx/manifest/virtualization/windows10',
    'rescap': 'http://schemas.microsoft.com/appx/manifest/foundation/windows10/restrictedcapabilities',
}
for prefix, uri in NS.items():
    ET.register_namespace(prefix, uri)


def q(name, prefix=''):
    return '{' + NS[prefix] + '}' + name


def identity_from_json(path=None, development=False):
    if development:
        if path is not None:
            raise ValueError('Choose an actual Store identity or development mode')
        return dict(name='Radici.Genealogy.Development', publisher='CN=Radici.Development',
                    publisher_display_name='Radici development build', display_name='Radici Genealogy - Prova')
    if path is None:
        raise ValueError('The real application identity from Partner Center is required')
    data = json.loads(Path(path).read_text('utf-8-sig'))
    return validate_store_identity(data)


def validate_store_identity(data):
    for key in ('name', 'publisher', 'publisher_display_name', 'display_name'):
        value = data.get(key)
        if not isinstance(value, str) or not value.strip() or len(value) > 256 or any(c in value for c in '\r\n\0'):
            raise ValueError('Invalid Store identity field: ' + key)
        if re.search(r'INSERIRE|REPLACE|PLACEHOLDER|DEVELOPMENT|EXAMPLE', value, re.I):
            raise ValueError('Replace the identity template with Partner Center values: ' + key)
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.-]{2,49}', data['name']):
        raise ValueError('Invalid Package/Identity/Name from Partner Center')
    if not data['publisher'].startswith('CN='):
        raise ValueError('Use the complete Publisher value from Partner Center')
    return {key: data[key] for key in ('name', 'publisher', 'publisher_display_name', 'display_name')}


def manifest(identity):
    root = ET.Element(q('Package'), IgnorableNamespaces='uap uap10 desktop6 virtualization rescap')
    ET.SubElement(root, q('Identity'), Name=identity['name'], Publisher=identity['publisher'], Version=VERSION, ProcessorArchitecture='x64')
    properties = ET.SubElement(root, q('Properties'))
    for name, text in [('DisplayName', identity['display_name']), ('PublisherDisplayName', identity['publisher_display_name']),
                       ('Description', 'Alberi genealogici locali, compilazione guidata e stampe per album.'), ('Logo', r'Assets\StoreLogo.png')]:
        ET.SubElement(properties, q(name)).text = text
    # The existing genealogy archive must never become uninstallable app cache.
    # Windows 10 fallback preserves AppData writes; Windows 11 narrows the exception.
    ET.SubElement(properties, q('FileSystemWriteVirtualization', 'desktop6')).text = 'disabled'
    virtualization = ET.SubElement(properties, q('FileSystemWriteVirtualization', 'virtualization'))
    exclusions = ET.SubElement(virtualization, q('ExcludedDirectories', 'virtualization'))
    ET.SubElement(exclusions, q('ExcludedDirectory', 'virtualization')).text = r'$(KnownFolder:LocalAppData)\Radici\Archivio'
    resources = ET.SubElement(root, q('Resources'))
    ET.SubElement(resources, q('Resource'), Language='it-IT')
    dependencies = ET.SubElement(root, q('Dependencies'))
    ET.SubElement(dependencies, q('TargetDeviceFamily'), Name='Windows.Desktop', MinVersion='10.0.19041.0', MaxVersionTested='10.0.26100.0')
    applications = ET.SubElement(root, q('Applications'))
    app = ET.SubElement(applications, q('Application'), Id='Radici', Executable='Radici.exe',
                        attrib={q('RuntimeBehavior', 'uap10'): 'packagedClassicApp', q('TrustLevel', 'uap10'): 'mediumIL'})
    ET.SubElement(app, q('VisualElements', 'uap'), DisplayName=identity['display_name'],
                  Description='La storia della tua famiglia', Square150x150Logo=r'Assets\Square150x150Logo.png',
                  Square44x44Logo=r'Assets\Square44x44Logo.png', BackgroundColor='#315f4d')
    capabilities = ET.SubElement(root, q('Capabilities'))
    ET.SubElement(capabilities, q('Capability', 'rescap'), Name='runFullTrust')
    ET.SubElement(capabilities, q('Capability', 'rescap'), Name='unvirtualizedResources')
    ET.indent(root, space='  ')
    return ET.tostring(root, encoding='utf-8', xml_declaration=True)


def icon_png(size):
    """Rasterize the existing Radici tree mark with stdlib; no new dependency."""
    def distance(px, py, ax, ay, bx, by):
        dx, dy = bx - ax, by - ay
        t = max(0, min(1, ((px-ax)*dx + (py-ay)*dy) / (dx*dx+dy*dy)))
        return ((px-ax-t*dx)**2 + (py-ay-t*dy)**2)**.5
    rows = []
    for y in range(size):
        row = bytearray([0])
        for x in range(size):
            px, py = (x+.5)/size, (y+.5)/size
            white = any((px-cx)**2+(py-cy)**2 < .085**2 for cx, cy in ((.5,.30),(.28,.64),(.72,.64)))
            white |= any(distance(px,py,*line) < .021 for line in ((.5,.33,.28,.64),(.5,.33,.72,.64),(.28,.64,.28,.81),(.72,.64,.72,.81)))
            row.extend((255,253,248,255) if white else (49,95,77,255))
        rows.append(row)
    def chunk(kind, data):
        return struct.pack('>I',len(data))+kind+data+struct.pack('>I',binascii.crc32(kind+data)&0xffffffff)
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',size,size,8,6,0,0,0))+chunk(b'IDAT',zlib.compress(b''.join(rows),9))+chunk(b'IEND',b'')


def makeappx_path(explicit=None):
    if explicit:
        path = Path(explicit)
        if not path.is_file():
            raise ValueError('MakeAppx tool not found')
        return path
    directory = Path(os.environ.get('ProgramFiles(x86)', 'C:/Program Files (x86)')) / 'Windows Kits/10/bin'
    choices = list(directory.glob('*/x64/makeappx.exe'))
    if not choices:
        raise ValueError('Install the official Windows SDK or provide --makeappx')
    return max(choices, key=lambda p: tuple(int(x) for x in p.parents[1].name.split('.')))


def collect_files():
    files = {'Radici.exe': desktop.BIN/'Radici.exe', 'Radici.ico': ROOT/'desktop/Radici.ico'}
    for path in sorted(desktop.PROGRAM.rglob('*')):
        if path.is_file() and (path.relative_to(desktop.PROGRAM).parts[0] == 'Runtime' or ('__pycache__' not in path.parts and path.suffix != '.pyc')):
            files['Programma/'+path.relative_to(desktop.PROGRAM).as_posix()] = path
    for name in ('Microsoft.Web.WebView2.Core.dll','Microsoft.Web.WebView2.WinForms.dll'):
        files[name] = desktop.DEPS/'sdk/lib/net462'/name
    files['WebView2Loader.dll'] = desktop.DEPS/'sdk/runtimes/win-x64/native/WebView2Loader.dll'
    for name in ('LICENSE.txt','LICENSE','License.txt','NOTICE.txt'):
        path = desktop.DEPS/'sdk'/name
        if path.is_file(): files['Licenze/WebView2-'+name] = path
    files['Sorgenti/LICENSE'] = ROOT/'LICENSE'
    files['Sorgenti/NOTICE'] = ROOT/'NOTICE'
    files['Sorgenti/gramps-v6.0.8.zip'] = desktop.DEPS/'gramps-v6.0.8.zip'
    archive = WORK / ('Radici-'+desktop.VERSION+'-sorgenti.zip')
    desktop.source_archive(archive)
    files['Sorgenti/'+archive.name] = archive
    return files


def validate_payload(files):
    required = {'Radici.exe','Programma/RadiciMotore.exe','Programma/Runtime/libpython3.14.dll','Programma/Runtime/lib/library.zip','Programma/app/static/index.html'}
    if not required.issubset(files):
        raise ValueError('Incomplete application payload: '+str(sorted(required-set(files))))
    for name, path in files.items():
        desktop.safe_zip_name(name)
        if set(Path(name).parts) & (desktop.PRIVATE_PARTS - {'runtime','__pycache__'}):
            raise ValueError('Private data directory in package: '+name)
        if not path.is_file() or path.is_symlink():
            raise ValueError('Unsafe package input: '+name)
        if name.lower().endswith(('.pfx','.p12')) or Path(name).name in ('Installa-Radici-Desktop.exe','Disinstalla.exe','WebViewRuntime.exe'):
            raise ValueError('An installer, credential or uninstaller is not a Store payload: '+name)


def build(identity, development=False, makeappx=None):
    if STAGE.exists() and any(STAGE.iterdir()):
        raise ValueError('MSIX staging folder must be empty; use a clean build directory')
    STAGE.mkdir(parents=True, exist_ok=True)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    files = collect_files()
    validate_payload(files)
    for name, path in sorted(files.items()):
        target = STAGE/name
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(path,target)
    (STAGE/'AppxManifest.xml').write_bytes(manifest(identity))
    assets = STAGE/'Assets';assets.mkdir()
    for name, size in (('StoreLogo.png',50),('Square44x44Logo.png',44),('Square150x150Logo.png',150)):
        (assets/name).write_bytes(icon_png(size))
    suffix = 'BOZZA-NON-INSTALLABILE' if development else 'STORE-NON-FIRMATO'
    package = OUTPUT/f'Radici-{VERSION}-x64-{suffix}.msix'
    subprocess.run([str(makeappx_path(makeappx)), 'pack', '/o', '/h', 'SHA256', '/d', str(STAGE), '/p', str(package)],check=True)
    with zipfile.ZipFile(package) as archive:
        names = set(archive.namelist())
        if 'AppxSignature.p7x' in names: raise ValueError('Unexpected local signature on Store input')
        actual = ET.fromstring(archive.read('AppxManifest.xml')).find(q('Identity'))
        if actual.get('Name') != identity['name'] or actual.get('Publisher') != identity['publisher']:
            raise ValueError('Packaged identity differs from requested identity')
        if not {'AppxBlockMap.xml','[Content_Types].xml','Radici.exe'}.issubset(names):
            raise ValueError('Invalid MakeAppx output')
    desktop.checksum(package)
    if not development:
        with zipfile.ZipFile(package.with_suffix('.msixupload'),'w',zipfile.ZIP_STORED) as upload:
            upload.write(package,package.name)
        desktop.checksum(package.with_suffix('.msixupload'))
    report = dict(product='Radici',version=VERSION,package_name=package.name,identity=identity,
                  development_identity=development,store_submission_ready=not development,
                  store_certification_passed=False,signed=False,files=len(files),bytes=package.stat().st_size,
                  sha256=desktop.sha(package),source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
                  archive_location=r'%LOCALAPPDATA%\Radici\Archivio',archive_survives_uninstall_requires_runtime_test=True,
                  restricted_capabilities=['runFullTrust','unvirtualizedResources'],webview2='Shared Evergreen runtime; official installation help if unavailable',
                  contains_user_data=False)
    (OUTPUT/'msix-report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report))
    return package


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    identity_group = parser.add_mutually_exclusive_group(required=True)
    identity_group.add_argument('--development', action='store_true')
    identity_group.add_argument('--store-identity', type=Path)
    identity_group.add_argument('--store-environment', action='store_true')
    parser.add_argument('--makeappx', type=Path)
    args = parser.parse_args()
    if args.store_environment:
        identity=validate_store_identity({key:os.environ.get(env,'') for key,env in (
            ('name','STORE_IDENTITY_NAME'),('publisher','STORE_PUBLISHER'),
            ('publisher_display_name','STORE_PUBLISHER_DISPLAY_NAME'),('display_name','STORE_DISPLAY_NAME'))})
    else:
        identity=identity_from_json(args.store_identity,args.development)
    STAGE=WORK/('msix-stage-development' if args.development else 'msix-stage-store')
    build(identity,args.development,args.makeappx)
