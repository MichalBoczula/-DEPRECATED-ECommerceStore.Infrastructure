"""Verify and recover the Angular artifact from its pinned published image layer."""
import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import tarfile

MAX_BYTES = 50 * 1024 * 1024
MAX_FILES = 5000


def read_files(blob, artifact):
    if len(blob) != artifact['size'] or 'sha256:' + hashlib.sha256(blob).hexdigest() != artifact['digest']:
        raise ValueError('Static artifact checksum or size mismatch')
    prefix = artifact['root'] + '/'
    files = {}
    seen = set()
    total = 0
    with tarfile.open(fileobj=io.BytesIO(blob), mode='r:gz') as archive:
        for count, member in enumerate(archive, start=1):
            if count > MAX_FILES:
                raise ValueError('Too many archive entries')
            path = PurePosixPath(member.name)
            if (path.is_absolute() or '..' in path.parts or '\\' in member.name
                    or any(part.startswith('.wh.') for part in path.parts)
                    or member.name in seen or not (member.isdir() or member.isfile())):
                raise ValueError('Unsafe archive entry')
            seen.add(member.name)
            if member.isdir():
                continue
            if not member.name.startswith(prefix) or member.size < 0:
                raise ValueError('File outside static artifact root')
            total += member.size
            if total > MAX_BYTES:
                raise ValueError('Static artifact exceeds extraction limit')
            stream = archive.extractfile(member)
            data = stream.read(member.size + 1)
            if len(data) != member.size:
                raise ValueError('Truncated archive file')
            relative = str(path.relative_to(artifact['root']))
            if relative in files:
                raise ValueError('Duplicate normalized archive entry')
            files[relative] = data
    if not files.get('index.html'):
        raise ValueError('Angular index.html missing')
    return files


def files_manifest(files):
    return {name: {'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
            for name, data in sorted(files.items())}


def extract(blob, release_path, output):
    release = json.loads(release_path.read_text())
    artifact = release['applications']['frontend']['staticArtifact']
    files = read_files(blob, artifact)
    expected_path = release_path.parent / artifact['filesManifest']
    expected_bytes = expected_path.read_bytes()
    if hashlib.sha256(expected_bytes).hexdigest() != artifact['filesManifestSha256']:
        raise ValueError('Files manifest checksum mismatch')
    if files_manifest(files) != json.loads(expected_bytes):
        raise ValueError('Static file inventory mismatch')
    # Require a new directory, so existing symlinks/files cannot redirect writes.
    output.mkdir(parents=True, exist_ok=False)
    for name, data in files.items():
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return len(files)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('layer', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--release', type=Path, default=Path('releases/development.json'))
    args = parser.parse_args()
    if args.layer.stat().st_size > MAX_BYTES:
        raise SystemExit('Compressed layer exceeds size limit')
    try:
        count = extract(args.layer.read_bytes(), args.release, args.output)
        print(f'Verified {count} Angular files from the published artifact; no rebuild.')
    except (ValueError, KeyError, OSError, tarfile.TarError) as error:
        raise SystemExit(str(error)) from error
