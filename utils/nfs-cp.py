#!/usr/bin/env python3
"""Copy a file to, from or between NFS servers.

Usage:  nfs-cp.py [--nfs-version V] SOURCE DEST

Either side is a local path or an nfs://server/export/dir/file URL (at least
one must be a URL).  If DEST is an existing directory the file keeps its name.

Examples:
    nfs-cp.py notes.txt nfs://127.0.0.1/data/notes.txt     upload
    nfs-cp.py nfs://127.0.0.1/data/notes.txt .             download
    nfs-cp.py nfs://a/data/x nfs://b/backup/x              server to server
"""
import argparse
import os
import sys

import _common



class Local:
    """A local file, opened lazily like the NFS side."""
    def __init__(self, path):
        self.path = path

    def is_dir(self):
        return os.path.isdir(self.path)

    def child(self, name):
        return Local(os.path.join(self.path, name))

    def name(self):
        return os.path.basename(self.path)

    def open(self, mode):
        return open(self.path, mode)


class Remote:
    """An NFS file.  Mounting is the expensive part (about a dozen round
    trips), so mount the parent directory once and use that one mount both
    to look at the file and to open it."""
    def __init__(self, url, version):
        self.url, self.version = url, version
        self._parent = None         # (mount, file name), made on first use

    def _mount(self, mount_url):
        return _common.mount(_common.with_version(mount_url, self.version))

    def _in_parent(self):
        if self._parent is None:
            mount_url, name = _common.split_file_url(self.url)
            self._parent = (self._mount(mount_url), name)
        return self._parent

    def is_dir(self):
        if self.url.endswith('/'):
            return True             # nothing to look at, and no mount needed
        try:
            nfs, name = self._in_parent()
        except IOError as parent_error:
            # e.g. the export root itself, which has no parent to mount
            try:
                return self._mount(self.url).isdir('/')
            except IOError:
                raise parent_error      # the parent is what is really missing
        return nfs.isdir('/' + name)

    def child(self, name):
        return Remote(self.url.rstrip('/') + '/' + name, self.version)

    def name(self):
        return _common.split_file_url(self.url)[1]

    def open(self, mode):
        nfs, name = self._in_parent()
        return nfs.open('/' + name, mode=mode)


def endpoint(arg, version):
    return Remote(arg, version) if _common.is_url(arg) else Local(arg)


def main():
    ap = argparse.ArgumentParser(description='Copy a file to or from NFS.')
    ap.add_argument('source')
    ap.add_argument('dest')
    ap.add_argument('--nfs-version', choices=_common.VERSIONS,
                    help='NFS version to use (libnfs defaults to 3)')
    args = ap.parse_args()
    if not (_common.is_url(args.source) or _common.is_url(args.dest)):
        ap.error('one of SOURCE and DEST must be an nfs:// URL')

    src = endpoint(args.source, args.nfs_version)
    dst = endpoint(args.dest, args.nfs_version)
    if dst.is_dir():
        dst = dst.child(src.name())

    with src.open('rb') as fin, dst.open('wb') as fout:
        total = _common.copy_stream(fin, fout)
    print('%d bytes copied' % total, file=sys.stderr)


if __name__ == '__main__':
    sys.exit(_common.run(main))
