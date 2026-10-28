"""Build only public application code. Never reads a user archive or USB drive."""
import argparse
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / '.build/windows'
DEPS = WORK / 'deps'
BIN = WORK / 'bin'
PROGRAM = WORK / 'program'
DIST = WORK / 'dist'
VERSION = '5.0.0'
OWN_BINARIES = ('Radici.exe', 'RadiciMotore.exe', 'Disinstalla.exe')
PRIVATE_PARTS = {'.git', '.secrets', '.build', 'runtime', '__pycache__', 'Dati', 'Foto', 'Stampe', 'Backup', 'Impostazioni', 'Registri', 'Temp'}
PRIVATE_SUFFIXES = {'.db', '.log', '.gramps', '.gpkg', '.ged', '.pfx', '.p12', '.pyc'}


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def source_allowed(name):
    path = Path(name)
    return not (set(path.parts) & PRIVATE_PARTS or path.suffix.lower() in PRIVATE_SUFFIXES or path.name == '.env')


def safe_zip_name(name):
    if not name or '\\' in name or ':' in name or name.startswith('/'):
        raise ValueError('Invalid archive path: ' + name)
    if any(p in ('', '.', '..') or p.endswith((' ', '.')) for p in name.rstrip('/').split('/')):
        raise ValueError('Invalid archive path: ' + name)
    return name


def extract_zip(path, destination):
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            safe_zip_name(info.filename)
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError('Symlink not allowed in dependency archive')
        archive.extractall(destination)


def fetch(item):
    destination = DEPS / item['filename']
    if destination.exists():
        if sha(destination) != item['sha256']:
            raise ValueError('Cached dependency hash mismatch: ' + item['filename'])
        return destination
    temporary = destination.with_suffix(destination.suffix + '.partial')
    try:
        request = urllib.request.Request(item['url'], headers={'User-Agent': 'Radici-build/5.0'})
        with urllib.request.urlopen(request, timeout=120) as incoming, temporary.open('wb') as output:
            shutil.copyfileobj(incoming, output, 1024 * 1024)
        if sha(temporary) != item['sha256']:
            raise ValueError('Downloaded dependency hash mismatch: ' + item['filename'])
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def microsoft_signature(path):
    # Only inspect the publisher; never modify trust or run the redistributable here.
    command = "$s=Get-AuthenticodeSignature -LiteralPath $env:RADICI_VERIFY_FILE; if($s.Status -ne 'Valid' -or $s.SignerCertificate.Subject -notmatch 'O=Microsoft Corporation'){throw 'Invalid Microsoft signature'}"
    subprocess.run(['powershell.exe', '-NoProfile', '-Command', command], env={**os.environ, 'RADICI_VERIFY_FILE': str(path)}, check=True)


def prepare():
    lock = json.loads((ROOT / 'dependencies/windows.lock.json').read_text('utf-8'))
    DEPS.mkdir(parents=True, exist_ok=True)
    entries = [value for key, value in lock.items() if key != 'wheels'] + lock['wheels']
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(fetch, entries))
    sdk = DEPS / 'sdk'
    extract_zip(DEPS / lock['webview_sdk']['filename'], sdk)
    microsoft_signature(DEPS / lock['webview_runtime']['filename'])
    for name in ('Microsoft.Web.WebView2.Core.dll', 'Microsoft.Web.WebView2.WinForms.dll'):
        microsoft_signature(sdk / 'lib/net462' / name)
    microsoft_signature(sdk / 'runtimes/win-x64/native/WebView2Loader.dll')
    sevenzip = shutil.which('7z') or str(Path(os.environ.get('ProgramFiles', 'C:/Program Files')) / '7-Zip/7z.exe')
    extracted = DEPS / 'aio'
    extracted.mkdir(exist_ok=True)
    with (DEPS / 'extract.log').open('w', encoding='utf-8') as log:
        subprocess.run([sevenzip, 'x', '-y', '-o' + str(extracted), str(DEPS / lock['gramps_aio']['filename'])], stdout=log, stderr=subprocess.STDOUT, check=True)
    PROGRAM.mkdir(exist_ok=True)
    runtime = PROGRAM / 'Runtime'
    runtime.mkdir(exist_ok=True)
    for path in sorted(extracted.iterdir()):
        if path.name.startswith('$') or path.name in ('uninstall.exe', 'gramps.exe', 'grampsd.exe', 'grampsw.exe', 'pip.exe'):
            continue
        if path.is_dir():
            shutil.copytree(path, runtime / path.name, dirs_exist_ok=True, ignore=shutil.ignore_patterns('__pycache__', '*.pyc', 'pip', 'ensurepip'))
        else:
            shutil.copy2(path, runtime / path.name)
    if not (runtime / 'libpython3.14.dll').is_file() or not (runtime / 'lib/library.zip').is_file():
        raise ValueError('Unexpected Gramps AIO layout')
    libraries = PROGRAM / 'Librerie'
    for wheel in lock['wheels']:
        extract_zip(DEPS / wheel['filename'], libraries)
    for name in ('timeit', 'python_license'):
        shutil.copy2(DEPS / lock[name]['filename'], libraries / lock[name]['filename'])
    shutil.copytree(ROOT / 'app', PROGRAM / 'app', dirs_exist_ok=True, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    shutil.copy2(ROOT / 'portable_bootstrap.py', PROGRAM / 'portable_bootstrap.py')


def compile_cs(source, target, extra=(), platform='x64'):
    compiler = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    subprocess.run([str(compiler), '/nologo', '/target:winexe', '/optimize+', '/platform:' + platform,
                    '/win32manifest:' + str(ROOT / 'desktop/windows.manifest'), '/win32icon:' + str(ROOT / 'desktop/Radici.ico'),
                    '/r:System.Windows.Forms.dll', '/r:System.Drawing.dll', '/r:System.Web.Extensions.dll',
                    '/r:System.IO.Compression.dll', '/r:System.IO.Compression.FileSystem.dll', '/out:' + str(target),
                    *extra, str(ROOT / 'desktop/AssemblyInfo.cs'), str(ROOT / source)], check=True, cwd=ROOT)


def binaries():
    BIN.mkdir(parents=True, exist_ok=True)
    sdk = DEPS / 'sdk/lib/net462'
    compile_cs('desktop/RadiciDesktop.cs', BIN / 'Radici.exe', ['/r:' + str(sdk / name) for name in ('Microsoft.Web.WebView2.Core.dll', 'Microsoft.Web.WebView2.WinForms.dll')])
    compile_cs('portable/RadiciMotore.cs', BIN / 'RadiciMotore.exe')
    compile_cs('desktop/DisinstallaRadici.cs', BIN / 'Disinstalla.exe', platform='anycpu')
    if PROGRAM.exists():
        shutil.copy2(BIN / 'RadiciMotore.exe', PROGRAM / 'RadiciMotore.exe')


def native_test():
    qa = WORK / 'qa'
    qa.mkdir(exist_ok=True)
    test_script = ROOT / 'scripts/native_tests.py'
    process = subprocess.run([str(PROGRAM / 'RadiciMotore.exe'), str(qa), '--desktop', '--test', str(test_script)], timeout=300)
    report = qa / 'native-tests.json'
    if not report.is_file():
        raise RuntimeError('Native test did not finish; inspect .build/windows/qa/Registri')
    result = json.loads(report.read_text('utf-8'))
    print(json.dumps(result))
    if process.returncode or result['failures'] or result['errors'] or result['skipped'] or result['tests'] < 140:
        raise RuntimeError('Native test suite failed or skipped required checks')


def verify_signatures(paths):
    thumb = os.environ.get('SIGNPATH_CERT_THUMBPRINT', '').replace(' ', '').upper()
    if len(thumb) != 40 or any(c not in '0123456789ABCDEF' for c in thumb):
        raise ValueError('Missing expected production signing certificate thumbprint')
    request = WORK / 'verify-request.json'
    request.write_text(json.dumps({'files': [str(path.resolve()) for path in paths]}), encoding='utf-8')
    subprocess.run(['powershell.exe', '-NoProfile', '-File', str(ROOT / 'desktop/Verify-Authenticode.ps1'), '-Manifest', str(request), '-CertificateThumbprint', thumb], check=True)


def source_archive(destination):
    names = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode('utf-8').split('\0')
    names = sorted(name for name in names if name)
    if not {'scripts/build_windows.py', 'desktop/AssemblyInfo.cs', 'README.md'}.issubset(names):
        raise ValueError('Build source must be a complete tracked checkout')
    with zipfile.ZipFile(destination, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name in names:
            if not source_allowed(name) or (ROOT / name).is_symlink():
                raise ValueError('Private or unsafe tracked source: ' + name)
            archive.write(ROOT / name, safe_zip_name(name))


def installer(development_unsigned=False):
    binaries_root = BIN if development_unsigned else WORK / 'signed/binaries'
    if not development_unsigned:
        verify_signatures([binaries_root / name for name in OWN_BINARIES])
    shutil.copy2(binaries_root / 'RadiciMotore.exe', PROGRAM / 'RadiciMotore.exe')
    files = {}
    def add(name, path):
        safe_zip_name(name)
        if set(Path(name).parts) & (PRIVATE_PARTS - {'runtime'}) or not path.is_file() or path.is_symlink():
            raise ValueError('Unsafe package file: ' + name)
        files[name] = path
    for name in ('Radici.exe', 'Disinstalla.exe'):
        add(name, binaries_root / name)
    add('Radici.ico', ROOT / 'desktop/Radici.ico')
    for path in sorted(PROGRAM.rglob('*')):
        if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc':
            add('Programma/' + path.relative_to(PROGRAM).as_posix(), path)
    sdk = DEPS / 'sdk'
    for name in ('Microsoft.Web.WebView2.Core.dll', 'Microsoft.Web.WebView2.WinForms.dll'):
        add(name, sdk / 'lib/net462' / name)
    add('WebView2Loader.dll', sdk / 'runtimes/win-x64/native/WebView2Loader.dll')
    for name in ('LICENSE.txt', 'LICENSE', 'License.txt', 'NOTICE.txt'):
        if (sdk / name).is_file():
            add('Licenze/WebView2-' + name, sdk / name)
    sources = WORK / 'Radici-5.0.0-sorgenti.zip'
    source_archive(sources)
    add('Sorgenti/' + sources.name, sources)
    for name in ('LICENSE', 'NOTICE'):
        add('Sorgenti/' + name, ROOT / name)
    add('Sorgenti/gramps-v6.0.8.zip', DEPS / 'gramps-v6.0.8.zip')
    readme = WORK / 'LEGGIMI.txt'
    readme.write_text('RADICI DESKTOP 5.0\nDati: %LOCALAPPDATA%\\Radici\\Archivio\nProgramma e dati sono separati. La disinstallazione conserva gli alberi.\nLeggi Sorgenti/NOTICE e i documenti inclusi prima della migrazione.\n' + ('ANTEPRIMA NON FIRMATA.\n' if development_unsigned else 'Verificare la firma digitale del pacchetto prima dell’installazione.\n'), encoding='utf-8-sig')
    add('LEGGIMI.txt', readme)
    manifest = dict(product='radici-desktop-v1', version=VERSION, engine='6.0.8', publisher_signed=not development_unsigned, files=[])
    package = WORK / 'desktop-package.zip'
    with zipfile.ZipFile(package, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for name, path in sorted(files.items()):
            manifest['files'].append(dict(path=name, bytes=path.stat().st_size, sha256=sha(path)))
            archive.write(path, name)
        archive.writestr('desktop-package.json', json.dumps(manifest))
    DIST.mkdir(exist_ok=True)
    target = DIST / ('Installa-Radici-Desktop-NON-FIRMATO.exe' if development_unsigned else 'Installa-Radici-Desktop.exe')
    compile_cs('desktop/InstallaRadici.cs', target, ['/resource:' + str(package) + ',RadiciDesktopPackage', '/resource:' + str(DEPS / 'webview2-runtime.exe') + ',WebViewRuntime'], platform='anycpu')
    report = dict(version=VERSION, own_binary_signatures_verified=not development_unsigned, installer_signed=False,
                  source_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT,text=True).strip(),
                  files=len(files), installer_bytes=target.stat().st_size, sha256=sha(target), contains_user_data=False)
    (WORK / 'build-report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    checksum(target)
    print(json.dumps(report))


def checksum(path):
    path.with_suffix(path.suffix + '.sha256').write_text(sha(path) + '  ' + path.name + '\n', encoding='ascii')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('prepare', 'binaries', 'test', 'installer', 'verify-release'))
    parser.add_argument('--development-unsigned', action='store_true')
    args = parser.parse_args()
    WORK.mkdir(parents=True, exist_ok=True)
    if args.phase == 'prepare': prepare()
    elif args.phase == 'binaries': binaries()
    elif args.phase == 'test': native_test()
    elif args.phase == 'installer': installer(args.development_unsigned)
    else:
        if args.development_unsigned:
            parser.error('A signed release cannot use --development-unsigned')
        result = WORK / 'signed/installer/Installa-Radici-Desktop.exe'
        verify_signatures([result])
        verify_signatures([WORK / 'signed/binaries' / name for name in OWN_BINARIES])
        shutil.copy2(result, DIST / result.name)
        checksum(DIST / result.name)
        report = json.loads((WORK / 'build-report.json').read_text('utf-8'))
        report.update(installer_signed=True, sha256=sha(result), installer_bytes=result.stat().st_size)
        (WORK / 'build-report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
