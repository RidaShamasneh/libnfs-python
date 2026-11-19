# libnfs-python

This module is an NFS client for Python.

This project is hosted at https://github.com/RidaShamasneh/libnfs-python

This module depends on the libnfs library.
You must first install libnfs before you can use this module.
Libnfs can be found at https://github.com/sahlberg/libnfs

The two main classes in this module are NFS and NFSFH.
NFS represents an NFS context that describes a mount point.
NFSFH is the main class that implements a file-like object for NFS files.

## Project history and maintenance

libnfs-python was originally written by [Ronnie Sahlberg](https://github.com/sahlberg),
the author of [libnfs](https://github.com/sahlberg/libnfs). The original repository,
[sahlberg/libnfs-python](https://github.com/sahlberg/libnfs-python), has been archived,
and its [final commit](https://github.com/sahlberg/libnfs-python/commit/04b91d4c2ba8e7e2be4f53393bdb3d914c7c77ad) points users here.

**This repository is now the official home of libnfs-python** and is maintained by
[Rida Shamasneh](https://github.com/RidaShamasneh). Many thanks to Ronnie for creating
the bindings and for libnfs itself.

### What's changing

- Bindings are being updated to match the current libnfs `master` branch.
- Python 3 only; Python 2 support has been dropped.
- New PyPI releases are planned. The existing [`libnfs`](https://pypi.org/project/libnfs/)
  package on PyPI (`1.0.post4`, 2016) is not built from this repository; the package
  name for new releases will be announced here once confirmed. Until then, install
  from source (see INSTALL).
- More utilities and examples are planned.

### Getting help

- **Bugs and feature requests:** [GitHub Issues](https://github.com/RidaShamasneh/libnfs-python/issues)
- **Questions and discussion:** [libnfs-python Google Group](https://groups.google.com/g/libnfs-python)
- **Problems in the C library itself:** [libnfs issues](https://github.com/sahlberg/libnfs/issues)

Issues and pull requests left open on the archived repository can't receive replies.
If one still affects you, please open it again here.

## License

This module is distributed under LGPL version 2.1.
Please see COPYING for the full text of this license.

## Context-full access

In the context-full mode you will first need to mount an NFS share and create
an NFS context before you can access any files. This NFS context is then used
for all future access to files in that mount point.

The benefit with this mode is that since performing the actual NFS mount is
very expensive you only need to perform it once, when creating the NFS object
and can reuse the mount for any future files you want to access.

In this mode absolute paths are relative to the mount point for the NFS object.

Example:

```python
import libnfs

nfs = libnfs.NFS('nfs://127.0.0.1/data/tmp/')
path = '/foo-test'

file = nfs.open(path, mode='w+')
file.write('libnfs-python!')
file.close()

with nfs.open(path, mode='r') as file:
    print(file.read())
```

## Context-free access

This module also provides a mode where you can directly open and access
a file-like object without first having to instantiate a NFS mount.
In this case the file-like object will internally create an NFS mount
for the duration of the lifespan of the file-like object.

In this mode you invoke the `libnfs.open()` function with an NFS url
that points to a file:

Example:

```python
import libnfs

url = 'nfs://127.0.0.1/data/tmp/foo-test'
file = libnfs.open(url, mode='w+')
file.write('libnfs-python!')
file.close()

with libnfs.open(url, mode='r') as file:
    print(file.read())
```

In the example above we create two instances of a file-like object. First
we create and write to the file and second time we read the file back and
print it. This is however both expensive and potentially poor performing.
The reason is that when we use context-free file-like objects we have to
create an NFS mount internally for each object and this is expensive.

Basically, when creating an NFS mount, the NFS protocol requires that we
perform the following operations/roundtrips.

### Creating an NFS context

1. Establish TCP connection to portmapper (TCP port 111) on the server.
2. Send a Portmapper NULL command to verify we are connected to a genuine
   Portmapper and that it is alive.
3. Send a Portmapper GetPort command to fetch which port the MOUNT daemon
   is running on.
   Close the TCP connection.
4. Establish a TCP connection to the MOUNT daemon
5. Send a MOUNT NULL command to verify the MOUNT daemon is alive.
6. Send a MOUNT MNT command to fetch the NFS file handle for the mount point.
   Close the TCP connection.
7. Establish TCP connection to portmapper (TCP port 111) on the server.
8. Send a Portmapper NULL command to verify we are connected to a genuine
   Portmapper and that it is alive.
9. Send a Portmapper GetPort command to fetch which port the DAEMON daemon
   is running on.
   Close the TCP connection.
10. Establish a TCP connection to the NFS daemon
11. Send a NFS NULL command to verify the NFS daemon is alive.
12. Send a NFS FSINFO command to fetch some basic information about the
    filesystem we just mounted.
13. Send a NFS GETATTR command to fetch some information about the root
    directory for this mount.

When using context-free handles we have to perform these steps every time
a new file-like object is created making it very expensive.

The benefit with context-free handles is that they are very convenient to use.
Just pass an NFS url to the `libnfs.open()` function and you have a file-like
object. The drawback is that every context-free handle have to perform their
own NFS mount internally. If you plan to access multiple/many files you
should consider using context-full handles instead.

## Command-line tools

`utils/` has small tools that also serve as short, complete examples of the
API. They take `nfs://server/export/path` URLs and accept
`--nfs-version {3,4,4.1,4.2}` (libnfs defaults to NFSv3).

```sh
python utils/nfs-ls.py -l nfs://server/export/dir          # list a directory
python utils/nfs-cat.py nfs://server/export/dir/file       # print files
python utils/nfs-cp.py notes.txt nfs://server/export/dir/  # upload
python utils/nfs-cp.py nfs://server/export/dir/file .      # download
python utils/nfs-cp.py nfs://a/data/f nfs://b/backup/f     # server to server
```

## Running the tests

`tests/test_nfs.py` runs the bindings against a real NFS server: mount, open,
read, write, stat, listdir, mkdir, rmdir and unlink, once over NFSv3 and once
over NFSv4. Only the Python standard library is needed.

Point it at any server you can write to:

```sh
python setup.py build_ext --inplace
export NFS_TEST_SERVER=192.0.2.10        # required, else tests are skipped
export NFS_TEST_EXPORT=/export           # default /export
export NFS_TEST_ARGS='uid=0&gid=0'       # optional extra URL arguments
python -m unittest discover -v tests
```

CI (`.github/workflows/tests.yml`) installs the Linux kernel NFS server
(`nfs-kernel-server`) on the runner and runs the same tests against it.

## Mailing list

A libnfs-python mailing list is available at
<http://groups.google.com/group/libnfs-python>.
Announcements of new versions of libnfs-python will be posted to this list.
