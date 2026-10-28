"""Run once before Compose. Password entered privately, never printed."""
import getpass
import os
import shutil
from pathlib import Path

root = Path(__file__).resolve().parents[1]
secret = root/'.secrets'/'app_password.txt'
secret.parent.mkdir(exist_ok=True)
if os.name != 'nt':
    secret.parent.chmod(0o700)
if secret.exists():
    print('Password già configurata. Nessuna modifica.')
else:
    value = getpass.getpass('Scegli una password (almeno 12 caratteri): ')
    if len(value) < 12:
        raise SystemExit('Servono almeno 12 caratteri.')
    if value != getpass.getpass('Ripeti la password: '):
        raise SystemExit('Le password non coincidono.')
    fd = os.open(secret, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as f:
        f.write(value+'\n')
    # Compose file secrets are bind mounts; the unprivileged container must read
    # the file. The host directory remains 0700, shielding it from other users.
    if os.name != 'nt':
        secret.chmod(0o444)
    print('Password salvata in .secrets/app_password.txt (esclusa da Git).')
if not (root/'.env').exists():
    shutil.copyfile(root/'.env.example', root/'.env')
print('Ora esegui: docker compose up --build -d')
