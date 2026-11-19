#   Copyright (C) 2014 by Ronnie Sahlberg <ronniesahlberg@gmail.com>
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU Lesser General Public License as published by
#   the Free Software Foundation; either version 2.1 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU Lesser General Public License for more details.
#
#   You should have received a copy of the GNU Lesser General Public License
#   along with this program; if not, see <http://www.gnu.org/licenses/>.

import errno
import os
import stat
from .libnfs import *

try:
    from fcntl import F_RDLCK, F_WRLCK, F_UNLCK
except ImportError:     # not a POSIX platform; use the Linux values
    F_RDLCK, F_WRLCK, F_UNLCK = 0, 1, 2

def _stat_to_dict(stat):
        return {'dev': stat.nfs_dev,
                'ino': stat.nfs_ino,
                'mode': stat.nfs_mode,
                'nlink': stat.nfs_nlink,
                'uid': stat.nfs_uid,
                'gid': stat.nfs_gid,
                'rdev': stat.nfs_rdev,
                'size': stat.nfs_size,
                'blksize': stat.nfs_blksize,
                'blocks': stat.nfs_blocks,
                'atime': {'sec':  stat.nfs_atime,
                          'nsec': stat.nfs_atime_nsec},
                'ctime': {'sec':  stat.nfs_ctime,
                          'nsec': stat.nfs_ctime_nsec},
                'mtime': {'sec':  stat.nfs_mtime,
                          'nsec': stat.nfs_mtime_nsec}
                }


class NFSFH:
    def __init__(self, nfs, path, mode='r', codec=None):

        self._nfs = nfs
        self._name = path

        self._codec = codec or 'utf-8'
        self._binary = True if 'b' in mode else False

        if path[:6] == "nfs://":
            _pos = path.rfind('/')
            _dir = path[:_pos]
            path = path[_pos:]
            self._private_context = NFS(_dir)
            self._nfs = self._private_context._nfs

        _plus = True if '+' in mode else False
        _mode = 0
        if 'r' in mode:
            _mode = os.O_RDWR if _plus else os.O_RDONLY
        if 'w' in mode:
            _mode = os.O_RDWR if _plus else os.O_WRONLY
            _mode |= os.O_CREAT|os.O_TRUNC
        if 'a' in mode:
            _mode = os.O_RDWR if _plus else os.O_WRONLY
            _mode |= os.O_CREAT|os.O_APPEND

        self._nfsfh = new_NFSFileHandle()
        _status = nfs_open(self._nfs, path, _mode, self._nfsfh)
        if _status == -errno.ENOENT and _mode & os.O_CREAT:
            _status = nfs_open2(self._nfs, path, _mode, 0o664, self._nfsfh)
        if _status == -errno.ENOENT:
                raise IOError(errno.ENOENT, 'No such file or directory');
        if _status != 0:
            _errmsg = "open failed: %s" % (os.strerror(-_status),)
            raise ValueError(_errmsg)
        self._nfsfh = NFSFileHandle_value(self._nfsfh)
        self._closed = False
        self._need_flush = False
        self._writing = True if _mode & (os.O_RDWR|os.O_WRONLY) else False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def close(self):
        if self._closed:
            return
        if self._need_flush:
            self.flush()
        nfs_close(self._nfs, self._nfsfh)
        self._closed = True

    def write(self, data):
        if self._closed:
            raise ValueError('I/O operation on closed file')
        if not self._writing:
            raise IOError('Trying to write on file open for reading')

        if not self._binary:
            if not isinstance(data, str):
                raise TypeError(f'write() argument must be str, not {type(data).__name__}')
            data = data.encode(self._codec)

        with memoryview(data) as view:
            ret = nfs_write(self._nfs, self._nfsfh, view, view.nbytes)
        self._need_flush = True
        if ret < 0:
            raise IOError(-ret, os.strerror(-ret))

        return ret

    def read(self, size=-1):
        if size < 0:
            _pos = self.tell()

            _st = nfs_stat_64()
            nfs_fstat64(self._nfs, self._nfsfh, _st)

            size = _st.nfs_size - _pos

        buf = bytearray(size)
        ret = nfs_read(self._nfs, self._nfsfh, buf, len(buf))
        if ret < 0:
            raise IOError(-ret, os.strerror(-ret))

        data = bytes(memoryview(buf)[:ret])
        return data if self._binary else data.decode(self._codec)

    def fstat(self):
        _stat = nfs_stat_64()
        nfs_fstat64(self._nfs, self._nfsfh, _stat)
        return _stat_to_dict(_stat)

    def tell(self):
        _pos = new_uint64_t_ptr()
        nfs_lseek(self._nfs, self._nfsfh, 0, os.SEEK_CUR, _pos)
        _pos = uint64_t_ptr_value(_pos)
        return _pos

    def seek(self, offset, whence=os.SEEK_CUR):
        _pos = new_uint64_t_ptr()
        nfs_lseek(self._nfs, self._nfsfh, offset, whence, _pos)

    def truncate(self, offset=-1):
        if offset < 0:
            offset = self.tell()
        nfs_ftruncate(self._nfs, self._nfsfh, offset)

    def fileno(self):
        _st = nfs_stat_64()
        nfs_fstat64(self._nfs, self._nfsfh, _st)
        return _st.nfs_ino

    def flush(self):
        if self._closed:
            raise ValueError('I/O operation on closed file');
        nfs_fsync(self._nfs, self._nfsfh)
        self._need_flush = False

    def lock(self, lock_type=F_WRLCK, start=0, length=0,
             whence=os.SEEK_SET, blocking=False):
        """Take an NFSv4 byte-range lock (LOCK).

        lock_type is F_RDLCK (shared) or F_WRLCK (exclusive); length 0 means
        'to end of file'.  Without blocking, an IOError is raised if another
        client holds a conflicting lock.  libnfs does not translate
        NFS4ERR_DENIED, so that conflict is reported as EIO.
        """
        if self._closed:
            raise ValueError('I/O operation on closed file')
        fl = nfs4_flock()
        fl.l_type = lock_type
        fl.l_whence = os.SEEK_SET
        fl.l_start = self._lock_start(start, whence)
        fl.l_len = self._lock_length(length)
        cmd = NFS4_F_SETLKW if blocking else NFS4_F_SETLK
        ret = nfs_fcntl(self._nfs, self._nfsfh, cmd, fl)
        if ret < 0:
            raise self._lock_error(ret)

    def unlock(self, start=0, length=0, whence=os.SEEK_SET):
        """Release a byte-range lock (LOCKU)."""
        if self._closed:
            raise ValueError('I/O operation on closed file')
        # nfs_fcntl(F_UNLCK) does not record the stateid returned by LOCKU,
        # so any later lock on this file fails.  nfs_lockf(F_ULOCK) does.
        ret = self._lockf_at(NFS4_F_ULOCK, start, length, whence)
        if ret < 0:
            raise self._lock_error(ret)

    def lockt(self, start=0, length=0, whence=os.SEEK_SET):
        """Test a byte range for a conflicting lock (LOCKT).

        Returns True if another client holds a lock that would conflict with
        an exclusive lock on the range, False if the range is free.  Locks
        taken through this same context never conflict with themselves.
        """
        if self._closed:
            raise ValueError('I/O operation on closed file')
        ret = self._lockf_at(NFS4_F_TEST, start, length, whence)
        if ret == 0:
            return False
        # libnfs maps NFS4ERR_DENIED to EIO; tell it apart from real errors
        if 'NFS4ERR_DENIED' in (nfs_get_error(self._nfs) or ''):
            return True
        raise self._lock_error(ret)

    def _lockf_at(self, op, start, length, whence):
        """nfs_lockf() works at the current offset: seek there and back."""
        start = self._lock_start(start, whence)
        length = self._lock_length(length)
        pos = self.tell()
        nfs_lseek(self._nfs, self._nfsfh, start, os.SEEK_SET, new_uint64_t_ptr())
        try:
            return nfs_lockf(self._nfs, self._nfsfh, op, length)
        finally:
            nfs_lseek(self._nfs, self._nfsfh, pos, os.SEEK_SET, new_uint64_t_ptr())

    def _lock_error(self, ret):
        # Add libnfs's own message: errno alone (usually EIO) hides which
        # NFS4ERR_* the server returned.
        return IOError(-ret, '%s (%s)' % (os.strerror(-ret),
                                          nfs_get_error(self._nfs)))

    def _lock_start(self, start, whence):
        if whence == os.SEEK_CUR:
            return self.tell() + start
        if whence == os.SEEK_END:
            _st = nfs_stat_64()
            nfs_fstat64(self._nfs, self._nfsfh, _st)
            return _st.nfs_size + start
        return start

    @staticmethod
    def _lock_length(length):
        # NFSv4 spells 'to end of file' as 2**64-1; it rejects 0.
        return length if length else 0xFFFFFFFFFFFFFFFF

    def isatty(self):
        return False

    @property
    def name(self):
        return self._name

    @property
    def closed(self):
        return self._closed

    @property
    def error(self):
        return nfs_get_error(self._nfs)


class NFS:
    def __init__(self, url):
        self._url = None
        self._nfs = nfs_init_context()
        if self._nfs is None:
            raise IOError('Failed to initialize an NFS context')
        self._url = nfs_parse_url_dir(self._nfs, url)
        if self._url is None:
            raise IOError(nfs_get_error(self._nfs))
        ret = nfs_mount(self._nfs, self._url.server, self._url.path)
        if ret != 0:
            raise IOError(nfs_get_error(self._nfs))

    def __del__(self):
        if self._url is not None:
            nfs_destroy_url(self._url)
        if self._nfs is not None:
            nfs_destroy_context(self._nfs)

    def open(self, path, mode='r', codec=None):
        return NFSFH(self._nfs, path, mode=mode, codec=codec)

    def stat(self, path):
        _stat = nfs_stat_64()
        ret = nfs_stat64(self._nfs, path, _stat)
        if ret == -errno.ENOENT:
                raise IOError(errno.ENOENT, 'No such file or directory');
        return _stat_to_dict(_stat)

    def lstat(self, path):
        _stat = nfs_stat_64()
        ret = nfs_lstat64(self._nfs, path, _stat)
        if ret == -errno.ENOENT:
                raise IOError(errno.ENOENT, 'No such file or directory');
        return _stat_to_dict(_stat)

    def unlink(self, path):
        ret = nfs_unlink(self._nfs, path)
        if ret == -errno.ENOENT:
                raise IOError(errno.ENOENT, 'No such file or directory');
        return ret

    def mkdir(self, path):
        ret = nfs_mkdir(self._nfs, path)
        if ret == -errno.ENOENT:
                raise IOError(errno.ENOENT, 'No such file or directory');
        return ret

    def rmdir(self, path):
        ret = nfs_rmdir(self._nfs, path)
        if ret == -errno.ENOENT:
                raise IOError(errno.ENOENT, 'No such file or directory');
        return ret

    def listdir(self, path):
        d = new_NFSDirHandle()
        ret = nfs_opendir(self._nfs, path, d)
        if ret == -errno.ENOENT:
                raise IOError(errno.ENOENT, 'No such file or directory');
        d = NFSDirHandle_value(d)

        ret = []
        while True:
                de = nfs_readdir(self._nfs, d)
                if de == None:
                        break

                ret.append(de.name)
        return ret

    def makedirs(self, path):
        npath = "/"
        for p in path.split(os.path.sep):
            npath = os.path.join(npath, p)
            self.mkdir(npath)

    def rawstat(self, path):
        _stat = nfs_stat_64()
        ret = nfs_stat64(self._nfs, path, _stat)
        if ret == -errno.ENOENT:
                raise IOError(errno.ENOENT, 'No such file or directory')
        return _stat

    def isfile(self, path):
        """Test whether a path is a regular file"""
        try:
            st = self.rawstat(path)
        except IOError:
            return False
        return stat.S_ISREG(st.nfs_mode)

    def isdir(self, s):
        """Return true if the pathname refers to an existing directory."""
        try:
            st = self.rawstat(s)
        except IOError:
            return False
        return stat.S_ISDIR(st.nfs_mode)

    def rename(self, src, dst):
        """Rename file"""
        ret = nfs_rename(self._nfs, src, dst)
        if ret == -errno.ENOENT:
            raise IOError(errno.ENOENT, 'No such file or directory')
        return ret

    @property
    def error(self):
        return nfs_get_error(self._nfs)


def open(url, mode='r', codec=None):
    return NFSFH(None, url, mode=mode, codec=codec)
