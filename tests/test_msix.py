import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from scripts import build_msix as msix


class MsixTests(unittest.TestCase):
    def test_real_partner_center_identity_is_preserved_and_xml_escaped(self):
        values=dict(name='Contoso.Radici',publisher='CN=00000000-0000-4000-8000-000000000001',
                    publisher_display_name='Prove & Famiglia',display_name='Radici - Prove & Famiglia')
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'identity.json';path.write_text(json.dumps(values),encoding='utf-8')
            identity=msix.identity_from_json(path)
        root=ET.fromstring(msix.manifest(identity))
        self.assertEqual(root.find(msix.q('Identity')).get('Publisher'),values['publisher'])
        self.assertEqual(root.find(msix.q('Properties')).find(msix.q('DisplayName')).text,values['display_name'])
        self.assertEqual(root.find(msix.q('Identity')).get('ProcessorArchitecture'),'x64')

    def test_development_identity_cannot_accidentally_become_store_submission(self):
        values=msix.identity_from_json(development=True)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'identity.json';path.write_text(json.dumps(values),encoding='utf-8')
            with self.assertRaises(ValueError):msix.identity_from_json(path)
            with self.assertRaises(ValueError):msix.identity_from_json(path,development=True)
        with self.assertRaises(ValueError):msix.identity_from_json()

    def test_genealogy_archive_is_excluded_from_uninstall_virtualization(self):
        root=ET.fromstring(msix.manifest(msix.identity_from_json(development=True)))
        props=root.find(msix.q('Properties'))
        self.assertEqual(props.find(msix.q('FileSystemWriteVirtualization','desktop6')).text,'disabled')
        exclusions=props.find(msix.q('FileSystemWriteVirtualization','virtualization')).find(msix.q('ExcludedDirectories','virtualization'))
        self.assertEqual([x.text for x in exclusions],[r'$(KnownFolder:LocalAppData)\Radici\Archivio'])
        caps={item.get('Name') for item in root.find(msix.q('Capabilities'))}
        self.assertEqual(caps,{'runFullTrust','unvirtualizedResources'})
        self.assertIsNone(props.find(msix.q('RegistryWriteVirtualization','desktop6')))

    def test_private_data_installers_and_credentials_are_rejected(self):
        required={'Radici.exe','Programma/RadiciMotore.exe','Programma/Runtime/libpython3.14.dll','Programma/Runtime/lib/library.zip','Programma/app/static/index.html'}
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);file=root/'fixture.bin';file.write_bytes(b'fixture')
            files={name:file for name in required};msix.validate_payload(files)
            for name in ('Dati/trees.json','Foto/family.jpg','Backup/tree.zip','identity.pfx','Disinstalla.exe','../outside'):
                with self.subTest(name=name),self.assertRaises(ValueError):msix.validate_payload({**files,name:file})

    def test_packaging_refuses_to_replace_an_existing_staging_folder(self):
        with tempfile.TemporaryDirectory() as directory:
            stage=Path(directory)/'stage';stage.mkdir();sentinel=stage/'keep.txt';sentinel.write_text('preserve')
            with patch.object(msix,'STAGE',stage):
                with self.assertRaisesRegex(ValueError,'empty'):msix.build(msix.identity_from_json(development=True),development=True)
            self.assertEqual(sentinel.read_text(),'preserve')

    def test_template_and_command_line_injections_are_not_valid_identities(self):
        values=dict(name='Contoso.Radici',publisher='CN=00000000-0000-4000-8000-000000000001',publisher_display_name='Editore Prova',display_name='Radici')
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'identity.json'
            for field,value in [('name','INSERIRE_NOME'),('name','bad/name'),('publisher','CN=bad\nvalue'),('display_name','')]:
                path.write_text(json.dumps({**values,field:value}),encoding='utf-8')
                with self.subTest(field=field,value=value),self.assertRaises(ValueError):msix.identity_from_json(path)
