Changelog
=========

0.6.10
------
* FIXED username should be checked for `None` when building ssh url

0.6.9
-----
* RESOLVED #32 regression, always transferring full snapshots

0.6.8
-----
* RESOLVED #31 Error when destination has no snapshots

0.6.7
-----
* FIXED #30: full snapshot warning breaks local jobs (having no destination)
* RESOLVED #29: can't destroy when destination unavailable

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

