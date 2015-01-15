import io
import os
import logging
import logging.handlers
import subprocess
import time

from configparser import ConfigParser
from btrfs_sxbackup.SnapshotName import SnapshotName
from btrfs_sxbackup.KeepExpression import KeepExpression
from btrfs_sxbackup.Subvolume import Subvolume


class Command:
    @staticmethod
    def exists(command, location=None):
        """
        Check if shell command exists
        :param command: Command to verify
        :param location: Location to check in or None for local system
        :return: True if location exists, otherwise False
        """
        type_cmd = ['type ' + command]
        if location is not None:
            type_cmd = location.create_subprocess_args(type_cmd)

        type_prc = subprocess.Popen(type_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
        return type_prc.wait() == 0


class Backup:
    """ Backup """

    class Error(Exception):
        pass

    class Location:
        """ Backup location """

        __TEMP_BACKUP_NAME = 'temp'
        __CONFIG_FILENAME = '.btrfs-sxbackup'

        class Configuration:
            """ btrfs-sxbackup configuration file """

            __KEY_SOURCE = 'source'
            __KEY_SOURCE_CONTAINER = 'source-container'
            __KEY_DESTINATION = 'destination'
            __KEY_KEEP = 'keep'

            def __init__(self, location=None):
                """
                c'tor
                :param location: Location this configuration refers to/resides or none for global configuration file
                """

                self.__location = location
                self.source = None
                self.source_container = None
                self.destination = None
                self.keep = KeepExpression('1w:2/d, 2w:daily, 1m:weekly, 2m:none')

            @staticmethod
            def __section_name_by_location(location):
                """
                Delivers the default configuration section name by location instance/type
                :param location: Location instance or None
                :return: Section name string
                """
                if isinstance(location, Backup.SourceLocation):
                    return 'Source'
                else:
                    if isinstance(location, Backup.DestinationLocation):
                        return 'Destination'
                    else:
                        raise ValueError('Configuration does not support location instance type [%s]' % location)

            def read(self, fileobject):
                parser = ConfigParser()
                parser.read_file(fileobject)

                section_name = self.__section_name_by_location(self.__location)
                self.source = parser.get(section_name, self.__KEY_SOURCE, fallback=None)
                self.source_container = parser.get(section_name, self.__KEY_SOURCE_CONTAINER, fallback=None)
                self.destination = parser.get(section_name, self.__KEY_DESTINATION, fallback=None)
                self.keep = parser.get(section_name, self.__KEY_KEEP, fallback=self.keep)

            def write(self, fileobject):
                parser = ConfigParser()

                section_name = self.__section_name_by_location(self.__location)
                parser.add_section(section_name)
                if self.source is not None:
                    parser.set(section_name, self.__KEY_SOURCE, self.source)
                if self.source_container is not None:
                    parser.set(section_name, self.__KEY_SOURCE_CONTAINER, self.source_container)
                if self.destination is not None:
                    parser.set(section_name, self.__KEY_DESTINATION, self.destination)
                if self.keep is not None:
                    parser.set(section_name, self.__KEY_KEEP, self.keep)
                parser.write(fileobject)

        def __init__(self, url, container_subvolume, keep):
            """
            c'tor
            :param url: Location URL
            :param container_subvolume: Subvolume name
            :param keep: Keep expression instance
            """
            self.__logger = logging.getLogger(self.__class__.__name__)
            self.__url = url
            self.__container_subvolume = os.path.join(url.path, container_subvolume)
            self.__keep = keep
            self.__snapshot_names = []
            self.__configuration_filename = os.path.join(self.__container_subvolume, self.__CONFIG_FILENAME)

            # Path of subvolume for current backup run
            # Subvolumes will be renamed from temp to timestamp based name on both side if successful.
            self.__temp_subvolume = os.path.join(self.__container_subvolume, self.__TEMP_BACKUP_NAME)

            # Override configuration params
            self.__configuration = Backup.Location.Configuration(self)

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
        def configuration(self):
            return self.__configuration

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
            return self.__container_subvolume

        @property
        def keep(self):
            return self.__keep

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
            # in case cmd is a regular value, convert to list
            cmd = cmd if cmd is list else [cmd]
            # wrap into bash or ssh command respectively
            # depending if command is executed locally (host==None) or remotely
            subprocess_args = ['bash', '-c'] + cmd if self.__url.hostname is None else \
                ['ssh', '-o', 'ServerAliveInterval=5', '-o', 'ServerAliveCountMax=3', '%s@%s'
                 % (self.__url.username, self.__url.hostname)] + cmd
            self._log_debug(subprocess_args)
            return subprocess_args

        def create_cleanup_bash_command(self, snapshot_names):
            """ Creates bash comand string to remove multiple snapshots within a btrfs subvolume """

            return " && ".join(
                map(lambda x: 'btrfs sub del %s' % (os.path.join(self.__container_subvolume, str(x))), snapshot_names))

        def prepare_environment(self):
            """ Prepare location environment """

            # Check and remove temporary snapshot volume (possible leftover of previously interrupted backup)
            subprocess.check_output(self.create_subprocess_args(
                'if [ -d %s ] ; then btrfs sub del %s; fi' % (self.__temp_subvolume, self.__temp_subvolume)))

        def retrieve_snapshot_names(self):
            """ Determine snapshot names. Snapshot names are sorted in reverse order (newest first).
            stored internally (self.snapshot_names) and also returned. """

            self._log_info('Retrieving snapshot names')
            output = subprocess.check_output(
                self.create_subprocess_args('btrfs sub list -o %s' % self.__container_subvolume))
            # output is delivered as a byte sequence, decode to unicode string and split lines
            lines = output.decode().splitlines()

            subvolumes = list(map(lambda x: Subvolume.parse(x), lines))

            # verify snapshot subvolume path consistency
            if len(subvolumes) > 0:
                first_path = os.path.dirname(subvolumes[0].path)
                first_inconsistent_path = \
                    next((s.path for s in subvolumes if os.path.dirname(s.path) != first_path), None)

                if first_inconsistent_path:
                    raise Exception('Inconsistent path detected at %s [%s != %s], indicating a nested'
                                    ' folder/subvolume structure within a container subvolume.'
                                    ' Each backup job must have a dedicated source/destination container subvolume'
                                    % (self.__url.path, first_path, first_inconsistent_path))

            # sort and return
            snapshot_names = map(lambda l: SnapshotName.parse(os.path.basename(l.path)), subvolumes)
            self.__snapshot_names = sorted(snapshot_names, key=lambda sn: sn.timestamp, reverse=True)
            return self.__snapshot_names

        def cleanup_snapshots(self):
            """ Clean out excess backups/snapshots """
            if self.__keep is not None:
                (to_remove_by_condition, to_keep) = self.__keep.filter(self.__snapshot_names, lambda sn: sn.timestamp)

                for c in to_remove_by_condition.keys():
                    to_remove = to_remove_by_condition[c]

                    self._log_info('Removing %d snapshot(s) due to condition [%s]: %s'
                                   % (len(to_remove), str(c), list(map(lambda x: str(x), to_remove))))
                    subprocess.check_output(
                        self.create_subprocess_args(self.create_cleanup_bash_command(to_remove)))

        def write_configuration(self):
            """ Write configuration file to container subvolume """
            # Configuration to string
            str_file = io.StringIO()
            self.__configuration.write(str_file)
            config_str = str_file.getvalue()
            # Write config file to location directory
            p = subprocess.Popen(self.create_subprocess_args('cat > %s' % self.__configuration_filename),
                                 stdin=subprocess.PIPE)
            p.communicate(input=bytes(config_str, 'utf-8'))

        def read_configuration(self):
            """ Read configuration file from container subvolume """
            # Read via cat, ignore errors in case file does not exist
            p = subprocess.Popen(self.create_subprocess_args('cat %s' % self.__configuration_filename),
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            (out, err) = p.communicate()
            # Parse config
            self.__configuration.read(out.decode().splitlines())

        def __str__(self):
            return self.__format_log_msg('Url [%s] snapshot container subvolume [%s] keep [%s]'
                                         % (self.__url.geturl(), self.__container_subvolume, self.__keep))

    class SourceLocation(Location):
        """ Source location """

        @property
        def name(self):
            return 'Source'

        def prepare_environment(self):
            """ Prepares source environment """
            # Source specific preparation, check and create source snapshot volume if required
            subprocess.check_output(self.create_subprocess_args(
                'if [ ! -d %s ] ; then btrfs sub create %s; fi' % (self.container_subvolume, self.container_subvolume)))

            # Generic location preparation
            super().prepare_environment()

        def create_snapshot(self):
            """ Creates a new (temporary) snapshot within container subvolume """
            # Create new temporary snapshot (source)
            self._log_info('Creating snapshot')
            subprocess.check_output(self.create_subprocess_args(
                'btrfs sub snap -r %s %s && sync' % (self.url.path, self.temp_subvolume)))

    class DestinationLocation(Location):
        @property
        def name(self):
            return 'Destination'

    def __init__(self, config, source_url, source_container_subvolume, source_keep, dest_url, dest_keep, compress):
        """
        c'tor
        :param config: Global configuration instance
        :param source_url: Source URL
        :param source_container_subvolume: Source container subvolume name
        :param source_keep: Source keep expression instance
        :param dest_url: Destination URL
        :param dest_keep: Destination keep expression instance
        :return:
        """
        self.__logger = logging.getLogger(self.__class__.__name__)

        self.__config = config
        self.__source = Backup.SourceLocation(source_url, source_container_subvolume, source_keep)
        self.__dest = Backup.DestinationLocation(dest_url, "", dest_keep)

        self.__compress = compress

    def run(self):
        """ Performs backup run """

        self.__logger.info(self.__source)
        self.__logger.info(self.__dest)

        starting_time = time.monotonic()

        # Prepare environments
        self.__logger.info('Preparing environment')
        self.__source.prepare_environment()
        self.__dest.prepare_environment()

        # Read location configurations
        self.__source.read_configuration()
        self.__dest.read_configuration()

        # Update configuration parameters with current settings for this backup (both ways)
        both_remote_or_local = not (self.__source.is_remote() ^ self.__dest.is_remote())

        # Update location configuration (in a meaningful way)
        self.__source.configuration.source = None
        self.__source.configuration.source_container = None
        self.__source.configuration.destination = None
        self.__source.configuration.keep = None
        self.__dest.configuration.source = None
        self.__dest.configuration.source_container = None
        self.__dest.configuration.destination = None
        self.__dest.configuration.keep = None

        if both_remote_or_local:
            self.__source.configuration.source = self.__source.url.geturl()
            self.__source.configuration.source_container = self.__source.container_subvolume
            self.__dest.configuration.destination = self.__dest.url.geturl()

        if both_remote_or_local or self.__dest.is_remote():
            self.__source.configuration.destination = self.__dest.url.geturl()

        if self.__source.keep:
            self.__source.configuration.keep = self.__source.keep.expression_text

        if both_remote_or_local or self.__source.is_remote():
            self.__dest.configuration.source = self.__source.url.geturl()
            self.__dest.configuration.source_container = self.__source.container_subvolume

        if self.__dest.keep:
            self.__dest.configuration.keep = self.__dest.keep.expression_text

        # Retrieve snapshot names of both source and destination 
        self.__source.retrieve_snapshot_names()
        self.__dest.retrieve_snapshot_names()

        new_snapshot_name = SnapshotName()
        if len(self.__source.snapshot_names) > 0 \
                and new_snapshot_name.timestamp <= self.__source.snapshot_names[0].timestamp:
            raise Backup.Error('Current snapshot name [%s] would be older than newest existing snapshot [%s] \
                                 which may indicate a system time problem'
                               % (new_snapshot_name, self.__source.snapshot_names[0]))

        # Create source snapshot
        self.__source.create_snapshot()

        # Transfer temporary snapshot
        self.__logger.info('Transferring snapshot')
        # btrfs send command/subprocess
        if len(self.__source.snapshot_names) == 0:
            send_command_str = 'btrfs send %s' % self.__source.temp_subvolume
        else:
            send_command_str = 'btrfs send -p %s %s' % (
                os.path.join(self.__source.container_subvolume, str(self.__source.snapshot_names[0])),
                self.__source.temp_subvolume)

        if self.__compress:
            send_command_str += ' | lzop -1'

        send_command = self.__source.create_subprocess_args(send_command_str)
        send_process = subprocess.Popen(send_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        # pv command/subprocess for progress indication
        pv_process = None
        if Command.exists('pv'):
            pv_process = subprocess.Popen(['pv'], stdin=send_process.stdout, stdout=subprocess.PIPE)

        # btrfs receive command/subprocess
        receive_command_str = 'btrfs receive %s' % self.__dest.url.path
        if self.__compress:
            receive_command_str = 'lzop -d | ' + receive_command_str

        receive_command = self.__dest.create_subprocess_args(receive_command_str)
        receive_process = subprocess.Popen(receive_command,
                                           stdin=pv_process.stdout if pv_process is not None else send_process.stdout,
                                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        receive_returncode = None
        send_returncode = None
        while receive_returncode is None or send_returncode is None:
            receive_returncode = receive_process.poll()
            send_returncode = send_process.poll()

            if receive_returncode is not None and receive_returncode != 0:
                try:
                    send_process.kill()
                except ProcessLookupError:
                    pass
                break

            if send_returncode is not None and send_returncode != 0:
                try:
                    receive_process.kill()
                except ProcessLookupError:
                    pass
                break

            time.sleep(2)

        # wait for commands to complete
        send_returncode = send_process.wait()
        receive_returncode = receive_process.wait()

        if send_returncode != 0:
            raise subprocess.CalledProcessError(send_returncode, send_command, None)
        if receive_returncode != 0:
            raise subprocess.CalledProcessError(receive_returncode, receive_command, None)

        # After successful transmission, rename source and destinationside
        # snapshot subvolumes (from pending to timestamp-based name)
        subprocess.check_output(self.__source.create_subprocess_args(
            'mv %s %s' % (
                self.__source.temp_subvolume, os.path.join(self.__source.container_subvolume, str(new_snapshot_name)))))
        subprocess.check_output(self.__dest.create_subprocess_args(
            'mv %s %s' % (self.__dest.temp_subvolume, os.path.join(self.__dest.url.path, str(new_snapshot_name)))))

        # Update snapshot name lists
        self.__source.snapshot_names.insert(0, new_snapshot_name)
        self.__dest.snapshot_names.insert(0, new_snapshot_name)

        # Clean out excess backups/snapshots
        self.__source.cleanup_snapshots()
        self.__dest.cleanup_snapshots()

        self.__source.write_configuration()
        self.__dest.write_configuration()

        self.__logger.info('Backup %s created successfully in %s'
                           % (new_snapshot_name,
                              time.strftime("%H:%M:%S", time.gmtime(time.monotonic() - starting_time))))

    def __str__(self):
        return 'Source %s \nDestination %s' % \
               (self.__source, self.__dest)
