"""Executed only by the native worker, with synthetic temporary genealogy."""
import json
import os
from pathlib import Path
import sys
import unittest

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
suite = unittest.defaultTestLoader.discover(str(root / 'tests'))
result = unittest.TextTestRunner(verbosity=2).run(suite)
report = dict(tests=result.testsRun, failures=len(result.failures), errors=len(result.errors), skipped=len(result.skipped))
(Path(os.environ['RADICI_PORTABLE_ROOT']) / 'native-tests.json').write_text(json.dumps(report), encoding='utf-8')
if result.failures or result.errors or result.skipped:
    raise RuntimeError('Native suite failed; see native-tests.json and Registri/radici.log')
