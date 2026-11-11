#!/bin/bash
# Build and install the C libnfs library into /usr/local (manylinux container).
set -euxo pipefail

LIBNFS_REF="${LIBNFS_REF:-libnfs-8.0.0}"

# CMake from PyPI: the CentOS 7 based manylinux2014 image has a version that
# is too old for libnfs.
PIP="$(ls /opt/python/cp3*/bin/pip | tail -1)"
"$PIP" install cmake
export PATH="$(dirname "$PIP"):$PATH"
git clone --depth 1 --branch "$LIBNFS_REF" \
  https://github.com/sahlberg/libnfs.git /tmp/libnfs
cmake -S /tmp/libnfs -B /tmp/libnfs/build \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_INSTALL_PREFIX=/usr/local \
  -DCMAKE_INSTALL_LIBDIR=lib
cmake --build /tmp/libnfs/build -j"$(nproc)"
cmake --install /tmp/libnfs/build
