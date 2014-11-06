btrfs-sxbackup
==============

Btrfs snapshot backup utility with push/pull support via SSH

```
btrfs-sxbackup.py --help

btrfs-sxbackup.py v0.2.5 by masc
usage: btrfs-sxbackup.py [-h] [-sm SOURCE_MAX_SNAPSHOTS]
                         [-dm DESTINATION_MAX_SNAPSHOTS]
                         [-ss SOURCE_SNAPSHOT_SUBVOLUME]
                         source_subvolume destination_snapshot_subvolume

positional arguments:
  source_subvolume      Source subvolume to snapshot/backup. Local path or SSH
                        url.
  destination_snapshot_subvolume
                        Destination subvolume storing received snapshots.
                        Local path or SSH url.

optional arguments:
  -h, --help            show this help message and exit
  -sm SOURCE_MAX_SNAPSHOTS, --source-max-snapshots SOURCE_MAX_SNAPSHOTS
                        Maximum number of source snapshots to keep (defaults
                        to 10).
  -dm DESTINATION_MAX_SNAPSHOTS, --destination-max-snapshots DESTINATION_MAX_SNAPSHOTS
                        Maximum number of destination snapshots to keep
                        (defaults to 10).
  -ss SOURCE_SNAPSHOT_SUBVOLUME, --source-snapshot-subvolume SOURCE_SNAPSHOT_SUBVOLUME
                        Override path to source snapshot container subvolume.
                        Both absolute and relative paths are possible.
                        Relative paths relate ot source subvolume. (defaults
                        to sxbackup relative to source subvolume)
```

## Dependencies ##
* python3
* btrfs-progs
* bash
* pv (for progress indication)
* ssh (when pushing/pulling, not required for local operation)

## Setup ##
* when using ssh, public/private key authentication should be setup

## Examples ##
```
btrfs-sxbackup.py ssh://root@myhost/ /backup/myhost
```
Pulls snapshot backups of / on remote host 'myhost' to local subvolume /backup/myhost
```
btrfs-sxbackup.py / ssh://root@mybackupserver/backup/myhost
```
Pushes snapshot backups of local subvolume / to remote subvolume /backup/myhost on host 'mybackupserver' 
