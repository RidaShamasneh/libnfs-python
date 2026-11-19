#!/usr/bin/env python3
"""Exercise NFSv4 operations through the libnfs Python binding.

Usage:  python3 example.py [nfs://server/export/]   (or set NFS_URL="nfs://server/export/" python3 example.py)

Everything happens inside a scratch directory that is created at the start
and removed at the end.  Each step prints PASS/FAIL/SKIP and the run
continues after a failure; the exit status is non-zero if anything failed.
"""
import errno
import os
import stat
import sys
import time
import traceback

import libnfs
from libnfs import (nfs_open2, nfs_close, nfs_pread, nfs_pwrite, nfs_read,
                    nfs_write, nfs_lseek, nfs_fsync, nfs_truncate,
                    nfs_ftruncate, nfs_mkdir, nfs_mkdir2, nfs_rmdir,
                    nfs_unlink, nfs_rename, nfs_link, nfs_symlink,
                    nfs_readlink, nfs_chmod, nfs_fchmod, nfs_chown,
                    nfs_fchown, nfs_utimes, nfs_access, nfs_mknod,
                    nfs_chdir, nfs_stat64, nfs_lstat64, nfs_fstat64,
                    nfs_opendir, nfs_readdir, nfs_closedir)

BASE = sys.argv[1] if len(sys.argv) > 1 else os.environ.get('NFS_URL')

if not BASE:
    sys.exit("usage: %s nfs://server/export/\n"
             "   or: NFS_URL=nfs://server/export/ %s"
             % (sys.argv[0], sys.argv[0]))

# Without version=4 libnfs speaks NFSv3, so make sure v4 is requested.
if 'version=' not in BASE:
    BASE += ('&' if '?' in BASE else '?') + 'version=4'

results = {'PASS': 0, 'FAIL': 0, 'SKIP': 0}


def check(name, fn, skip=()):
    """Run fn(); skip is a tuple of errnos that mean 'not permitted here'."""
    try:
        detail = fn()
        results['PASS'] += 1
        print("PASS  %-36s %s" % (name, detail if detail else ''))
    except OSError as e:
        if e.errno in skip:
            results['SKIP'] += 1
            print("SKIP  %-36s %s" % (name, os.strerror(e.errno)))
        else:
            results['FAIL'] += 1
            print("FAIL  %-36s %s" % (name, e))
    except Exception:
        results['FAIL'] += 1
        print("FAIL  %-36s" % name)
        traceback.print_exc()


def rc(ret):
    """libnfs returns -errno on failure; turn that into an exception."""
    if ret < 0:
        raise OSError(-ret, os.strerror(-ret))
    return ret


def expect_errno(ret, err):
    if ret != -err:
        raise AssertionError("expected %s, got %d" % (errno.errorcode[err], ret))


class File(object):
    """RAII wrapper over a raw nfsfh so every OPEN gets its CLOSE."""
    def __init__(self, ctx, path, flags, mode=0o644):
        self.ctx = ctx
        h = libnfs.new_NFSFileHandle()
        rc(nfs_open2(ctx, path, flags, mode, h))
        self.fh = libnfs.NFSFileHandle_value(h)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        nfs_close(self.ctx, self.fh)

    # binding signatures: (ctx, fh, buff, count[, offset])
    def write(self, data):
        buf = bytearray(data)
        return rc(nfs_write(self.ctx, self.fh, buf, len(buf)))

    def pwrite(self, off, data):
        buf = bytearray(data)
        return rc(nfs_pwrite(self.ctx, self.fh, buf, len(buf), off))

    def read(self, n):
        buf = bytearray(n)
        got = rc(nfs_read(self.ctx, self.fh, buf, n))
        return bytes(buf[:got])

    def pread(self, off, n):
        buf = bytearray(n)
        got = rc(nfs_pread(self.ctx, self.fh, buf, n, off))
        return bytes(buf[:got])

    def seek(self, off, whence=os.SEEK_SET):
        pos = libnfs.new_uint64_t_ptr()
        rc(nfs_lseek(self.ctx, self.fh, off, whence, pos))
        return libnfs.uint64_t_ptr_value(pos)

    def fstat(self):
        st = libnfs.nfs_stat_64()
        rc(nfs_fstat64(self.ctx, self.fh, st))
        return st


def stat_of(ctx, path, follow=True):
    st = libnfs.nfs_stat_64()
    rc((nfs_stat64 if follow else nfs_lstat64)(ctx, path, st))
    return st


def listdir(ctx, path):
    d = libnfs.new_NFSDirHandle()
    rc(nfs_opendir(ctx, path, d))
    d = libnfs.NFSDirHandle_value(d)
    names = []
    while True:
        de = nfs_readdir(ctx, d)
        if de is None:
            break
        names.append(de.name)
    nfs_closedir(ctx, d)
    return sorted(n for n in names if n not in ('.', '..'))


def rmtree(ctx, path):
    for n in listdir(ctx, path):
        p = path + '/' + n
        if stat.S_ISDIR(stat_of(ctx, p, follow=False).nfs_mode):
            rmtree(ctx, p)
        else:
            rc(nfs_unlink(ctx, p))
    rc(nfs_rmdir(ctx, path))


def main():
    print("Mounting %s" % BASE)
    nfs = libnfs.NFS(BASE)          # PUTROOTFH / LOOKUP / GETFH / GETATTR
    ctx = nfs._nfs
    print("rsize=%d wsize=%d" % (libnfs.nfs_get_readmax(ctx),
                                 libnfs.nfs_get_writemax(ctx)))

    T = '/libnfs-py-test-%d' % os.getpid()

    # ---- directories: CREATE(NF4DIR), LOOKUP, GETATTR, READDIR, REMOVE ----
    check('mkdir', lambda: rc(nfs_mkdir(ctx, T)))
    check('mkdir2 (explicit mode)',
          lambda: rc(nfs_mkdir2(ctx, T + '/sub', 0o750)))
    check('stat dir -> mode',
          lambda: oct(stat_of(ctx, T + '/sub').nfs_mode & 0o7777))
    check('mkdir existing -> EEXIST',
          lambda: expect_errno(nfs_mkdir(ctx, T), errno.EEXIST))
    check('readdir', lambda: str(listdir(ctx, T)))

    def chdir_rel():
        rc(nfs_chdir(ctx, T))
        try:
            stat_of(ctx, 'sub')           # relative LOOKUP
        finally:
            rc(nfs_chdir(ctx, '/'))
    check('chdir + relative lookup', chdir_rel)

    # ---- OPEN(create) / WRITE / COMMIT / CLOSE / READ ----
    f1 = T + '/file1'
    data = b'hello nfsv4\n' * 100

    def create_write():
        with File(ctx, f1, os.O_CREAT | os.O_WRONLY | os.O_TRUNC) as f:
            n = f.write(data)
            rc(nfs_fsync(ctx, f.fh))      # COMMIT
            return '%d bytes' % n
    check('open(create)+write+fsync', create_write)

    def read_back():
        with File(ctx, f1, os.O_RDONLY) as f:
            got = f.read(len(data))
            assert got == data, 'data mismatch'
            return '%d bytes' % len(got)
    check('open(read)+read', read_back)

    def pread_pwrite():
        with File(ctx, f1, os.O_RDWR) as f:
            f.pwrite(6, b'NFSV4')
            assert f.pread(0, 11) == b'hello NFSV4', 'pwrite/pread mismatch'
            assert f.seek(0, os.SEEK_END) == len(data)
            assert f.seek(5, os.SEEK_SET) == 5
    check('pwrite/pread/lseek', pread_pwrite)

    def append():
        with File(ctx, f1, os.O_WRONLY | os.O_APPEND) as f:
            f.write(b'tail')
        assert stat_of(ctx, f1).nfs_size == len(data) + 4
    check('O_APPEND', append)

    def excl():
        ret = nfs_open2(ctx, f1, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o644,
                        libnfs.new_NFSFileHandle())
        expect_errno(ret, errno.EEXIST)
    check('O_CREAT|O_EXCL existing -> EEXIST', excl)

    def many_open():     # several concurrent open stateids
        files = [File(ctx, T + '/m%d' % i, os.O_CREAT | os.O_RDWR)
                 for i in range(8)]
        try:
            for i, f in enumerate(files):
                f.write(b'x' * (i + 1))
            return '8 files open at once'
        finally:
            for f in files:
                f.__exit__()
    check('multiple open stateids', many_open)

    def big_io():        # forces multiple READ/WRITE RPCs
        size = 4 * 1024 * 1024 + 123
        blob = os.urandom(size)
        with File(ctx, T + '/big', os.O_CREAT | os.O_RDWR) as f:
            done = 0
            while done < size:
                done += f.write(blob[done:done + 1024 * 1024])
            rc(nfs_fsync(ctx, f.fh))
            assert f.pread(0, size) == blob, 'big file mismatch'
        return '%d bytes' % size
    check('large write/read', big_io)

    # ---- GETATTR ----
    check('stat file', lambda: 'size=%d' % stat_of(ctx, f1).nfs_size)

    def fstat():
        with File(ctx, f1, os.O_RDONLY) as f:
            assert f.fstat().nfs_size == stat_of(ctx, f1).nfs_size
    check('fstat', fstat)
    check('stat missing -> ENOENT',
          lambda: expect_errno(
              nfs_stat64(ctx, T + '/nope', libnfs.nfs_stat_64()), errno.ENOENT))

    # ---- SETATTR ----
    def chmod():
        rc(nfs_chmod(ctx, f1, 0o600))
        assert stat_of(ctx, f1).nfs_mode & 0o777 == 0o600
    check('chmod', chmod)

    def fchmod():
        with File(ctx, f1, os.O_RDWR) as f:
            rc(nfs_fchmod(ctx, f.fh, 0o640))
        assert stat_of(ctx, f1).nfs_mode & 0o777 == 0o640
    check('fchmod', fchmod)

    def utimes():
        tv = libnfs.new_TimeValArray(2)
        for i, sec in enumerate((1000000000, 1100000000)):
            t = libnfs.timeval()
            t.tv_sec, t.tv_usec = sec, 0
            libnfs.TimeValArray_setitem(tv, i, t)
        rc(nfs_utimes(ctx, f1, tv))
        st = stat_of(ctx, f1)
        assert (st.nfs_atime, st.nfs_mtime) == (1000000000, 1100000000), \
            (st.nfs_atime, st.nfs_mtime)
    check('utimes', utimes)

    def trunc():
        rc(nfs_truncate(ctx, f1, 10))
        assert stat_of(ctx, f1).nfs_size == 10
        with File(ctx, f1, os.O_RDWR) as f:
            rc(nfs_ftruncate(ctx, f.fh, 4096))
        assert stat_of(ctx, f1).nfs_size == 4096     # extends, zero-filled
    check('truncate/ftruncate', trunc)

    check('chown', lambda: rc(nfs_chown(ctx, f1, os.getuid(), os.getgid())),
          skip=(errno.EPERM, errno.EACCES))

    def fchown():
        with File(ctx, f1, os.O_RDWR) as f:
            rc(nfs_fchown(ctx, f.fh, os.getuid(), os.getgid()))
    check('fchown', fchown, skip=(errno.EPERM, errno.EACCES))

    # ---- ACCESS ----
    check('access(R_OK|W_OK)',
          lambda: rc(nfs_access(ctx, f1, os.R_OK | os.W_OK)))

    # ---- LINK / SYMLINK / READLINK / RENAME ----
    def hardlink():
        rc(nfs_link(ctx, f1, T + '/hard'))
        assert stat_of(ctx, f1).nfs_nlink == 2
        assert stat_of(ctx, f1).nfs_ino == stat_of(ctx, T + '/hard').nfs_ino
    check('link (hard link)', hardlink)

    def symlink():
        rc(nfs_symlink(ctx, 'file1', T + '/sym'))
        assert stat.S_ISLNK(stat_of(ctx, T + '/sym', follow=False).nfs_mode)
        assert stat.S_ISREG(stat_of(ctx, T + '/sym').nfs_mode)   # followed
    check('symlink + lstat/stat', symlink)

    def readlink():
        buf = bytearray(256)
        rc(nfs_readlink(ctx, T + '/sym', buf, len(buf)))
        target = bytes(buf).split(b'\0', 1)[0].decode()
        assert target == 'file1', target
        return target
    check('readlink', readlink)

    def rename():
        rc(nfs_rename(ctx, T + '/hard', T + '/renamed'))
        names = listdir(ctx, T)
        assert 'renamed' in names and 'hard' not in names
    check('rename (same dir)', rename)

    def rename_dir():
        rc(nfs_rename(ctx, T + '/renamed', T + '/sub/moved'))
        assert 'moved' in listdir(ctx, T + '/sub')
    check('rename (across dirs)', rename_dir)

    def mknod():
        rc(nfs_mknod(ctx, T + '/fifo', stat.S_IFIFO | 0o644, 0))
        assert stat.S_ISFIFO(stat_of(ctx, T + '/fifo').nfs_mode)
    check('mknod (FIFO)', mknod,
          skip=(errno.EPERM, errno.ENOTSUP, errno.EINVAL))

    # ---- REMOVE ----
    check('unlink', lambda: rc(nfs_unlink(ctx, T + '/sym')))
    check('unlink missing -> ENOENT',
          lambda: expect_errno(nfs_unlink(ctx, T + '/sym'), errno.ENOENT))
    check('rmdir non-empty -> ENOTEMPTY',
          lambda: expect_errno(nfs_rmdir(ctx, T + '/sub'), errno.ENOTEMPTY))

    def unlink_open():       # delete-while-open behaviour
        with File(ctx, T + '/gone', os.O_CREAT | os.O_RDWR) as f:
            f.write(b'still here')
            rc(nfs_unlink(ctx, T + '/gone'))
            return 'read after unlink: %r' % f.pread(0, 10)
    check('unlink while open', unlink_open)

    # ---- high-level wrapper API too ----
    def wrapper_api():
        with nfs.open(T + '/hl.txt', mode='wb+') as f:
            f.write(b'high level')
        assert nfs.open(T + '/hl.txt', mode='r').read() == 'high level'
        assert nfs.isfile(T + '/hl.txt') and nfs.isdir(T)
    check('NFS.open/isfile/isdir wrapper', wrapper_api)

    # ---- lease renewal: idle for a while with a file open ----
    def lease():
        with File(ctx, T + '/lease', os.O_CREAT | os.O_RDWR) as f:
            f.write(b'a')
            time.sleep(int(os.environ.get('LEASE_SLEEP', '5')))
            f.write(b'b')
            assert f.pread(0, 2) == b'ab'
    check('open file across idle period', lease)

    # ---- LOCK / LOCKU: byte-range locks (NFSv4 only) ----
    def locking():
        path = T + '/lockfile'
        with nfs.open(path, mode='wb+') as f:
            f.write(b'x' * 100)
            f.lock(libnfs.F_WRLCK, 0, 50)      # LOCK  bytes 0-49
            assert not f.lockt(0, 50)          # LOCKT: own lock never conflicts
            f.unlock(0, 50)                    # LOCKU
            f.lock(libnfs.F_RDLCK)             # shared lock, whole file
            f.unlock()
    check('lock/unlock (byte-range)', locking)

    # ---- cleanup ----
    check('cleanup (recursive remove)', lambda: rmtree(ctx, T))

    print("\n%(PASS)d passed, %(FAIL)d failed, %(SKIP)d skipped" % results)
    print("""
Not reachable through this binding (no wrapper exists): delegations,
ACLs/named attributes, SECINFO, COPY/CLONE and fallocate().  Those need
the C API or new SWIG wrappers.

SEEK_DATA and SEEK_HOLE (NFSv4.2 only) do work: pass them as `whence` to
nfs_lseek() on a mount made with version=4.2.

NFSv4.1+ sessions (EXCHANGE_ID, CREATE_SESSION, SEQUENCE, ...) are set up by
libnfs itself; mount with version=4.1 or version=4.2 to use them.""")
    return 1 if results['FAIL'] else 0


if __name__ == '__main__':
    sys.exit(main())
