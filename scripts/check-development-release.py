"""Check the reviewed release set without Azure access or application rebuilds."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re

SOURCES = {
    'products': ('ProductsCatalog', 'master', 'product-catalog-api'),
    'users': ('ECommerceStoreUsers', 'master', 'ecommerce-store-users-api'),
    'invoice': ('ECommerceStoreInvoice', 'master', 'ecommerce-store-invoice-api'),
    'payments': ('ECommerceStorePayments', 'main', 'ecommerce-store-payments-api'),
    'bff': ('ECommerceStoreBFF', 'master', 'ecommerce-store-bff-api'),
    'frontend': ('ecommerce-store-web', 'master', 'ecommerce-store-web'),
    'livedocs': ('ECommerceStore.LiveDocs', 'main', 'ecommerce-store-livedocs'),
}
SHA = re.compile(r'[0-9a-f]{40}')
DIGEST = re.compile(r'sha256:[0-9a-f]{64}')
HEX = re.compile(r'[0-9a-f]{64}')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(data):
    return 'sha256:' + hashlib.sha256(data).hexdigest()


def check(root):
    release = json.loads((root / 'development.json').read_text())
    require(type(release['schemaVersion']) is int and release['schemaVersion'] == 1, 'Unsupported release schema')
    require(release['status'] == 'inventory' and release['cloudValidated'] is False, 'D/5 cannot claim Azure acceptance')
    apps = release['applications']
    require(set(apps) == set(SOURCES), 'Expected five business apps, frontend and LiveDocs')
    publications = json.loads((root / 'evidence/publications.json').read_text())
    require(set(publications) == set(SOURCES), 'All image publication records required')
    manifests = {}
    configs = {}
    for name, (repo, branch, image) in SOURCES.items():
        pin = apps[name]
        require(pin['repository'] == 'MichalBoczula/' + repo and pin['defaultBranch'] == branch, name + ': wrong source')
        require(isinstance(pin['commitSha'], str) and SHA.fullmatch(pin['commitSha']), name + ': full source SHA required')
        require(re.fullmatch('mb0101/' + image + r'@sha256:[0-9a-f]{64}', pin['image']), name + ': immutable image required')
        for field in ('publicationRun', 'publicationJob'):
            require(type(pin[field]) is int and pin[field] > 0, name + ': publication provenance required')
        publication = publications[name]
        for field in ('repository', 'commitSha', 'image', 'publicationRun', 'publicationJob'):
            require(publication[field] == pin[field], name + ': publication record differs from release')
        match = re.fullmatch(r'[0-9TZ:.+-]+ ([a-f0-9]{40}): digest: (sha256:[a-f0-9]{64}) size: [0-9]+', publication['pushLogLine'])
        require(match and match.group(1) == pin['commitSha'] and match.group(2) == pin['image'].split('@')[1], name + ': published push source/digest mismatch')
        manifest_bytes = (root / 'evidence/registry' / (name + '.manifest.json')).read_bytes()
        require(digest(manifest_bytes) == pin['image'].split('@')[1], name + ': image manifest checksum mismatch')
        manifest = json.loads(manifest_bytes)
        config_bytes = (root / 'evidence/registry' / (name + '.config.json')).read_bytes()
        require(digest(config_bytes) == manifest['config']['digest'] and len(config_bytes) == manifest['config']['size'], name + ': config checksum mismatch')
        config = json.loads(config_bytes)
        require((config['os'], config['architecture'], pin['platform']) == ('linux', 'amd64', 'linux/amd64'), name + ': unsupported platform')
        manifests[name], configs[name] = manifest, config
        if name != 'frontend':
            runtime = pin['runtime']
            require(type(runtime['targetPort']) is int and runtime['targetPort'] == 8080, name + ': target port must be 8080')
            require('8080/tcp' in config['config']['ExposedPorts'], name + ': image port mismatch')
            require(runtime['ingress'] == ('external' if name in ('bff', 'livedocs') else 'internal'), name + ': ingress mismatch')
            for probe in ('startup', 'liveness', 'readiness'):
                expected = '/health' if name == 'bff' else ('/health/ready' if probe == 'readiness' else '/health/live')
                require(runtime[probe] == expected, name + ': probe does not match source')
    livedocs = json.loads((root / 'livedocs.json').read_text())
    for field in ('image', 'commitSha', 'publicationRun'):
        require(apps['livedocs'][field] == livedocs[field], 'LiveDocs release differs from the Terraform reapply pin')
    module = release['infrastructure']
    require(module['repository'] == 'MichalBoczula/ECommerceStore.Infrastructure', 'Unexpected module source')
    require(re.fullmatch(r'\d+\.\d+\.\d+', module['moduleVersion']) and module['moduleTag'] == 'modules-v' + module['moduleVersion'], 'Immutable module tag required')
    require(SHA.fullmatch(module['commitSha']) and type(module['publicationRun']) is int and module['publicationRun'] > 0, 'Module provenance required')
    artifact = apps['frontend']['staticArtifact']
    require(artifact['kind'] == 'oci-static-layer' and artifact['root'] == 'usr/share/nginx/html' and artifact['swaReady'] is False, 'Frontend cloud conversion remains D/11')
    last = manifests['frontend']['layers'][-1]
    require(all(artifact[k] == last[k] for k in ('digest', 'size', 'mediaType')), 'Frontend artifact is not the final published layer')
    history = [h for h in configs['frontend']['history'] if not h.get('empty_layer', False)]
    require(len(history) == len(manifests['frontend']['layers']) and history[-1]['created_by'].startswith('COPY /app/dist/ecommerce-store-web/browser /usr/share/nginx/html'), 'Final layer is not the Angular COPY artifact')
    require(artifact['filesManifest'] == 'evidence/frontend-files.json', 'Unexpected artifact inventory path')
    files_bytes = (root / artifact['filesManifest']).read_bytes()
    require(HEX.fullmatch(artifact['filesManifestSha256']) and hashlib.sha256(files_bytes).hexdigest() == artifact['filesManifestSha256'], 'Angular file inventory checksum mismatch')
    files = json.loads(files_bytes)
    require(len(files) <= 5000, 'Too many Angular files')
    for name in files:
        path = PurePosixPath(name)
        require(not path.is_absolute() and '..' not in path.parts and '\\' not in name and str(path) == name, 'Unsafe Angular inventory path')
    require('index.html' in files and files and all(type(v['size']) is int and v['size'] >= 0 and HEX.fullmatch(v['sha256']) for v in files.values()), 'Invalid Angular file checksums')
    require(set(release['contracts']) == {'products', 'users', 'invoice', 'payments'}, 'Four upstream API contracts required')
    for consumer in ('bff', 'frontend'):
        path = 'evidence/' + consumer + '.contracts.json'
        upstream = json.loads((root / path).read_text())
        require(set(upstream) == set(release['contracts']), consumer + ': missing upstream contract')
        for name, contract in upstream.items():
            require(contract['image'] == apps[name]['image'] and contract['specSha256'] == release['contracts'][name], consumer + ': incompatible upstream pin ' + name)
            # Older Products export omitted its SHA; D/5 recovers it from publication CI.
            require(contract['sourceCommit'] == apps[name]['commitSha'] or (name == 'products' and contract['sourceCommit'] is None), consumer + ': incompatible source ' + name)
            require(HEX.fullmatch(contract['specSha256']), consumer + ': invalid contract checksum')
    invoice = json.loads((root / 'evidence/payments.invoice.json').read_text())
    require(invoice['image'] == apps['invoice']['image'] and invoice['published_revision'] == apps['invoice']['commitSha'] and invoice['sha256'] == release['contracts']['invoice'], 'Payments Invoice contract does not match release')
    require(release['compatibility']['fullStackRun'] == apps['frontend']['publicationRun'], 'Full-stack evidence must test the selected frontend source')
    require(release['reportBundles'] == [], 'No production report bundles have been integrated yet; use the later content contract')
    require(release['pendingGates'], 'Cloud acceptance gates must remain visible')
    return release


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('release_directory', nargs='?', type=Path, default=Path('releases'))
    args = parser.parse_args()
    try:
        result = check(args.release_directory)
        print(result['releaseId'] + ': immutable image, source, contract and Angular artifact inventory verified.')
    except (KeyError, TypeError, ValueError, OSError) as error:
        raise SystemExit('Release validation failed: ' + str(error)) from error
