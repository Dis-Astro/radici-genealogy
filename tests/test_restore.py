import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from app.restore import restore


class RestoreValidationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.data,self.media=self.root/'data',self.root/'media'
        self.data.mkdir();self.media.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def backup(self,name,payload,checksum=None):
        path=self.root/'backup.zip'
        with zipfile.ZipFile(path,'w') as z:
            z.writestr(name,payload)
            z.writestr('manifest.json',json.dumps(dict(version=1,gramps='6.0.8',sha256={name:checksum or hashlib.sha256(payload).hexdigest()})))
        return path

    def test_rejects_path_traversal_before_writing(self):
        archive=self.backup('media/../../escape.txt',b'no')
        with self.assertRaisesRegex(ValueError,'Percorso non sicuro'):
            restore(archive,self.data,self.media)
        self.assertFalse((self.root/'escape.txt').exists())
        self.assertFalse(list(self.data.iterdir()))

    def test_rejects_checksum_corruption(self):
        archive=self.backup('tree.gramps',b'corrupt','0'*64)
        with self.assertRaisesRegex(ValueError,'danneggiato'):
            restore(archive,self.data,self.media)
        self.assertFalse(list(self.data.iterdir()))

    def test_refuses_existing_data(self):
        (self.data/'important.txt').write_text('preserve')
        with self.assertRaisesRegex(ValueError,'completamente vuoti'):
            restore(self.root/'missing.zip',self.data,self.media)
        self.assertEqual((self.data/'important.txt').read_text(),'preserve')
