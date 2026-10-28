"""Closing must preserve committed work without exporting the whole archive."""
import concurrent.futures
import importlib.util
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from app.portable_rpc import OwnerProxy


HAS_GRAMPS = importlib.util.find_spec('gramps') is not None


class ShutdownTests(unittest.TestCase):
    def test_close_does_not_export_or_open_other_trees(self):
        from app.portable import close_workspace
        proxy = OwnerProxy()
        calls = []

        class Workspace:
            def close(self):
                calls.append('close')

            def _open(self, identifier):
                raise AssertionError('Closing must not open another tree')

            def export(self):
                raise AssertionError('Closing must not export an archive')

        with patch('app.portable.complete_backup', side_effect=AssertionError('Full backup on close')):
            close_workspace(Workspace(), proxy)
        self.assertEqual(calls, ['close'])
        self.assertFalse(proxy.alive)
        self.assertFalse(proxy.ready)

    def test_shutdown_releases_queued_request_without_mutating(self):
        from app.portable import close_workspace
        proxy = OwnerProxy()
        writes = []

        class Workspace:
            def command(self, *args, **kwargs):
                writes.append(args)

            def close(self):
                pass

        workspace = Workspace()
        proxy.target = workspace
        with concurrent.futures.ThreadPoolExecutor(1) as pool:
            queued = pool.submit(proxy.command, 'add', {'first': 'Too late'})
            deadline = time.monotonic() + 2
            while proxy.jobs.empty() and not queued.done():
                self.assertLess(time.monotonic(), deadline, 'Request was never queued')
                time.sleep(.01)
            close_workspace(workspace, proxy)
            with self.assertRaises(ValueError):
                queued.result(timeout=1)
        self.assertEqual(writes, [])
        with self.assertRaises(ValueError):
            proxy.command('add', {'first': 'After closing'})

    @unittest.skipUnless(HAS_GRAMPS, 'Requires official Gramps 6.0.8 runtime')
    def test_native_changes_and_manual_positions_survive_close_without_backup(self):
        from app.portable import close_workspace
        from app.workspace import Workspace
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = Workspace(root/'Dati', root/'Foto', root/'Backup', False)
            other = workspace.create('Secondo albero')['tree_id']
            state = workspace.command('add', {'tree_id': other, 'revision': 0,
                                             'first': 'Élisa', 'surname': 'D’Angelo',
                                             'birth': '1948'})
            identifier = state['people'][0]['id']
            state = workspace.command('move', {'tree_id': other, 'revision': state['revision'],
                                              'id': identifier, 'x': 640, 'y': 480, 'snap': False})
            position = state['positions'][identifier].copy()
            workspace.switch('original')
            state = workspace.command('add', {'tree_id': 'original', 'revision': 0,
                                             'first': 'Anna', 'surname': 'Rossi'})
            proxy = OwnerProxy()
            proxy.target = workspace
            proxy.ready = True
            for service in workspace.services.values():
                service.engine.export = lambda: self.fail('Closing called Engine.export')
            with patch('app.portable.complete_backup', side_effect=AssertionError('Full backup on close')):
                close_workspace(workspace, proxy)
            self.assertEqual(list((root/'Backup').rglob('*.zip')), [])

            reopened = Workspace(root/'Dati', root/'Foto', root/'Backup', False)
            try:
                self.assertEqual(reopened.state()['people'][0]['first'], 'Anna')
                state = reopened.switch(other)
                self.assertEqual(state['people'][0]['first'], 'Élisa')
                self.assertEqual(state['people'][0]['surname'], 'D’Angelo')
                self.assertEqual(state['people'][0]['years'], '1948')
                self.assertEqual(state['positions'][identifier], position)
                self.assertTrue(position['locked'])
            finally:
                reopened.close()
