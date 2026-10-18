import io
import json
import os
from pathlib import Path
import tempfile
import textwrap
import unittest
from unittest.mock import Mock, patch

import github_app_auth as auth


class GitHubAppAuthTest(unittest.TestCase):
    url = f'https://api.github.com/repos/{auth.REPOSITORY}/actions/artifacts/123'

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.key = Path(self.directory.name).resolve() / 'key.pem'
        self.key.write_text('test-only-placeholder')
        self.key.chmod(0o600)
        self.environment = dict(zip(auth.ENVIRONMENT, ('123', '456', str(self.key))))
        self.environ = patch.dict(os.environ, self.environment, clear=True)
        self.environ.start()
        self.addCleanup(self.environ.stop)
        auth._cached = None

    def test_refresh_before_expiry_and_never_fallback_on_refresh_failure(self):
        with patch.object(auth, '_mint', side_effect=[('first', 4600), ('second', 8000), ValueError('denied')]) as mint, \
                patch.object(auth.time, 'time', return_value=1000) as clock:
            for _ in range(100):
                self.assertEqual('first', auth.token_for(self.url, 'fallback'))
            self.assertEqual(1, mint.call_count)
            clock.return_value = 4300
            self.assertEqual('second', auth.token_for(self.url, 'fallback'))
            clock.return_value = 7700
            with self.assertRaisesRegex(ValueError, 'denied'):
                auth.token_for(self.url, 'fallback')

    def test_no_app_credential_outside_fixed_repository_read_routes(self):
        with patch.object(auth, '_mint') as mint:
            for url in ('https://example.com/download', self.url.replace('api.github.com', 'api.github.com.evil'),
                        self.url.replace(auth.REPOSITORY, 'other/repo'),
                        f'https://api.github.com/repos/{auth.REPOSITORY}/environments'):
                self.assertEqual('fallback', auth.token_for(url, 'fallback'))
            mint.assert_not_called()
        os.environ.pop(auth.ENVIRONMENT[1])
        with self.assertRaisesRegex(ValueError, 'configuration'):
            auth.token_for(self.url, 'fallback')
        os.environ.clear()
        self.assertEqual('fallback', auth.token_for(self.url, 'fallback'))

    def test_each_pagination_page_resolves_current_credential(self):
        with patch.object(auth, 'token_for', side_effect=['first', 'second']) as tokens, \
                patch.object(auth.reuse, 'api_json', side_effect=[{'items': list(range(100))}, {'items': [100]}]) as api:
            self.assertEqual(list(range(101)), auth.paginated_items(self.url, 'items', 'fallback'))
            self.assertEqual(2, tokens.call_count)
            self.assertEqual(['first', 'second'], [call.args[1] for call in api.call_args_list])

    def test_mint_exact_scope_and_reject_scope_expansion(self):
        value = {'token': 'ghs_' + 'a' * 36, 'expires_at': '1970-01-01T01:16:40Z',
                 'permissions': {**auth.PERMISSIONS, 'metadata': 'read'},
                 'repositories': [{'id': auth.REPOSITORY_ID, 'full_name': auth.REPOSITORY}]}
        opener = Mock()
        def response(*args, **kwargs):
            return io.BytesIO(json.dumps(value).encode())
        opener.open.side_effect = response
        with patch.object(auth.time, 'time', return_value=1000), \
                patch.object(auth.subprocess, 'run', return_value=Mock(returncode=0, stdout=b'signed')) as signer, \
                patch.object(auth.urllib.request, 'build_opener', return_value=opener):
            self.assertEqual((value['token'], 4600), auth._mint(('123', '456', str(self.key))))
            request = opener.open.call_args.args[0]
            self.assertEqual({'repository_ids': [auth.REPOSITORY_ID], 'permissions': auth.PERMISSIONS}, json.loads(request.data))
            self.assertEqual('POST', request.get_method())
            self.assertNotIn('signed', str(signer.call_args.args))
            value['permissions']['actions'] = 'write'
            with self.assertRaisesRegex(ValueError, 'scope'):
                auth._mint(('123', '456', str(self.key)))
            self.assertIsNone(auth._NoRedirect().redirect_request(None))

    def test_transport_reuses_existing_digest_and_redirect_checks(self):
        artifact = {'archive_download_url': self.url}
        with patch.object(auth, 'token_for', return_value='app'), \
                patch.object(auth.reuse, 'download_artifact', return_value=b'original') as download, \
                patch.object(auth.reuse, 'download_artifact_to_file') as stream:
            self.assertEqual(b'original', auth.download_artifact(artifact, 'fallback'))
            download.assert_called_once_with(artifact, 'app')
            auth.download_artifact_to_file(artifact, 'fallback', self.key, max_bytes=12)
            stream.assert_called_once_with(artifact, 'app', self.key, max_bytes=12)

    def test_private_key_access_and_product_child_environment(self):
        from ci import product_reuse as worker
        with patch.object(auth, '_mint') as mint:
            if os.name != 'nt':
                self.key.chmod(0o644)
                with self.assertRaisesRegex(ValueError, 'other users'):
                    auth.token_for(self.url, 'fallback')
                self.key.chmod(0o600)
            alias = self.key.parent / 'alias'
            alias.symlink_to(self.key)
            os.environ[auth.ENVIRONMENT[-1]] = str(alias)
            with self.assertRaisesRegex(ValueError, 'configuration'):
                auth.token_for(self.url, 'fallback')
            mint.assert_not_called()
        with patch.object(worker, '_runtime_worker_checkout'):
            safe = worker._worker_process_environment(self.key.parent, {}, self.key.parent,
                {**self.environment, 'GRADLE_USER_HOME': str(self.key.parent / 'gradle')})
        self.assertTrue(set(auth.ENVIRONMENT).isdisjoint(safe))

    def test_configuration_is_control_only_for_every_product_phase(self):
        from products.registry import PHASE_INSTANCE_IDS
        from products.selection import phase_inventory_paths
        paths = ['ci/github_app_auth.py', 'ci/product_reuse.py', 'ci/runtime_reference_archive.py',
                 '.github/actions/prepare-github-read-app/action.yml',
                 '.github/workflows/product-validation.yml', 'ci/tests/test_github_app_auth.py']
        for instance in PHASE_INSTANCE_IDS:
            self.assertEqual((), phase_inventory_paths(paths, instance))

    def test_protected_setup_keeps_key_outside_checkout_and_environment_output(self):
        root = Path(__file__).resolve().parents[2]
        action = (root / '.github/actions/prepare-github-read-app/action.yml').read_text()
        source = textwrap.dedent(action.split("        python3 -B - <<'PY'\n", 1)[1].split('\n        PY', 1)[0])
        workspace = self.key.parent / 'workspace'
        scratch = self.key.parent / 'scratch'
        workspace.mkdir()
        scratch.mkdir()
        output = self.key.parent / 'environment'
        secret = 'test-only-private-key-placeholder'
        environment = {'READ_APP_ID': '123', 'READ_INSTALLATION_ID': '456',
                       'READ_APP_PRIVATE_KEY': secret, 'GITHUB_WORKSPACE': str(workspace),
                       'RUNNER_TEMP': str(scratch), 'GITHUB_ENV': str(output)}
        with patch.dict(os.environ, environment, clear=True), patch('sys.stdout', new_callable=io.StringIO) as stdout:
            exec(compile(source, '<prepare-github-read-app>', 'exec'), {})
            self.assertNotIn(secret, stdout.getvalue())
        exported = dict(line.split('=', 1) for line in output.read_text().splitlines())
        self.assertEqual(set(auth.ENVIRONMENT), set(exported))
        self.assertNotIn(secret, output.read_text())
        key = Path(exported[auth.ENVIRONMENT[-1]])
        self.assertTrue(key.is_relative_to(scratch))
        self.assertEqual(secret, key.read_text())
        if os.name != 'nt':
            self.assertEqual(0o600, key.stat().st_mode & 0o777)
        environment['READ_APP_ID'] = ''
        with patch.dict(os.environ, environment, clear=True):
            with self.assertRaisesRegex(ValueError, 'identity'):
                exec(compile(source, '<prepare-github-read-app>', 'exec'), {})


if __name__ == '__main__':
    unittest.main()
