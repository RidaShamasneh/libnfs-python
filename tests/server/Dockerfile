# A userspace NFS server (NFS-Ganesha) exporting /export over NFSv3 and NFSv4.
# Used by the integration tests in ../test_nfs.py.
FROM ubuntu:24.04

RUN apt-get update \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        nfs-ganesha nfs-ganesha-vfs rpcbind dbus \
 && rm -rf /var/lib/apt/lists/*

COPY ganesha.conf /etc/ganesha/ganesha.conf
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 111 2049
ENTRYPOINT ["/entrypoint.sh"]
