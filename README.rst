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

* bash

* btrfs-progs

The system executing btrfs-backup requires

* python3

Optional
--------
* ssh (for remote push/pull, not required for local operation)
   
  * bash has to be set as the default remote shell for the user running the backup
   
* lzop (for compression support if desired)

* pv (provides progress indication if installed)

* sendmail (for email notifications if desired)

Installation
============
.. code ::

    pip3 install btrfs-sxbackup

Setup
=====
* when using ssh, public/private key authentication should be set up

Known limitations
=================
* the destination filesystem has to be mounted without the subvol option, otherwise an error will occur on btrfs receive prompting you to remount with fs tree

* some commands (like *update*) may not be available for backup jobs created with older versions of btrfs-sxbackup. in this case backup jobs can be recreated using *destroy* and *init*. existing snapshots will be kept as long as *destroy* is **not** invoked with *--purge*.

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

Synopsis and options
====================

.. code ::

    usage: btrfs-sxbackup [-h] [-q] [--version] [-v]
                          {init,destroy,update,run,info,transfer} ...

    positional arguments:
      {init,destroy,update,run,info,transfer}
        init                initialize backup job
        destroy             destroy backup job
        update              update backup job
        run                 run backup job
        info                backup job info
        purge               purge backups according to retention expressions
        transfer            transfer snapshot

    optional arguments:
      -h, --help            show this help message and exit
      -q, --quiet           do not log to stdout
      --version             show program's version number and exit
      -v                    can be specified multiple times to increase verbosity

init
----

.. code ::

    usage: btrfs-sxbackup init [-h] [-sr SOURCE_RETENTION]
                               [-dr DESTINATION_RETENTION] [-c]
                               source-subvolume destination-subvolume

    positional arguments:
      source-subvolume      source subvolume to backup. local path or ssh url
      destination-subvolume
                            destination subvolume receiving backup snapshots.
                            local path or ssh url

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

purge
-----

.. code ::

    usage: btrfs-sxbackup purge [-h] [-sr SOURCE_RETENTION]
                                [-dr DESTINATION_RETENTION]
                                subvolume [subvolume ...]

    positional arguments:
      subvolume             backup job source or destination subvolume. local path
                            or SSH url

    optional arguments:
      -h, --help            show this help message and exit
      -sr SOURCE_RETENTION, --source-retention SOURCE_RETENTION
                            Optionally override expression defining which source
                            snapshots to retain/cleanup. can be a static number
                            (of backups) or more complex expression like "1d:4/d,
                            1w:daily, 2m:none" literally translating to: "1 day
                            from now keep 4 backups a day, 1 week from now keep
                            daily backups, 2 months from now keep none"
      -dr DESTINATION_RETENTION, --destination-retention DESTINATION_RETENTION
                            Optionally override expression defining which
                            destination snapshots to retain/cleanup. can be a
                            static number (of backups) or more complex expression
                            (see --source-retention argument)

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

transfer
--------

.. code ::

    usage: btrfs-sxbackup transfer [-h] [-c]
                                   source-subvolume destination-subvolume

    positional arguments:
      source-subvolume      source subvolume to transfer. local path or ssh url
      destination-subvolume
                            destination subvolume. local path or ssh url

    optional arguments:
      -h, --help            show this help message and exit
      -c, --compress        enables compression during transmission. Requires lzop
                            to be installed on both source and destination

Changelog
=========

0.6.6
-----
* ADDED support for retain timespan multiplier (eg. '1/4m' -> keep 1 in 4 months) and yearly timespan literal ('y'), resolving #28

0.6.5
-----
* RESOLVED #18, improved error output

0.6.4
-----
* ADDED support for falling back to transferring full snapshot if latest snapshot (timestamp) does not match on source/destination

0.6.3
-----
* FIXED exception during exception handling in main method

0.6.2
-----
* FIXED pip installation may fail with bdist/wheel

0.6.1
-----
* README update

0.6.0
-----
* ADDED support for purge command

0.5.9
-----
* ADDED license headers to all source files, no functional changes

0.5.8
-----
* FIXED job won't run due to inconsistent  datetime comparison (offset-naive/aware)

0.5.7
-----
* ADDED local timestamps to info, resolving #14

0.5.6
-----
* Fixed #13 "update" command always activates compression, regardless of -c

0.5.5
-----
* Fixed retention breakage which could occur when first/earliest expression kept 1 backup per interval

0.5.4
-----
* Python 3.3 compatibility fixes

* Added proper support for relative paths passed to init

0.5.0
-----
* New command line interface

* Source container subvolume path is now **.sxbackup** relative to the source subvolume and cannot be customized anylonger

* Backups created with older versions are still supported.
  If you customized the source container subvolume, this will still work, but it's recommended to rename it
  to the new default (**.sxbackup**) and update source and destination configuration files (.btrfs-sxbackup) accordingly

