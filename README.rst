btrfs-sxbackup
**************

Btrfs snapshot backup utility

* Push/pull support via SSH
* Retention
* Email notifications
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
* sendmail (for email notifications if desired)

Installation
============
.. code ::

    pip install btrfs-sxbackup

Setup
=====
* When using ssh, public/private key authentication should be set up

Usage examples
==============

Initialize
----------

Initialize a backup job pulling snapshots of subvolume **/** on remote host **myhost.org** to local subvolume **/backup/myhost**

.. code ::

    btrfs-sxbackup init ssh://root@myhost.org:/ /backup/myhost

Initialize a backup job pushing snapshots of local subvolume **/** to remote subvolume **/backup/myhost** on host **mybackupserver.org**

.. code ::

    btrfs-sxbackup init / ssh://root@mybackupserver.org:/backup/myhost

Run
---

Run a backup job

.. code ::

    btrfs-sxbackup run /backup/myhost

Cron
----

Cronjob performing a pull backup job

.. code ::

    # /etc/cron.d/btrfs-sxbackup
    PATH="/usr/sbin:/usr/bin:/sbin:/bin"
    30 2    * * *     root     btrfs-sxbackup run /backup/myhost

Changelog
=========

0.5.0
-----
* New command line interface
* Source container subvolume path is now **.sxbackup** relative to the source subvolume and cannot be customized anylonger
* Backups created with older versions are still supported. 
  If you customized the source container subvolume, this will still work, but it's recommended to rename it 
  to the new default (**.sxbackup**) and destroy and reinitialize the backup job subsequently.
  Recreating a backup job will not remove any snapshots (unless --purge is used)

Synopsis and options
====================

.. code ::

    usage: btrfs-sxbackup [-h] [-q] [--trace] [--version]
                          {init,destroy,update,run,info} ...

    positional arguments:
      {init,destroy,update,run,info}
        init                initialize backup job
        destroy             destroy backup job
        update              update backup job
        run                 run backup job
        info                backup job info

    optional arguments:
      -h, --help            show this help message and exit
      -q, --quiet           do not log to stdout
      --trace               enables trace output
      --version             show program's version number and exit

init
----

.. code ::

    usage: btrfs-sxbackup init [-h] [-sr SOURCE_RETENTION]
                               [-dr DESTINATION_RETENTION] [-c]
                               source-subvolume destination-subvolume

    positional arguments:
      source-subvolume      source subvolume to backup. local path or SSH url
      destination-subvolume
                            destination subvolume receiving backup snapshots.
                            local path or SSH url

    optional arguments:
      -h, --help            show this help message and exit
      -sr SOURCE_RETENTION, --source-retention SOURCE_RETENTION
                            expression defining which source snapshots to
                            retain/cleanup. can be a static number (of backups) or
                            more complex expression like "1d:4/d, 1w:daily,
                            2m:none" literally translating to: "1 day from now
                            keep 4 backups a day, 1 week from now keep daily
                            backups, 2 months from now keep none"
      -dr DESTINATION_RETENTION, --destination-retention DESTINATION_RETENTION
                            expression defining which destination snapshots to
                            retain/cleanup. can be a static number (of backups) or
                            more complex expression (see --source-retention
                            argument)
      -c, --compress        enables compression during transmission. Requires lzop
                            to be installed on both source and destination

run
---

.. code ::

    usage: btrfs-sxbackup run [-h] [-m [MAIL]] [-li LOG_IDENT]
                              subvolume [subvolume ...]

    positional arguments:
      subvolume             backup job source or destination subvolume. local path
                            or SSH url

    optional arguments:
      -h, --help            show this help message and exit
      -m [MAIL], --mail [MAIL]
                            enables email notifications. If an email address is
                            given, it overrides the default email-recipient
                            setting in /etc/btrfs-sxbackup.conf
      -li LOG_IDENT, --log-ident LOG_IDENT
                            log ident used for syslog logging, defaults to script
                            name

update
------

.. code ::

    usage: btrfs-sxbackup update [-h] [-sr SOURCE_RETENTION]
                                 [-dr DESTINATION_RETENTION] [-c]
                                 subvolume [subvolume ...]

    positional arguments:
      subvolume             backup job source or destination subvolume. local path
                            or SSH url

    optional arguments:
      -h, --help            show this help message and exit
      -sr SOURCE_RETENTION, --source-retention SOURCE_RETENTION
                            expression defining which source snapshots to
                            retain/cleanup. can be a static number (of backups) or
                            more complex expression like "1d:4/d, 1w:daily,
                            2m:none" literally translating to: "1 day from now
                            keep 4 backups a day, 1 week from now keep daily
                            backups, 2 months from now keep none"
      -dr DESTINATION_RETENTION, --destination-retention DESTINATION_RETENTION
                            expression defining which destination snapshots to
                            retain/cleanup. can be a static number (of backups) or
                            more complex expression (see --source-retention
                            argument)
      -c, --compress        enables compression during transmission. Requires lzop
                            to be installed on both source and destination

info
----

.. code ::

    usage: btrfs-sxbackup info [-h] subvolume [subvolume ...]

    positional arguments:
      subvolume   backup job source or destination subvolume. local path or SSH
                  url

    optional arguments:
      -h, --help  show this help message and exit

destroy
-------

.. code ::

    usage: btrfs-sxbackup destroy [-h] [--purge] subvolume [subvolume ...]

    positional arguments:
      subvolume   backup job source or destination subvolume. local path or SSH
                  url

    optional arguments:
      -h, --help  show this help message and exit
      --purge     removes all backup snapshots from source and destination
