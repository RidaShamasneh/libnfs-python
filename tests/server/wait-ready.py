"""Wait until the test server accepts writes over both NFSv3 and NFSv4.

Usage: wait-ready.py SERVER [EXPORT] [TIMEOUT_SECONDS]

The server is not usable the moment its port opens: NFSv4 refuses new state
while it is in its grace period.  So try to create and remove a directory
until that works for every version.
"""
import os
import sys
import time

import libnfs

server = sys.argv[1]
export = sys.argv[2] if len(sys.argv) > 2 else '/export'
timeout = float(sys.argv[3]) if len(sys.argv) > 3 else 120


last_error = {}


def ready(version):
    """Return True if the server accepts writes over this NFS version."""
    try:
        nfs = libnfs.NFS('nfs://%s%s?version=%s' % (server, export, version))
        ret = nfs.mkdir('/.ready-check')
        if ret != 0:
            last_error[version] = 'mkdir returned %d (%s)' % (
                ret, os.strerror(-ret))
            return False
        ret = nfs.rmdir('/.ready-check')
        if ret != 0:
            last_error[version] = 'rmdir returned %d (%s)' % (
                ret, os.strerror(-ret))
            return False
        return True
    except Exception as e:
        last_error[version] = '%s: %s' % (type(e).__name__, e)
        return False


deadline = time.time() + timeout
pending = ['3', '4']
while pending and time.time() < deadline:
    pending = [v for v in pending if not ready(v)]
    if pending:
        time.sleep(2)

if pending:
    for v in pending:
        print('NFSv%s: %s' % (v, last_error.get(v, 'unknown')))
    sys.exit('server not ready for NFSv%s after %ds' %
             (', NFSv'.join(pending), timeout))
print('server ready')
