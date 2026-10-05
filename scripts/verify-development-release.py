"""Recheck public publication provenance and registry availability; never deploy."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import importlib.util
import json
from pathlib import Path
import urllib.error
import urllib.request


def load_script(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


checker = load_script('release_checker', 'check-development-release.py')
extractor = load_script('frontend_extractor', 'extract-frontend.py')


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not newurl.startswith('https://'):
            raise ValueError('Non-HTTPS registry redirect')
        result = super().redirect_request(req, fp, code, msg, headers, newurl)
        result.remove_header('Authorization')
        return result


opener = urllib.request.build_opener(SafeRedirect())


def get(url, headers=None, limit=1024 * 1024):
    request = urllib.request.Request(url, headers={'User-Agent': 'ecommerce-release-verification', **(headers or {})})
    try:
        with opener.open(request, timeout=30) as response:
            data = response.read(limit + 1)
    except urllib.error.HTTPError as error:
        raise ValueError(f'Public response failed (HTTP {error.code}): {url}') from error
    if len(data) > limit:
        raise ValueError('Public response exceeds verification limit')
    return data


def github(path):
    return json.loads(get('https://api.github.com/' + path))


def verify_run(pin, job=None):
    repo = pin['repository']
    run = github('repos/' + repo + '/actions/runs/' + str(pin['publicationRun']))
    if (run['conclusion'] != 'success' or run['head_sha'] != pin['commitSha']
            or run['repository']['full_name'] != repo
            or run['head_branch'] != pin.get('defaultBranch', 'main')
            or run['event'] not in ('push', 'workflow_dispatch', 'workflow_run')):
        raise ValueError('Publication run does not match reviewed source: ' + repo)
    if job is not None:
        result = github('repos/' + repo + '/actions/jobs/' + str(job))
        if result['run_id'] != pin['publicationRun'] or result['conclusion'] != 'success':
            raise ValueError('Publication job was not successful: ' + repo)


def verify_image(name, pin, root):
    verify_run(pin, pin['publicationJob'])
    repo, digest = pin['image'].split('@')
    token = json.loads(get('https://auth.docker.io/token?service=registry.docker.io&scope=repository:' + repo + ':pull'))['token']
    headers = {'Authorization': 'Bearer ' + token,
               'Accept': 'application/vnd.docker.distribution.manifest.v2+json, application/vnd.oci.image.manifest.v1+json'}
    prefix = 'https://registry-1.docker.io/v2/' + repo
    manifest_bytes = get(prefix + '/manifests/' + digest, headers)
    if manifest_bytes != (root / 'evidence/registry' / (name + '.manifest.json')).read_bytes():
        raise ValueError('Registry bytes differ from pinned manifest: ' + name)
    manifest = json.loads(manifest_bytes)
    config_bytes = get(prefix + '/blobs/' + manifest['config']['digest'], headers)
    if config_bytes != (root / 'evidence/registry' / (name + '.config.json')).read_bytes():
        raise ValueError('Registry config differs from reviewed platform: ' + name)
    if name == 'frontend':
        artifact = pin['staticArtifact']
        blob = get(prefix + '/blobs/' + artifact['digest'], headers, limit=extractor.MAX_BYTES)
        files = extractor.read_files(blob, artifact)
        if extractor.files_manifest(files) != json.loads((root / artifact['filesManifest']).read_bytes()):
            raise ValueError('Published Angular files differ from reviewed artifact')
    return name


def verify(root):
    release = checker.check(root)
    with ThreadPoolExecutor(max_workers=3) as pool:
        verified = list(pool.map(lambda pair: verify_image(*pair, root), release['applications'].items()))
    module = release['infrastructure']
    verify_run(module)
    tag = github('repos/' + module['repository'] + '/git/ref/tags/' + module['moduleTag'])
    if tag['object']['type'] != 'commit' or tag['object']['sha'] != module['commitSha']:
        raise ValueError('Module release tag differs from reviewed commit')
    for consumer in ('bff', 'frontend'):
        pin = release['applications'][consumer]
        base = 'https://raw.githubusercontent.com/' + pin['repository'] + '/' + pin['commitSha'] + '/contracts/upstream/'
        if get(base + 'manifest.json') != (root / 'evidence' / (consumer + '.contracts.json')).read_bytes():
            raise ValueError('Consumer manifest differs from source: ' + consumer)
        for name, expected in release['contracts'].items():
            if hashlib.sha256(get(base + name + '.openapi.json')).hexdigest() != expected:
                raise ValueError('Consumer OpenAPI checksum mismatch: ' + consumer + '/' + name)
    payment = release['applications']['payments']
    base = 'https://raw.githubusercontent.com/' + payment['repository'] + '/' + payment['commitSha'] + '/contracts/invoice/'
    if get(base + 'source.json') != (root / 'evidence/payments.invoice.json').read_bytes():
        raise ValueError('Payments Invoice provenance differs from source')
    if hashlib.sha256(get(base + 'openapi.json')).hexdigest() != release['contracts']['invoice']:
        raise ValueError('Payments Invoice OpenAPI checksum mismatch')
    verify_run({**release['applications']['frontend'], 'publicationRun': release['compatibility']['fullStackRun']}, release['compatibility']['fullStackJob'])
    return verified


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('release_directory', nargs='?', type=Path, default=Path('releases'))
    args = parser.parse_args()
    try:
        print('Verified public sources, successful CI, registry bytes, API contracts and Angular artifact for: ' + ', '.join(verify(args.release_directory)))
    except Exception as error:
        raise SystemExit('Public release verification failed: ' + str(error)) from error
