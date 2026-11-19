#!/usr/bin/env python3
"""List the contents of an NFS directory.

Usage:  nfs-ls.py [-a] [-l] [--nfs-version V] nfs://server/export/dir

Example: nfs-ls.py -l nfs://127.0.0.1/data
"""
import argparse
import stat
import sys
import time

import _common


def main():
    ap = argparse.ArgumentParser(description='List an NFS directory.')
    ap.add_argument('url', help='nfs://server/export/dir')
    ap.add_argument('-a', '--all', action='store_true',
                    help='include names starting with a dot')
    ap.add_argument('-l', '--long', action='store_true',
                    help='show mode, owner, size and modification time')
    ap.add_argument('--nfs-version', choices=_common.VERSIONS,
                    help='NFS version to use (libnfs defaults to 3)')
    args = ap.parse_args()

    nfs = _common.mount(_common.with_version(args.url, args.nfs_version))
    for name in nfs.listdir('/'):
        if name in ('.', '..') or (name.startswith('.') and not args.all):
            continue
        if not args.long:
            print(name)
            continue
        st = nfs.lstat('/' + name)
        when = time.strftime('%Y-%m-%d %H:%M', time.localtime(st['mtime']['sec']))
        print('%s %3d %5d %5d %10d %s %s' % (
            stat.filemode(st['mode']), st['nlink'], st['uid'], st['gid'],
            st['size'], when, name))


if __name__ == '__main__':
    sys.exit(_common.run(main))
