#!/usr/bin/env python3
"""Write the contents of one or more NFS files to standard output.

Usage:  nfs-cat.py [--nfs-version V] nfs://server/export/dir/file ...

Example: nfs-cat.py nfs://127.0.0.1/data/hello.txt
"""
import argparse
import sys

import _common

CHUNK = 1024 * 1024


def cat(url, version, out):
    mount_url, name = _common.split_file_url(url)
    nfs = _common.mount(_common.with_version(mount_url, version))
    with nfs.open('/' + name, mode='rb') as f:
        while True:
            data = f.read(CHUNK)
            if not data:
                break
            out.write(data)


def main():
    ap = argparse.ArgumentParser(description='Print NFS files.')
    ap.add_argument('urls', nargs='+', metavar='url',
                    help='nfs://server/export/dir/file')
    ap.add_argument('--nfs-version', choices=_common.VERSIONS,
                    help='NFS version to use (libnfs defaults to 3)')
    args = ap.parse_args()

    for url in args.urls:
        cat(url, args.nfs_version, sys.stdout.buffer)
    sys.stdout.buffer.flush()


if __name__ == '__main__':
    sys.exit(_common.run(main))
