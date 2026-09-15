"""Create the next versioned Calibre plugin ZIP from the adjacent src folder."""

from contextlib import contextmanager
import os
from pathlib import Path
import re
import sys
import tempfile
import zipfile


@contextmanager
def build_lock(root):
    """Prevent simultaneous builders from exporting the same version."""
    with (root / '.build_plugin.lock').open('a+b') as handle:
        handle.seek(0, 2)
        if handle.tell() == 0:
            handle.write(b'0')
            handle.flush()
        handle.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError('Another plugin build is already running.') from exc
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == 'nt':
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def next_version(value):
    """Increment the minor integer, preserving the major version (1.9 becomes 1.10)."""
    match = re.fullmatch(r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)', value.strip())
    if not match:
        raise ValueError('version.txt must contain a version such as 1.1.')
    return int(match.group(1)), int(match.group(2)) + 1


def versioned_constants(data, major, minor):
    """Update only the three existing plugin version assignments, preserving other bytes."""
    for field, value in [('MAJOR', major), ('MINOR', minor), ('BUILD', 0)]:
        pattern = rb'(?m)^([ \t]*PLUGIN_VER_' + field.encode() + rb'[ \t]*=[ \t]*)[0-9]+'
        data, count = re.subn(pattern, lambda match: match.group(1) + str(value).encode(), data)
        if count != 1:
            raise ValueError(f'Expected one PLUGIN_VER_{field} assignment in plugin_constants.py.')
    return data


def build(root=None):
    """Export the next ZIP and commit version files; roll back if committing fails."""
    root = Path(root or Path(__file__).resolve().parent).resolve()
    with build_lock(root):
        return _build_locked(root)


def _build_locked(root):
    version_file = root / 'version.txt'
    source = root / 'src'
    constants = source / 'plugin_constants.py'
    old_version = version_file.read_bytes()
    old_constants = constants.read_bytes()
    major, minor = next_version(old_version.decode('utf-8-sig'))
    version = f'{major}.{minor}'
    output = root / f'sfarim_simania_v{version}.zip'
    if output.exists():
        raise FileExistsError(f'{output.name} already exists; it was not overwritten.')
    updated_constants = versioned_constants(old_constants, major, minor)
    for name in ('__init__.py', 'plugin-import-name-sfarim_simania.txt', 'simania_plugin.py', 'simania_html.py', 'simania_client.py', 'simania_cover.py', 'book_matching.py'):
        if not (source / name).is_file():
            raise FileNotFoundError(f'Missing required plugin source: {name}')
    with tempfile.TemporaryDirectory(prefix='.plugin-build-', dir=root) as temporary:
        staging = Path(temporary)
        archive_path = staging / output.name
        with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(source.rglob('*')):
                if not path.is_file() or '__pycache__' in path.parts or path.suffix in ('.pyc', '.pyo'):
                    continue
                relative = path.relative_to(source).as_posix()
                archive.writestr(relative, updated_constants if path == constants else path.read_bytes())
        with zipfile.ZipFile(archive_path) as archive:
            if archive.testzip() is not None:
                raise RuntimeError('ZIP validation failed.')
            if archive.read('plugin_constants.py') != updated_constants:
                raise RuntimeError('ZIP version verification failed.')
        new_version = staging / 'version.txt'
        new_constants = staging / 'plugin_constants.py'
        new_version.write_text(version + '\n', encoding='utf-8')
        new_constants.write_bytes(updated_constants)
        # Publish only after verification; keep original bytes for failure recovery.
        published = False
        constants_changed = False
        version_changed = False
        try:
            os.rename(archive_path, output)
            published = True
            os.replace(new_constants, constants)
            constants_changed = True
            os.replace(new_version, version_file)
            version_changed = True
        except Exception:
            if constants_changed:
                new_constants.write_bytes(old_constants)
                os.replace(new_constants, constants)
            if version_changed:
                new_version.write_bytes(old_version)
                os.replace(new_version, version_file)
            if published:
                output.unlink()
            raise
    return output


if __name__ == '__main__':
    try:
        output = build()
    except Exception as exc:
        print(f'Build failed: {exc}', file=sys.stderr)
        sys.exit(1)
    print(f'Created: {output}')
    print('Saved exported version in version.txt and updated Calibre version constants.')
