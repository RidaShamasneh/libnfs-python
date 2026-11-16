#!/usr/bin/env python3
from os import environ

try:
    from setuptools import setup, Extension
    from setuptools.command.build_ext import build_ext
except ImportError:
    from distutils.core import setup, Extension
    from distutils.command.build_ext import build_ext

# Although setuptools supports swig, it fails to copy the generated
# Python wrapper: http://stackoverflow.com/questions/12491328

cmdclass = { }

try:
    from setuptools.command.install import install
except ImportError:
    pass
else:
    class Install(install):
        def run(self):
            self.run_command('build_ext')
            install.run(self)
    cmdclass['install'] = Install

from distutils.command.build import build

class Build(build):
    def run(self):
        self.run_command('build_ext')
        build.run(self)
cmdclass['build'] = Build

name = 'libnfs'
# Matches the libnfs release bundled in the wheels (LIBNFS_REF in
# .github/scripts/build-libnfs.sh). For a bindings-only fix on top of the same
# libnfs, use a post-release such as 8.0.0.post1.
version = '8.0.0'
readme = 'README'
download_url = "https://github.com/sahlberg/libnfs-python/libnfs-" + \
                                                          version + ".tar.gz"
with open(readme, "r") as f:
    long_description = f.read()

_libnfs = Extension(name='libnfs._libnfs',
                   sources=['libnfs/libnfs.i'],
                   swig_opts=['-shadow', '-threads'],
                   extra_link_args=['-g'],
                   extra_compile_args=['-g'],
                   libraries=['nfs'],
)


setup(name = name,
      version = version,
      description = 'NFS client for Python.',
      long_description = long_description,
      long_description_content_type = 'text/plain',
      license = 'LGPLv2.1',
      platforms = ['any'],
      author = 'Ronnie Sahlberg',
      author_email = 'ronniesahlberg@gmail.com',
      url = 'https://github.com/sahlberg/libnfs-python/',
      download_url = download_url,
      packages = ['libnfs'],
      python_requires='>=3.6',
      classifiers = [
          'Development Status :: 4 - Beta',
          'Intended Audience :: Developers',
          'Operating System :: OS Independent',
          'Programming Language :: C',
          'Programming Language :: Python',
          'Programming Language :: Python :: 3 :: Only',
          'Topic :: Software Development :: Libraries :: Python Modules',
          'Topic :: Communications :: File Sharing',
          'Topic :: System :: Filesystems',
      ],
      ext_modules = [_libnfs],
      cmdclass = cmdclass,
      )
