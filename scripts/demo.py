"""Ephemeral local demo, no Gramps dependency. Requires Python >=3.10."""
import os
import sys
from pathlib import Path
root = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root))
os.environ.update(RADICI_DEMO='1',BIND='127.0.0.1',
                  DATA_DIR=str(root/'runtime'/'demo-data'),
                  MEDIA_DIR=str(root/'runtime'/'demo-media'),
                  BACKUP_DIR=str(root/'runtime'/'demo-backups'))
from app.server import main
main()
