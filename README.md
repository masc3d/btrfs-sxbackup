btrfs-sxbackup
==============

Btrfs snapshot backup utility with push/pull support via SSH

```
btrfs-sxbackup.py --help
btrfs-sxbackup v0.3.0 by masc
usage: btrfs-sxbackup.py [-h] [-sm SOURCE_MAX_SNAPSHOTS]
                         [-dm DESTINATION_MAX_SNAPSHOTS]
                         [-ss SOURCE_CONTAINER_SUBVOLUME] [-c]
                         source_subvolume destination_container_subvolume

positional arguments:
  source_subvolume      Source subvolume to backup. Local path or SSH url.
  destination_container_subvolume
                        Destination subvolume receiving snapshots. Local path
                        or SSH url.

optional arguments:
  -h, --help            show this help message and exit
  -sm SOURCE_MAX_SNAPSHOTS, --source-max-snapshots SOURCE_MAX_SNAPSHOTS
                        Maximum number of source snapshots to keep (defaults
                        to 10).
  -dm DESTINATION_MAX_SNAPSHOTS, --destination-max-snapshots DESTINATION_MAX_SNAPSHOTS
                        Maximum number of destination snapshots to keep
                        (defaults to 10).
  -ss SOURCE_CONTAINER_SUBVOLUME, --source-container-subvolume SOURCE_CONTAINER_SUBVOLUME
                        Override path to source snapshot container subvolume.
                        Both absolute and relative paths are possible.
                        (defaults to 'sxbackup', relative to source subvolume)
  -c, --compress        Enables compression, requires lzop to be installed on
                        both source and destination
```

## Dependencies ##
#### Required ####
The following packages have to be available on both source and destination
* python3
* btrfs-progs

#### Optional ####
* ssh (for remote push/pull, not required for local operation)
* lzop (for compression support if desired)
* pv (provides progress indication if installed)

## Setup ##
* when using ssh, public/private key authentication should be set up

## Examples ##
```
btrfs-sxbackup.py ssh://root@myhost.org:/ /backup/myhost
```
Pulls snapshot backups of ___/___ on remote host ___myhost.org___ to local subvolume ___/backup/myhost___
```
btrfs-sxbackup.py / ssh://root@mybackupserver.org:/backup/myhost
```
Pushes snapshot backups of local subvolume ___/___ to remote subvolume ___/backup/myhost___ on host ___mybackupserver.org___
