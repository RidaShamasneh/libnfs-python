"""Helpers shared by the nfs-* command-line tools."""
import sys
from urllib.parse import urlsplit, urlunsplit, unquote

import libnfs

VERSIONS = ('3', '4', '4.1', '4.2')


def is_url(arg):
    return arg.startswith('nfs://')


def with_version(url, version):
    """Add version=<n> to the URL unless it already names a version."""
    if not version or 'version=' in url:
        return url
    return url + ('&' if '?' in url else '?') + 'version=' + version


def split_file_url(url):
    """nfs://host/export/dir/file?x=y -> ('nfs://host/export/dir?x=y', 'file').

    libnfs mounts the directory a URL names, so a file is reached by
    mounting its directory and opening the file by name.
    """
    parts = urlsplit(url)
    directory, _, name = parts.path.rpartition('/')
    if not name:
        raise ValueError('not a file URL: %s' % url)
    mount = urlunsplit((parts.scheme, parts.netloc, directory or '/',
                        parts.query, ''))
    return mount, unquote(name)


def mount(url):
    return libnfs.NFS(url)


def run(main):
    """Run main(); report errors like a shell tool instead of a traceback."""
    prog = sys.argv[0].rsplit('/', 1)[-1]
    try:
        return main() or 0
    except KeyboardInterrupt:
        return 130
    except BrokenPipeError:
        return 1
    except (OSError, ValueError) as e:
        print('%s: %s' % (prog, e), file=sys.stderr)
        return 1
