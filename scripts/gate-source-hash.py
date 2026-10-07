"""Hash the exact verification build inputs, excluding local reports and compiled files."""
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def source_hash():
    paths = [ROOT / 'scripts/report-database-gate.py']
    base = ROOT / 'verification/database-gate'
    paths.extend(path for path in base.rglob('*') if path.is_file()
                 and not set(path.relative_to(base).parts) & {'bin', 'obj', '__pycache__'})
    digest = hashlib.sha256()
    # Path ordering is case-insensitive on Windows. Use case-sensitive relative
    # components everywhere, preserving the order used by published Linux images.
    for path in sorted(paths, key=lambda path: path.relative_to(ROOT).parts):
        # Git for Windows may check out CRLF; all retained build inputs are text.
        # Hash normalized text so the same source verifies on Windows and Linux.
        digest.update(path.relative_to(ROOT).as_posix().encode() + b'\0' + path.read_text(encoding='utf-8').encode() + b'\0')
    return digest.hexdigest()


if __name__ == '__main__':
    print(source_hash())
