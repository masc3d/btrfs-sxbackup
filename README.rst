btrfs-sxbackup
**************

Btrfs snapshot backup utility

* Push/pull support via SSH
* Housekeeping
* Compression of transferred data
* Syslog logging

System dependencies
===================
Required
--------
The following packages have to be available on both source and destination

* btrfs-progs

The system executing btrfs-backup requires

* python3

Optional
--------
* ssh (for remote push/pull, not required for local operation)
* lzop (for compression support if desired)
* pv (provides progress indication if installed)

Installation
============
.. code ::

    pip install btrfs-sxbackup

Setup
=====
* when using ssh, public/private key authentication should be set up

Usage examples
==============

Pull snapshot backups of **/** on remote host **myhost.org** to local subvolume **/backup/myhost**

.. code ::

    btrfs-sxbackup ssh://root@myhost.org:/ /backup/myhost

Push snapshot backups of local subvolume **/** to remote subvolume **/backup/myhost** on host **mybackupserver.org**

.. code ::

    btrfs-sxbackup / ssh://root@mybackupserver.org:/backup/myhost

Cron example
------------

Cronhob performing a local and remote pull backup job

.. code ::

    # /etc/cron.d/btrfs-sxbackup
    PATH="/usr/sbin:/usr/bin:/sbin:/bin"
    30 2    * * *     root     btrfs-sxbackup / /mnt/backup/localsystem/ -sk 3 -dk "1d = 4/d, 1w = daily, 2m = none"
    0 3     * * *     root     btrfs-sxbackup ssh://root@remotesystem/ /mnt/backup/remotesystem/ -sk 3 -dk "1d = 4/d, 1w = daily, 2m = none"

Synopsis and options
====================

.. code ::

    usage: btrfs-sxbackup [-h] [-c] [-q] [-sk SOURCE_KEEP] [-dk DESTINATION_KEEP]
                          [-ss SOURCE_CONTAINER_SUBVOLUME] [-li LOG_IDENT]
                          [--version]
                          source_subvolume destination_container_subvolume

    positional arguments:
      source_subvolume      Source subvolume to backup. Local path or SSH url.
      destination_container_subvolume
                            Destination subvolume receiving snapshots. Local path
                            or SSH url.

    optional arguments:
      -h, --help            show this help message and exit
      -c, --compress        Enables compression during transmission, requires lzop
                            to be installed on both source and destination
      -q, --quiet           Do not log to STDOUT
      -sk SOURCE_KEEP, --source-keep SOURCE_KEEP
                            Expression defining which source snapshots to
                            keep/cleanup. Can be a static number (of backups) or
                            more complex expression like "1d=4/d,1w=daily,2m=none"
                            literally translating to: "1 day from now keep 4
                            backups a day, 1 week from now keep daily backups, 2
                            months from now keep none". Default is 10
      -dk DESTINATION_KEEP, --destination-keep DESTINATION_KEEP
                            Expression defining which destination snapshots to
                            keep/cleanup. Can be a static number (of backups) or
                            more complex expression (see --source-keep arguemnt).
                            Default is 10
      -ss SOURCE_CONTAINER_SUBVOLUME, --source-container-subvolume SOURCE_CONTAINER_SUBVOLUME
                            Override path to source snapshot container subvolume.
                            Both absolute and relative paths are possible. Default
                            is 'sxbackup', relative to source subvolume
      -li LOG_IDENT, --log-ident LOG_IDENT
                            Log ident used for syslog logging, defaults to script
                            name
      --version             show program's version number and exit
