#!/bin/bash
# Build and install the C libnfs library into /usr/local (manylinux container).
set -euxo pipefail

LIBNFS_REF="${LIBNFS_REF:-master}"
LIBNFS_REPO="${LIBNFS_REPO:-https://github.com/sahlberg/libnfs.git}"

# RDMA transport (proto=rdma): only the libibverbs/librdmacm headers are needed
# to build. libnfs loads the libraries with dlopen() at run time, so the wheel
# imports on hosts without rdma-core and uses the host's rdma-core for RDMA.
if command -v dnf >/dev/null; then
  dnf install -y rdma-core-devel
else
  # The manylinux2014 image (CentOS 7, Python 3.6/3.7) is end of life and its
  # mirrors are gone: use the CentOS vault, which keeps the final 7.9 packages.
  sed -i -e 's|^mirrorlist=|#mirrorlist=|' \
         -e 's|^#\s*baseurl=http://mirror.centos.org|baseurl=http://vault.centos.org|' \
         /etc/yum.repos.d/*.repo
  yum install -y rdma-core-devel
fi

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
