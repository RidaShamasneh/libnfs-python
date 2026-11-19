"""Integration tests that run the bindings against a real NFS server.

The server is configured through the environment, so the same tests can run
against the Docker container used in CI or against any other server you can
write to:

    NFS_TEST_SERVER   host name or address of the server       (required)
    NFS_TEST_EXPORT   exported path to mount                   (default /export)
    NFS_TEST_ARGS     extra URL arguments, e.g. "uid=0&gid=0"  (optional)

Without NFS_TEST_SERVER the tests are skipped.  Every test runs once with
NFSv3 and once with NFSv4, inside a directory of its own that is removed
afterwards.  Only the standard library is needed:

    python -m unittest discover -v tests
"""
import errno
import os
import stat
import unittest
import uuid

import libnfs

SERVER = os.environ.get('NFS_TEST_SERVER')
EXPORT = os.environ.get('NFS_TEST_EXPORT', '/export')
EXTRA_ARGS = os.environ.get('NFS_TEST_ARGS', '')


def make_url(version, export=EXPORT):
    args = ['version=%s' % version]
    if EXTRA_ARGS:
        args.append(EXTRA_ARGS)
    return 'nfs://%s%s?%s' % (SERVER, export, '&'.join(args))


@unittest.skipUnless(SERVER, 'NFS_TEST_SERVER is not set')
class NFSTests:
    """Test cases; the concrete NFSv3/NFSv4 classes below set `version`."""

    version = None

    def setUp(self):
        self.nfs = libnfs.NFS(make_url(self.version))
        self.workdir = '/unittest-' + uuid.uuid4().hex
        self.nfs.mkdir(self.workdir)
        self.addCleanup(self._remove_tree, self.workdir)

    def _remove_tree(self, path):
        for name in self.nfs.listdir(path):
            if name in ('.', '..'):
                continue
            child = path + '/' + name
            if self.nfs.isdir(child):
                self._remove_tree(child)
            else:
                self.nfs.unlink(child)
        self.nfs.rmdir(path)

    def path(self, name):
        return self.workdir + '/' + name

    def write_file(self, path, data):
        f = self.nfs.open(path, mode='wb')
        f.write(bytes(data))
        f.close()

    def read_file(self, path):
        f = self.nfs.open(path, mode='rb')
        data = f.read()
        f.close()
        return data

    def names(self, path):
        return set(self.nfs.listdir(path)) - {'.', '..'}

    # ------------------------------------------------------------- mount

    def test_mount(self):
        self.assertTrue(self.nfs.isdir('/'))

    def test_mount_missing_export_fails(self):
        with self.assertRaises(IOError):
            libnfs.NFS(make_url(self.version, export='/no-such-export'))

    # -------------------------------------------------- open/read/write

    def test_write_then_read_back(self):
        payload = bytes(range(256)) * 16
        self.write_file(self.path('data.bin'), payload)
        self.assertEqual(self.read_file(self.path('data.bin')), payload)

    def test_read_with_size_and_seek(self):
        self.write_file(self.path('data.txt'), b'0123456789')
        f = self.nfs.open(self.path('data.txt'), mode='rb')
        self.assertEqual(f.read(4), b'0123')
        self.assertEqual(f.tell(), 4)
        f.seek(7, os.SEEK_SET)
        self.assertEqual(f.read(), b'789')
        f.close()

    def test_large_write(self):
        # Larger than a single READ/WRITE, to exercise chunking.
        payload = os.urandom(3 * 1024 * 1024)
        self.write_file(self.path('large.bin'), payload)
        self.assertEqual(self.nfs.stat(self.path('large.bin'))['size'],
                         len(payload))
        self.assertEqual(self.read_file(self.path('large.bin')), payload)

    def test_text_mode_utf8(self):
        text = u'héllo wörld'
        f = self.nfs.open(self.path('text.txt'), mode='w')
        f.write(text)
        f.close()
        f = self.nfs.open(self.path('text.txt'), mode='r')
        self.assertEqual(f.read(), text)
        f.close()

    def test_write_truncates_existing_file(self):
        self.write_file(self.path('f'), b'a long first version')
        self.write_file(self.path('f'), b'short')
        self.assertEqual(self.read_file(self.path('f')), b'short')

    def test_append(self):
        self.write_file(self.path('f'), b'abc')
        f = self.nfs.open(self.path('f'), mode='ab')
        f.write(bytearray(b'def'))
        f.close()
        self.assertEqual(self.read_file(self.path('f')), b'abcdef')

    def test_open_missing_file_for_read(self):
        with self.assertRaises(IOError) as cm:
            self.nfs.open(self.path('missing'), mode='rb')
        self.assertEqual(cm.exception.errno, errno.ENOENT)

    def test_write_wrong_type(self):
        path = self.path('f')
        f = self.nfs.open(path, mode='w')
        with self.assertRaises(TypeError):
            f.write(b'non-binary mode')
        f.close()

        f = self.nfs.open(path, mode='wb')
        with self.assertRaises(TypeError):
            f.write('binary mode')
        f.close()

    # ------------------------------------------------------------- stat

    def test_stat_regular_file(self):
        self.write_file(self.path('file'), b'twelve bytes')
        st = self.nfs.stat(self.path('file'))
        self.assertTrue(stat.S_ISREG(st['mode']))
        self.assertFalse(stat.S_ISDIR(st['mode']))
        self.assertEqual(st['size'], 12)
        self.assertEqual(st['nlink'], 1)
        self.assertTrue(self.nfs.isfile(self.path('file')))
        self.assertFalse(self.nfs.isdir(self.path('file')))

    def test_stat_directory(self):
        st = self.nfs.stat(self.workdir)
        self.assertTrue(stat.S_ISDIR(st['mode']))
        self.assertTrue(self.nfs.isdir(self.workdir))
        self.assertFalse(self.nfs.isfile(self.workdir))

    def test_fstat(self):
        self.write_file(self.path('file'), b'12345')
        f = self.nfs.open(self.path('file'), mode='rb')
        st = f.fstat()
        f.close()
        self.assertTrue(stat.S_ISREG(st['mode']))
        self.assertEqual(st['size'], 5)
        self.assertEqual(st['ino'], self.nfs.stat(self.path('file'))['ino'])

    def test_stat_missing_path(self):
        with self.assertRaises(IOError) as cm:
            self.nfs.stat(self.path('missing'))
        self.assertEqual(cm.exception.errno, errno.ENOENT)

    # ---------------------------------------------------------- listdir

    def test_listdir(self):
        self.write_file(self.path('a'), b'a')
        self.write_file(self.path('b'), b'b')
        self.nfs.mkdir(self.path('sub'))
        self.assertEqual(self.names(self.workdir), {'a', 'b', 'sub'})

    def test_listdir_empty(self):
        self.assertEqual(self.names(self.workdir), set())

    def test_listdir_missing_directory(self):
        with self.assertRaises(IOError) as cm:
            self.nfs.listdir(self.path('missing'))
        self.assertEqual(cm.exception.errno, errno.ENOENT)

    # ------------------------------------------------------ mkdir/rmdir

    def test_mkdir_and_rmdir(self):
        self.assertEqual(self.nfs.mkdir(self.path('newdir')), 0)
        self.assertTrue(self.nfs.isdir(self.path('newdir')))
        self.assertEqual(self.nfs.rmdir(self.path('newdir')), 0)
        self.assertFalse(self.nfs.isdir(self.path('newdir')))

    def test_mkdir_nested(self):
        self.nfs.mkdir(self.path('a'))
        self.nfs.mkdir(self.path('a/b'))
        self.write_file(self.path('a/b/f'), b'x')
        self.assertEqual(self.names(self.path('a/b')), {'f'})

    def test_mkdir_existing_fails(self):
        self.assertEqual(self.nfs.mkdir(self.workdir), -errno.EEXIST)

    def test_mkdir_missing_parent(self):
        with self.assertRaises(IOError) as cm:
            self.nfs.mkdir(self.path('no/such/parent'))
        self.assertEqual(cm.exception.errno, errno.ENOENT)

    # ----------------------------------------------------------- unlink

    def test_unlink(self):
        self.write_file(self.path('doomed'), b'x')
        self.assertTrue(self.nfs.isfile(self.path('doomed')))
        self.assertEqual(self.nfs.unlink(self.path('doomed')), 0)
        self.assertFalse(self.nfs.isfile(self.path('doomed')))
        self.assertNotIn('doomed', self.nfs.listdir(self.workdir))

    def test_unlink_missing_file(self):
        with self.assertRaises(IOError) as cm:
            self.nfs.unlink(self.path('missing'))
        self.assertEqual(cm.exception.errno, errno.ENOENT)


class NFSv3Tests(NFSTests, unittest.TestCase):
    version = '3'


class NFSv4Tests(NFSTests, unittest.TestCase):
    version = '4'

    # ------------------------------------------------------------ locking
    # LOCK/LOCKT/LOCKU exist only in NFSv4.  A second NFS context is a
    # second client (own client id and lock owner), so it conflicts with
    # locks taken through the first one.

    def _two_clients(self, name):
        path = self.path(name)
        self.write_file(path, b'x' * 100)
        other = libnfs.NFS(make_url(self.version))
        return path, other

    def test_lock_conflict(self):
        path, other = self._two_clients('conflict')
        with self.nfs.open(path, mode='r+b') as a, \
                other.open(path, mode='r+b') as b:
            a.lock(libnfs.F_WRLCK, 0, 50)
            b.lock(libnfs.F_WRLCK, 50, 50)      # disjoint range is fine
            with self.assertRaises(IOError) as cm:
                b.lock(libnfs.F_WRLCK, 0, 50)   # overlaps a's lock
            # libnfs reports NFS4ERR_DENIED as EIO
            self.assertEqual(cm.exception.errno, errno.EIO)

    def test_unlock_releases_lock(self):
        path, other = self._two_clients('unlock')
        with self.nfs.open(path, mode='r+b') as a, \
                other.open(path, mode='r+b') as b:
            a.lock(libnfs.F_WRLCK, 0, 50)
            a.unlock(0, 50)
            b.lock(libnfs.F_WRLCK, 0, 50)       # free after LOCKU
            b.unlock(0, 50)

    def test_relock_after_unlock(self):
        path = self.path('relock')
        self.write_file(path, b'x' * 100)
        with self.nfs.open(path, mode='r+b') as f:
            for _ in range(3):
                f.lock(libnfs.F_WRLCK, 10, 20)
                f.unlock(10, 20)
            f.lock()                            # whole file (length 0)
            f.unlock()
            self.assertEqual(f.tell(), 0)       # unlock keeps the offset

    def test_shared_locks(self):
        path, other = self._two_clients('shared')
        with self.nfs.open(path, mode='r+b') as a, \
                other.open(path, mode='r+b') as b:
            a.lock(libnfs.F_RDLCK, 0, 0)
            b.lock(libnfs.F_RDLCK, 0, 0)        # readers share
            with self.assertRaises(IOError):
                b.lock(libnfs.F_WRLCK, 0, 0)    # upgrade blocked by a

    def test_lockf(self):
        path = self.path('lockf')
        self.write_file(path, b'x' * 10)
        with self.nfs.open(path, mode='r+b') as f:
            ctx, fh = self.nfs._nfs, f._nfsfh
            ret = libnfs.nfs_lockf(ctx, fh, libnfs.NFS4_F_TLOCK, 10)
            self.assertEqual(ret, 0, libnfs.nfs_get_error(ctx))
            ret = libnfs.nfs_lockf(ctx, fh, libnfs.NFS4_F_ULOCK, 10)
            self.assertEqual(ret, 0, libnfs.nfs_get_error(ctx))


if __name__ == '__main__':
    unittest.main()
