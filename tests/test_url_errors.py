"""Tests for URLs that libnfs refuses to parse; no NFS server is needed."""
import unittest

import libnfs


class UrlErrorTests(unittest.TestCase):
    def test_unsupported_version_reports_libnfs_error(self):
        with self.assertRaises(IOError) as cm:
            libnfs.NFS('nfs://127.0.0.1/export/?version=4.3')
        self.assertIn('4.3', str(cm.exception))

    def test_failure_is_not_an_attribute_error(self):
        # A failed parse used to surface as
        # AttributeError: 'NoneType' object has no attribute 'server'
        try:
            libnfs.NFS('nfs://127.0.0.1/export/?version=4.3')
        except IOError:
            pass


if __name__ == '__main__':
    unittest.main()
