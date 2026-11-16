"""Wait until the test server accepts writes over both NFSv3 and NFSv4.

Usage: wait-ready.py SERVER [EXPORT] [TIMEOUT_SECONDS]

The server is not usable the moment its port opens: NFSv4 refuses new state
while it is in its grace period.  So try to create and remove a directory
until that works for every version.
"""
import sys
import time

import libnfs

server = sys.argv[1]
export = sys.argv[2] if len(sys.argv) > 2 else '/export'
timeout = float(sys.argv[3]) if len(sys.argv) > 3 else 120


def ready(version):
    try:
        nfs = libnfs.NFS('nfs://%s%s?version=%s' % (server, export, version))
        if nfs.mkdir('/.ready-check') != 0:
            return False
        return nfs.rmdir('/.ready-check') == 0
    except Exception:
        return False


deadline = time.time() + timeout
pending = ['3', '4']
while pending and time.time() < deadline:
    pending = [v for v in pending if not ready(v)]
    if pending:
        time.sleep(2)

if pending:
    sys.exit('server not ready for NFSv%s after %ds' %
             (', NFSv'.join(pending), timeout))
print('server ready')
