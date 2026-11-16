#!/bin/sh
set -e

mkdir -p /export /run/dbus /var/run/ganesha /var/lib/nfs/ganesha
chmod 777 /export

# NFSv3 needs the portmapper to find MOUNT and NFS.
rpcbind

# Ganesha talks to the system bus for administration; it is not required
# for serving, so do not fail if it cannot be started.
rm -f /run/dbus/pid
dbus-daemon --system --fork || true

exec ganesha.nfsd -F -L /dev/stdout -N NIV_EVENT -f /etc/ganesha/ganesha.conf
