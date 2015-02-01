import logging
import io
import os
import subprocess
from urllib import parse

from btrfs_sxbackup import shell
from btrfs_sxbackup.configs import LocationConfiguration
from btrfs_sxbackup.retention import RetentionExpression
from btrfs_sxbackup.entities import SnapshotName
from btrfs_sxbackup.entities import Subvolume


class Location:
    """ Base class for source/destination location """

    __TEMP_BACKUP_NAME = 'temp'
    __CONFIG_FILENAME = '.btrfs-sxbackup'

    def __init__(self, url: parse.SplitResult, container_subvolume_relpath: str=None):
        """
        c'tor
        :param url: Location URL
        """
        if not url:
            raise ValueError('Location url is mandatory')

        self.__logger = logging.getLogger(self.__class__.__name__)
        self.__url = url
        self.__retention = None
        self.__snapshot_names = []
        self.__container_subvolume_relpath = container_subvolume_relpath
        self.__container_subvolume_path = os.path.join(self.url.path, container_subvolume_relpath) \
            if container_subvolume_relpath else url.path
        # Path of subvolume for current backup run
        # Subvolumes will be renamed from temp to timestamp based name on both side if successful.
        self.__temp_subvolume = os.path.join(self.__container_subvolume_path, self.__TEMP_BACKUP_NAME)
        self.__configuration_filename = os.path.join(self.__container_subvolume_path, self.__CONFIG_FILENAME)

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
    def container_subvolume_relpath(self):
        return self.__container_subvolume_relpath

    @property
    def container_subvolume_path(self):
        return self.__container_subvolume_path

    @property
    def retention(self) -> RetentionExpression:
        return self.__retention

    @retention.setter
    def retention(self, retention: RetentionExpression):
        self.__retention = retention

    @property
    def temp_subvolume_path(self):
        return self.__temp_subvolume

    @property
    def configuration_filename(self):
        return self.__configuration_filename

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
            'if [ -d "%s" ] ; then btrfs sub del "%s"; fi' % (self.temp_subvolume_path, self.temp_subvolume_path)))

    def retrieve_snapshot_names(self):
        """ Determine snapshot names. Snapshot names are sorted in reverse order (newest first).
        stored internally (self.snapshot_names) and also returned. """

        self._log_info('Retrieving snapshot names')
        output = subprocess.check_output(
            self.create_subprocess_args('btrfs sub list -o "%s"' % self.container_subvolume_path))
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
        if self.__retention is not None and len(self.__snapshot_names) > 1:
            (to_remove_by_condition, to_retain) = self.__retention.filter(self.__snapshot_names[1:],
                                                                          lambda sn: sn.timestamp)

            for c in to_remove_by_condition.keys():
                to_remove = to_remove_by_condition[c]

                self._log_info('Removing %d snapshot(s) due to retention [%s]: %s'
                               % (len(to_remove), str(c), list(map(lambda x: str(x), to_remove))))
                cmd = " && ".join(
                    map(lambda x: 'btrfs sub del "%s"' % (os.path.join(self.container_subvolume_path, str(x))),
                        to_remove))

                subprocess.check_output(
                    self.create_subprocess_args(cmd))

    def write_configuration(self, config: LocationConfiguration):
        """ Write configuration file to container subvolume """
        # Configuration to string
        str_file = io.StringIO()
        config.write(str_file)
        config_str = str_file.getvalue()

        # Write config file to location directory
        args = self.create_subprocess_args('cat > "%s"' % self.configuration_filename)
        p = subprocess.Popen(args, stdin=subprocess.PIPE)
        (out, err) = p.communicate(input=bytes(config_str, 'utf-8'))
        retcode = p.wait()
        if retcode:
            raise subprocess.CalledProcessError(returncode=retcode, cmd=args, output=out)

    def read_configuration(self) -> LocationConfiguration:
        """ Read configuration file from container subvolume """
        # Read via cat, ignore errors in case file does not exist
        out = subprocess.check_output(self.create_subprocess_args('cat "%s"' % self.configuration_filename),
                                      stderr=subprocess.STDOUT)

        # Parse config
        return LocationConfiguration.read(out.decode().splitlines())

    def __str__(self):
        return self.__format_log_msg('Url [%s] snapshot container subvolume [%s] retention [%s]'
                                     % (self.__url.geturl(), self.container_subvolume_path, self.__retention))


class SourceLocation(Location):
    """ Source location """

    def __init__(self, url: parse.SplitResult,
                 container_subvolume_relpath: str=None):
        """
        c'tor
        :param url: Location URL
        """
        if not container_subvolume_relpath:
            container_subvolume_relpath = '.sxbackup'

        super().__init__(url, container_subvolume_relpath=container_subvolume_relpath)

    @property
    def name(self):
        return 'Source'

    def prepare_environment(self):
        """ Prepares source environment """

        # Source specific preparation, check and create source snapshot volume if required
        subprocess.check_output(self.create_subprocess_args(
            'if [ ! -d %s ] ; then btrfs sub create "%s"; fi' % (
            self.container_subvolume_path, self.container_subvolume_path)))

        # Generic location preparation
        super().prepare_environment()

    def create_snapshot(self):
        """ Creates a new (temporary) snapshot within container subvolume """
        # Create new temporary snapshot (source)
        self._log_info('Creating snapshot')
        subprocess.check_output(self.create_subprocess_args(
            'btrfs sub snap -r "%s" "%s" && sync' % (self.url.path, self.temp_subvolume_path)))


class DestinationLocation(Location):
    def __init__(self, url: parse.SplitResult):
        """
        c'tor
        :param url: Location URL
        """
        super().__init__(url)

    @property
    def name(self):
        return 'Destination'
