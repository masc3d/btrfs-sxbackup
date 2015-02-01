import logging
import io
import os
import subprocess

from btrfs_sxbackup import shell
from btrfs_sxbackup.configs import LocationConfiguration
from btrfs_sxbackup.retention import KeepExpression
from btrfs_sxbackup.entities import SnapshotName
from btrfs_sxbackup.entities import Subvolume


class Location:
    """ Base class for source/destination location """

    __TEMP_BACKUP_NAME = 'temp'
    __CONFIG_FILENAME = '.btrfs-sxbackup'

    def __init__(self, url, keep=None):
        """
        c'tor
        :param url: Location URL
        :param keep: Keep expression instance
        """

        if not keep:
            keep = KeepExpression('1w:2/d, 2w:daily, 1m:weekly, 2m:none')

        self.__logger = logging.getLogger(self.__class__.__name__)
        self.__url = url
        self.__keep = keep
        self.__snapshot_names = []
        self.__configuration_filename = os.path.join(self.container_subvolume, self.__CONFIG_FILENAME)

        # Path of subvolume for current backup run
        # Subvolumes will be renamed from temp to timestamp based name on both side if successful.
        self.__temp_subvolume = os.path.join(self.container_subvolume, self.__TEMP_BACKUP_NAME)

    def __format_log_msg(self, msg) -> str:
        return '%s :: %s' % (self.name, msg)

    def _log_info(self, msg):
        self.__logger.info(self.__format_log_msg(msg))

    def _log_debug(self, msg):
        self.__logger.debug(self.__format_log_msg(msg))

    @property
    def name(self) -> str:
        """
        Descriptive (short) name of this location.
        To be overridden in derived classes
        """
        return None

    @property
    def snapshot_names(self) -> list:
        """
        Most recently retrieved snapshot names
        """
        return self.__snapshot_names

    @property
    def url(self):
        return self.__url

    @property
    def container_subvolume(self):
        return self.__url.path

    @property
    def keep(self) -> KeepExpression:
        return self.__keep

    @keep.setter
    def keep(self, keep: KeepExpression):
        self.__keep = keep

    @property
    def temp_subvolume(self):
        return self.__temp_subvolume

    def is_remote(self):
        return self.__url.hostname is not None

    def create_subprocess_args(self, cmd):
        """
        Create subprocess arguments for shell command/args to be executed in this location.
        Internally Wraps command into ssh call if url host name is not None
        :param cmd: Shell command
        :return: Subprocess arguments
        """
        subprocess_args = shell.create_subprocess_args(cmd, self.url)
        self._log_debug(subprocess_args)
        return subprocess_args

    def prepare_environment(self):
        """ Prepare location environment """

        # Check and remove temporary snapshot volume (possible leftover of previously interrupted backup)
        subprocess.check_output(self.create_subprocess_args(
            'if [ -d "%s" ] ; then btrfs sub del "%s"; fi' % (self.__temp_subvolume, self.__temp_subvolume)))

    def retrieve_snapshot_names(self):
        """ Determine snapshot names. Snapshot names are sorted in reverse order (newest first).
        stored internally (self.snapshot_names) and also returned. """

        self._log_info('Retrieving snapshot names')
        output = subprocess.check_output(
            self.create_subprocess_args('btrfs sub list -o "%s"' % self.container_subvolume))
        # output is delivered as a byte sequence, decode to unicode string and split lines
        lines = output.decode().splitlines()

        subvolumes = list(map(lambda x: Subvolume.parse(x), lines))

        # verify snapshot subvolume path consistency
        if len(subvolumes) > 0:
            subvol_path = os.path.dirname(subvolumes[0].path)
            subvol_inconsistent_path = \
                next((s.path for s in subvolumes if os.path.dirname(s.path) != subvol_path), None)

            if subvol_inconsistent_path:
                raise Exception('Inconsistent path detected at %s [%s != %s], indicating a nested'
                                ' folder/subvolume structure within a container subvolume.'
                                ' Each backup job must have a dedicated source/destination container subvolume'
                                % (self.__url.path, subvol_path, subvol_inconsistent_path))

        # sort and return
        snapshot_names = map(lambda l: SnapshotName.parse(os.path.basename(l.path)), subvolumes)
        self.__snapshot_names = sorted(snapshot_names, key=lambda sn: sn.timestamp, reverse=True)
        return self.__snapshot_names

    def cleanup_snapshots(self):
        """ Clean out excess backups/snapshots. The newst one (index 0) will always be kept. """
        if self.__keep is not None and len(self.__snapshot_names) > 1:
            (to_remove_by_condition, to_keep) = self.__keep.filter(self.__snapshot_names[1:],
                                                                   lambda sn: sn.timestamp)

            for c in to_remove_by_condition.keys():
                to_remove = to_remove_by_condition[c]

                self._log_info('Removing %d snapshot(s) due to condition [%s]: %s'
                               % (len(to_remove), str(c), list(map(lambda x: str(x), to_remove))))
                cmd = " && ".join(
                    map(lambda x: 'btrfs sub del "%s"' % (os.path.join(self.container_subvolume, str(x))), to_remove))

                subprocess.check_output(
                    self.create_subprocess_args(cmd))

    def write_configuration(self, config: LocationConfiguration):
        """ Write configuration file to container subvolume """
        # Configuration to string
        str_file = io.StringIO()
        config.write(str_file)
        config_str = str_file.getvalue()
        # Write config file to location directory
        p = subprocess.Popen(self.create_subprocess_args('cat > "%s"' % self.__configuration_filename),
                             stdin=subprocess.PIPE)
        p.communicate(input=bytes(config_str, 'utf-8'))
        p.wait()

    def read_configuration(self) -> LocationConfiguration:
        """ Read configuration file from container subvolume """
        # Read via cat, ignore errors in case file does not exist
        out = subprocess.check_output(self.create_subprocess_args('cat "%s"' % self.__configuration_filename),
                                      stderr=subprocess.STDOUT)

        # Parse config
        return LocationConfiguration.read(out.decode().splitlines())

    def __str__(self):
        return self.__format_log_msg('Url [%s] snapshot container subvolume [%s] keep [%s]'
                                     % (self.__url.geturl(), self.container_subvolume, self.__keep))


class SourceLocation(Location):
    """ Source location """

    @property
    def name(self):
        return 'Source'

    @property
    def container_subvolume(self):
        return os.path.join(self.url.path, '.sxbackup')

    def prepare_environment(self):
        """ Prepares source environment """

        # Source specific preparation, check and create source snapshot volume if required
        subprocess.check_output(self.create_subprocess_args(
            'if [ ! -d %s ] ; then btrfs sub create "%s"; fi' % (self.container_subvolume, self.container_subvolume)))

        # Generic location preparation
        super().prepare_environment()

    def create_snapshot(self):
        """ Creates a new (temporary) snapshot within container subvolume """
        # Create new temporary snapshot (source)
        self._log_info('Creating snapshot')
        subprocess.check_output(self.create_subprocess_args(
            'btrfs sub snap -r "%s" "%s" && sync' % (self.url.path, self.temp_subvolume)))


class DestinationLocation(Location):
    @property
    def name(self):
        return 'Destination'

    @property
    def container_subvolume(self):
        return self.url.path
