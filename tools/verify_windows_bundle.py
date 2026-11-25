"""Reject known broken GUI bundles before an installer can be published."""
import argparse
from pathlib import Path
from PyInstaller.archive.readers import CArchiveReader


def verify(path):
    archive = CArchiveReader(str(path))
    names = {name.replace('\\', '/').lower() for name in archive.toc}
    if any(name.rsplit('/', 1)[-1] == 'ucrtbase.dll' for name in names):
        raise ValueError('Bundled ucrtbase.dll can override Windows UCRT and break QtWidgets. Use the isolated build script.')
    for library in ('qt6core.dll', 'qt6gui.dll', 'qt6widgets.dll'):
        if not any(name.endswith('/'+library) for name in names):
            raise ValueError('Missing Qt dependency: ' + library)
    print('GUI bundle dependencies verified; no private UCRT override.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('exe', type=Path)
    verify(parser.parse_args().exe)
