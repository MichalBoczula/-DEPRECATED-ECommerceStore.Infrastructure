"""Release drift and static artifact safety regression checks; no network/Azure."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


check = load('inventory', 'check-development-release.py')
extractor = load('artifact', 'extract-frontend.py')


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'releases'
        shutil.copytree(ROOT / 'releases', self.root)
        self.path = self.root / 'development.json'
        self.release = json.loads(self.path.read_text())

    def reject(self, message):
        self.path.write_text(json.dumps(self.release))
        with self.assertRaisesRegex(ValueError, message):
            check.check(self.root)

    def test_real_release_checks_offline(self):
        self.assertEqual(check.check(self.root)['releaseId'], 'development-2026-10-05')

    def test_latest_is_rejected(self):
        self.release['applications']['products']['image'] = 'mb0101/product-catalog-api:latest'
        self.reject('immutable image')

    def test_missing_service_is_rejected(self):
        del self.release['applications']['invoice']
        self.reject('five business apps')

    def test_short_source_sha_is_rejected(self):
        self.release['applications']['payments']['commitSha'] = '9663df1'
        self.reject('full source SHA')

    def test_incompatible_invoice_pin_is_rejected(self):
        p = self.root / 'evidence/payments.invoice.json'
        content = json.loads(p.read_text()); content['published_revision'] = 'f' * 40
        p.write_text(json.dumps(content))
        with self.assertRaisesRegex(ValueError, 'Payments Invoice'):
            check.check(self.root)

    def test_frontend_contract_drift_is_rejected(self):
        self.release['contracts']['payments'] = 'a' * 64
        self.reject('incompatible upstream pin')

    def test_registry_manifest_tampering_is_rejected(self):
        p = self.root / 'evidence/registry/users.manifest.json';p.write_bytes(p.read_bytes() + b' ')
        with self.assertRaisesRegex(ValueError, 'manifest checksum'):
            check.check(self.root)

    def test_registry_config_tampering_is_rejected(self):
        p = self.root / 'evidence/registry/bff.config.json';p.write_bytes(p.read_bytes() + b' ')
        with self.assertRaisesRegex(ValueError, 'config checksum'):
            check.check(self.root)

    def test_static_artifact_cannot_pin_another_layer(self):
        self.release['applications']['frontend']['staticArtifact']['digest'] = 'sha256:' + 'a' * 64
        self.reject('final published layer')

    def test_livedocs_reapply_pin_cannot_drift(self):
        self.release['applications']['livedocs']['commitSha'] = 'a' * 40
        self.reject('Terraform reapply pin')

    def test_internal_service_cannot_gain_external_ingress(self):
        self.release['applications']['invoice']['runtime']['ingress'] = 'external'
        self.reject('ingress mismatch')

    def test_module_source_cannot_change(self):
        self.release['infrastructure']['repository'] = 'someone/another-module'
        self.reject('Unexpected module source')

    def test_no_azure_acceptance_claim(self):
        self.release['cloudValidated'] = True
        self.reject('Azure acceptance')


class ArtifactTests(unittest.TestCase):
    def layer(self, entries):
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode='w:gz') as archive:
            for name, kind in entries:
                entry = tarfile.TarInfo(name)
                if kind == 'link':
                    entry.type = tarfile.SYMTYPE;entry.linkname = '../../escape'
                    archive.addfile(entry)
                else:
                    data = b'<html>Angular</html>';entry.size = len(data)
                    archive.addfile(entry, io.BytesIO(data))
        blob = buffer.getvalue()
        return blob, {'root': 'usr/share/nginx/html', 'size': len(blob), 'digest': check.digest(blob)}

    def test_valid_static_files_can_be_recovered(self):
        blob, pin = self.layer([('usr/share/nginx/html/index.html', 'file'), ('usr/share/nginx/html/assets/app.js', 'file')])
        self.assertEqual(set(extractor.read_files(blob, pin)), {'index.html', 'assets/app.js'})

    def test_corrupt_blob_is_rejected_before_unpacking(self):
        blob, pin = self.layer([('usr/share/nginx/html/index.html', 'file')])
        with self.assertRaisesRegex(ValueError, 'checksum or size'):
            extractor.read_files(blob + b'x', pin)

    def test_traversal_links_whiteouts_duplicate_and_unrelated_files_are_rejected(self):
        index = ('usr/share/nginx/html/index.html', 'file')
        cases = [('usr/share/nginx/html/../../escape', 'file'), ('/absolute', 'file'),
                 ('usr/share/nginx/html/link', 'link'), ('usr/share/nginx/html/.wh.index.html', 'file'),
                 ('etc/passwd', 'file'), index]
        for bad in cases:
            with self.subTest(entry=bad):
                blob, pin = self.layer([index, bad])
                with self.assertRaises(ValueError):
                    extractor.read_files(blob, pin)

    def test_archive_entry_and_expansion_limits(self):
        blob, pin = self.layer([('usr/share/nginx/html/index.html', 'file'), ('usr/share/nginx/html/app.js', 'file')])
        with patch.object(extractor, 'MAX_FILES', 1):
            with self.assertRaisesRegex(ValueError, 'Too many archive entries'):
                extractor.read_files(blob, pin)
        with patch.object(extractor, 'MAX_BYTES', 1):
            with self.assertRaisesRegex(ValueError, 'extraction limit'):
                extractor.read_files(blob, pin)

    def test_site_must_have_index(self):
        blob, pin = self.layer([('usr/share/nginx/html/app.js', 'file')])
        with self.assertRaisesRegex(ValueError, 'index.html'):
            extractor.read_files(blob, pin)

    def test_output_directory_must_be_new(self):
        blob, pin = self.layer([('usr/share/nginx/html/index.html', 'file')])
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); (root / 'evidence').mkdir()
            data = json.dumps(extractor.files_manifest(extractor.read_files(blob, pin))).encode()
            (root / 'evidence/frontend-files.json').write_bytes(data)
            pin.update(filesManifest='evidence/frontend-files.json', filesManifestSha256=hashlib.sha256(data).hexdigest())
            release = root / 'development.json';release.write_text(json.dumps({'applications': {'frontend': {'staticArtifact': pin}}}))
            with self.assertRaises(FileExistsError):
                extractor.extract(blob, release, root)


if __name__ == '__main__':
    unittest.main()
