#!/bin/bash
# Build and install the C libnfs library into /usr/local (manylinux container).
set -euxo pipefail

LIBNFS_REF="${LIBNFS_REF:-master}"
LIBNFS_REPO="${LIBNFS_REPO:-https://github.com/sahlberg/libnfs.git}"

# RDMA transport (proto=rdma): only the libibverbs/librdmacm headers are needed
# to build. libnfs loads the libraries with dlopen() at run time, so the wheel
# imports on hosts without rdma-core and uses the host's rdma-core for RDMA.
# manylinux2014 (CentOS 7) uses yum, manylinux_2_28 (AlmaLinux 8) has dnf.
if command -v dnf >/dev/null; then PKGMGR=dnf; else PKGMGR=yum; fi
"$PKGMGR" install -y rdma-core-devel

# CMake from PyPI: the CentOS 7 based manylinux2014 image has a version that
# is too old for libnfs.
PIP="$(ls /opt/python/cp3*/bin/pip | tail -1)"
"$PIP" install cmake swig
# Used by the Python 3.6 builds, which cannot run the swig launcher themselves.
ln -sf "$(dirname "$PIP")/swig" /usr/local/bin/swig
export PATH="$(dirname "$PIP"):$PATH"
git clone --depth 1 --branch "$LIBNFS_REF" \
  "$LIBNFS_REPO" /tmp/libnfs
git -C /tmp/libnfs log -1 --format='Building libnfs %H %s'
cmake -S /tmp/libnfs -B /tmp/libnfs/build \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_INSTALL_PREFIX=/usr/local \
  -DCMAKE_INSTALL_LIBDIR=lib \
  -DENABLE_RDMA=ON
cmake --build /tmp/libnfs/build -j"$(nproc)"
cmake --install /tmp/libnfs/build
