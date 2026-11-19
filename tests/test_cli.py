"""Tests for the command-line tools in utils/ (nfs-ls, nfs-cat, nfs-cp).

They run the scripts as subprocesses against a real server, configured the
same way as test_nfs.py (NFS_TEST_SERVER, NFS_TEST_EXPORT).  Without
NFS_TEST_SERVER they are skipped.
"""
import os
import subprocess
import sys
import tempfile
import unittest
import uuid

import libnfs

SERVER = os.environ.get('NFS_TEST_SERVER')
EXPORT = os.environ.get('NFS_TEST_EXPORT', '/export')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UTILS = os.path.join(ROOT, 'utils')


def run(tool, *args):
    env = dict(os.environ)
    env['PYTHONPATH'] = os.pathsep.join(
        [ROOT] + ([env['PYTHONPATH']] if env.get('PYTHONPATH') else []))
    return subprocess.run([sys.executable, os.path.join(UTILS, tool), *args],
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)


@unittest.skipUnless(SERVER, 'NFS_TEST_SERVER is not set')
class CommandLineToolTests(unittest.TestCase):

    def setUp(self):
        self.base = 'nfs://%s%s' % (SERVER, EXPORT)
        self.nfs = libnfs.NFS('%s?version=4' % self.base)
        self.dirname = 'cli-' + uuid.uuid4().hex
        self.nfs.mkdir('/' + self.dirname)
        self.addCleanup(self.remove_dir)
        self.url = '%s/%s' % (self.base, self.dirname)
        self.local = tempfile.TemporaryDirectory()
        self.addCleanup(self.local.cleanup)

    def remove_dir(self):
        for name in self.nfs.listdir('/' + self.dirname):
            if name not in ('.', '..'):
                self.nfs.unlink('/%s/%s' % (self.dirname, name))
        self.nfs.rmdir('/' + self.dirname)

    def tool(self, name, *args):
        return run(name, '--nfs-version', '4', *args)

    def write_local(self, name, data):
        path = os.path.join(self.local.name, name)
        with open(path, 'wb') as f:
            f.write(data)
        return path

    def test_cp_upload_cat_download_roundtrip(self):
        data = os.urandom(2 * 1024 * 1024 + 17)     # more than one chunk
        src = self.write_local('src.bin', data)
        remote = self.url + '/data.bin'

        r = self.tool('nfs-cp.py', src, remote)
        self.assertEqual(r.returncode, 0, r.stderr)

        r = self.tool('nfs-cat.py', remote)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, data)

        down = os.path.join(self.local.name, 'down.bin')
        r = self.tool('nfs-cp.py', remote, down)
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(down, 'rb') as f:
            self.assertEqual(f.read(), data)

    def test_cp_between_nfs_urls_and_into_directory(self):
        src = self.write_local('one.txt', b'copy me')
        self.assertEqual(
            self.tool('nfs-cp.py', src, self.url + '/one.txt').returncode, 0)
        r = self.tool('nfs-cp.py', self.url + '/one.txt', self.url + '/two.txt')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.tool('nfs-cat.py', self.url + '/two.txt').stdout,
                         b'copy me')
        # a local directory as destination keeps the file name
        r = self.tool('nfs-cp.py', self.url + '/two.txt', self.local.name)
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(os.path.join(self.local.name, 'two.txt'), 'rb') as f:
            self.assertEqual(f.read(), b'copy me')

    def test_cp_into_remote_directory(self):
        src = self.write_local('named.txt', b'into a dir')
        for dest in (self.url + '/', self.url):      # with and without slash
            with self.subTest(dest=dest):
                r = self.tool('nfs-cp.py', src, dest)
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertEqual(
                    self.tool('nfs-cat.py', self.url + '/named.txt').stdout,
                    b'into a dir')
                self.nfs.unlink('/%s/named.txt' % self.dirname)

    def test_cp_into_missing_directory_fails(self):
        src = self.write_local('x.txt', b'x')
        r = self.tool('nfs-cp.py', src, self.url + '/no-such-dir/x.txt')
        self.assertEqual(r.returncode, 1)
        self.assertNotIn(b'Traceback', r.stderr)

    def test_cat_several_files(self):
        for name, data in (('a', b'first\n'), ('b', b'second\n')):
            self.tool('nfs-cp.py', self.write_local(name, data),
                      '%s/%s' % (self.url, name))
        r = self.tool('nfs-cat.py', self.url + '/a', self.url + '/b')
        self.assertEqual(r.stdout, b'first\nsecond\n')

    def test_ls(self):
        for name in ('alpha', '.hidden'):
            self.tool('nfs-cp.py', self.write_local(name, b'12345'),
                      '%s/%s' % (self.url, name))
        r = self.tool('nfs-ls.py', self.url)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.split(), [b'alpha'])
        r = self.tool('nfs-ls.py', '-a', self.url)
        self.assertEqual(sorted(r.stdout.split()), [b'.hidden', b'alpha'])
        r = self.tool('nfs-ls.py', '-l', self.url)
        line = [l for l in r.stdout.splitlines() if l.endswith(b' alpha')][0]
        self.assertTrue(line.startswith(b'-rw'), line)
        self.assertIn(b' 5 ', line)                 # size

    def test_errors_exit_non_zero_without_traceback(self):
        for args in (('nfs-cat.py', self.url + '/missing'),
                     ('nfs-ls.py', self.base + '/' + uuid.uuid4().hex),
                     ('nfs-cp.py', self.url + '/missing',
                      os.path.join(self.local.name, 'x'))):
            with self.subTest(tool=args[0]):
                r = self.tool(*args)
                self.assertEqual(r.returncode, 1)
                self.assertNotIn(b'Traceback', r.stderr)
                self.assertTrue(r.stderr.startswith(args[0].encode()))

    def test_cp_needs_one_url(self):
        r = self.tool('nfs-cp.py', 'a', 'b')
        self.assertEqual(r.returncode, 2)


if __name__ == '__main__':
    unittest.main()
