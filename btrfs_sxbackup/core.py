import collections
import logging
import subprocess
import time
import uuid
import io
import os
import distutils.util
from configparser import ConfigParser
from uuid import UUID
from urllib import parse

from btrfs_sxbackup.entities import SnapshotName
from btrfs_sxbackup.retention import RetentionExpression
from btrfs_sxbackup import shell
from btrfs_sxbackup.entities import Subvolume


_logger = logging.getLogger(__name__)
_DEFAULT_RETENTION_SOURCE = RetentionExpression('3')
_DEFAULT_RETENTION_DESTINATION = RetentionExpression('2d: 1/d, 2w:3/w, 1m:1/w, 2m:none')
_DEFAULT_CONTAINER_RELPATH = '.sxbackup'


class Error(Exception):
    pass


class Configuration:
    """ btrfs-sxbackup global configuration file """

    __instance = None

    __CONFIG_FILENAME = '/etc/btrfs-sxbackup.conf'

    __SECTION_NAME = 'Default'
    __KEY_SOURCE_RETENTION = 'source-retention'
    __KEY_DEST_RETENTION = 'destination-retention'
    __KEY_LOG_IDENT = 'log-ident'
    __key_EMAIL_RECIPIENT = 'email-recipient'

    def __init__(self):
        self.__source_retention = None
        self.__destination_retention = None
        self.__log_ident = None
        self.__email_recipient = None

    @staticmethod
    def instance():
        """
        :return: Singleton instance
        :rtype: Configuration
        """
        if not Configuration.__instance:
            Configuration.__instance = Configuration()
        return Configuration.__instance

    @property
    def source_retention(self):
        return self.__source_retention

    @property
    def destination_retention(self):
        return self.__destination_retention

    @property
    def log_ident(self):
        return self.__log_ident

    @property
    def email_recipient(self):
        return self.__email_recipient

    def read(self):
        cparser = ConfigParser()

        if os.path.exists(self.__CONFIG_FILENAME):
            with open(self.__CONFIG_FILENAME, 'r') as file:
                cparser.read_file(file)

            source_retention_str = cparser.get(self.__SECTION_NAME, self.__KEY_SOURCE_RETENTION, fallback=None)
            dest_retention_str = cparser.get(self.__SECTION_NAME, self.__KEY_DEST_RETENTION, fallback=None)
            self.__source_retention = RetentionExpression(source_retention_str) if source_retention_str else None
            self.__destination_retention = RetentionExpression(dest_retention_str) if dest_retention_str else None
            self.__log_ident = cparser.get(self.__SECTION_NAME, self.__KEY_LOG_IDENT, fallback=None)
            self.__email_recipient = cparser.get(self.__SECTION_NAME, self.__key_EMAIL_RECIPIENT, fallback=None)


class Location:
    """
    Location
    """

    def __init__(self, url: parse.SplitResult):
        if not url:
            raise ValueError('location url is mandatory')

        self.__logger = logging.getLogger(self.__class__.__name__)
        self.__url = None

        self.url = url

    @property
    def url(self) -> parse.SplitResult:
        return self.__url

    @url.setter
    def url(self, value: parse.SplitResult):
        final_path = value.path
        if not value.hostname:
            final_path = os.path.abspath(final_path)

        if not final_path.endswith(os.path.sep):
            final_path += os.path.sep

        if final_path != value.path:
            value = parse.SplitResult(value.scheme,
                                      value.netloc,
                                      final_path,
                                      value.query, None)
        self.__url = value

    def _format_log_msg(self, msg) -> str:
        name = self.url.geturl()
        return '%s :: %s' % (name.lower(), msg) if name else msg

    def _log_info(self, msg):
        self.__logger.info(self._format_log_msg(msg))

    def _log_debug(self, msg):
        self.__logger.debug(self._format_log_msg(msg))

    def is_remote(self) -> bool:
        return self.url.hostname is not None

    def exec_check_output(self, cmd) -> bytes:
        """
        Wrapper for shell.exec_check_output
        :param cmd: Command to execute
        :return: output
        """
        return shell.exec_check_output(cmd, self.url)

    def exec_call(self, cmd) -> int:
        """
        Wrapper for shell.exec_call
        :param cmd: Command to execute
        :return: returncode
        """
        return shell.exec_call(cmd, self.url)

    def create_subprocess_args(self, cmd) -> list:
        """
        Wrapper for shell.create_subprocess_args, autmoatically passing location url
        :param cmd: Command to execute
        :return: subprocess args
        """
        return shell.create_subprocess_args(cmd, self.url)

    def remove_subvolume(self, subvolume_path):
        self._log_info('removing subvolume [%s]' % subvolume_path)
        self.exec_check_output('btrfs sub del "%s"' % subvolume_path)

    def __str__(self):
        return self._format_log_msg('url [%s]' % (self.url.geturl()))


class JobLocation(Location):
    """
    Backup job location
    """
    __TEMP_SUBVOL_NAME = 'temp'
    __CONFIG_FILENAME = '.btrfs-sxbackup'

    # Configuration file keys
    __KEY_UUID = 'uuid'
    __KEY_SOURCE = 'source'
    __KEY_SOURCE_CONTAINER = 'source-container'
    __KEY_DESTINATION = 'destination'
    __KEY_KEEP = 'keep'
    __KEY_RETENTION = 'retention'
    __KEY_COMPRESS = 'compress'

    TYPE_SOURCE = 'Source'
    TYPE_DESTINATION = 'Destination'

    def __init__(self, url: parse.SplitResult, location_type=None,
                 container_subvolume_relpath: str=None):
        """
        c'tor
        :param url: Location URL
        """
        super().__init__(url)

        self.__location_type = None
        self.__uuid = None
        self.__container_subvolume_relpath = None
        self.__compress = False
        self.__retention = None
        self.__snapshot_names = []

        self.location_type = location_type

        if self.location_type == JobLocation.TYPE_SOURCE and container_subvolume_relpath is None:
            self.container_subvolume_relpath = _DEFAULT_CONTAINER_RELPATH
        else:
            self.container_subvolume_relpath = container_subvolume_relpath

    def _format_log_msg(self, msg) -> str:
        name = self.__location_type
        return '%s :: %s' % (name.lower(), msg) if name else msg

    @property
    def snapshot_names(self) -> list:
        """
        Most recently retrieved snapshot names
        """
        return self.__snapshot_names

    @property
    def location_type(self):
        return self.__location_type

    @location_type.setter
    def location_type(self, location_type):
        if location_type and location_type != JobLocation.TYPE_SOURCE and location_type != JobLocation.TYPE_DESTINATION:
            raise ValueError('Location type must be one of [%s]'
                             % ', '.join([JobLocation.TYPE_SOURCE, JobLocation.TYPE_DESTINATION, None]))

        self.__location_type = location_type

    @property
    def uuid(self) -> UUID:
        return self.__uuid

    @uuid.setter
    def uuid(self, value: UUID):
        self.__uuid = value

    @property
    def container_subvolume_relpath(self) -> str:
        return self.__container_subvolume_relpath

    @container_subvolume_relpath.setter
    def container_subvolume_relpath(self, value: str):
        if value and not value.endswith(os.path.sep):
            value += os.path.sep
        self.__container_subvolume_relpath = value

    @property
    def retention(self) -> RetentionExpression:
        return self.__retention

    @retention.setter
    def retention(self, retention: RetentionExpression):
        self.__retention = retention

    @property
    def compress(self) -> bool:
        return self.__compress

    @compress.setter
    def compress(self, compress: bool):
        self.__compress = compress

    @property
    def container_subvolume_path(self) -> str:
        return os.path.join(self.url.path, self.container_subvolume_relpath) \
            if self.container_subvolume_relpath else self.url.path

    @property
    def configuration_filename(self) -> str:
        return os.path.join(self.container_subvolume_path, self.__CONFIG_FILENAME)

    def has_configuration(self):
        returncode = self.exec_call('if [ -f "%s" ] ; then exit 10; fi' % self.configuration_filename)
        return returncode == 10

    def prepare_environment(self):
        """ Prepare location environment """

        temp_subvolume_path = os.path.join(self.container_subvolume_path, self.__TEMP_SUBVOL_NAME)

        # Create container subvolume if it does not exist
        self.exec_check_output('if [ ! -d "%s" ] ; then btrfs sub create "%s"; fi' % (
            self.container_subvolume_path, self.container_subvolume_path))

        # Check if path is actually a subvolume
        self.exec_check_output('btrfs sub show "%s"' % self.container_subvolume_path)

        # Check and remove temporary snapshot volume (possible leftover of previously interrupted backup)
        self.exec_check_output(
            'if [ -d "%s" ] ; then btrfs sub del "%s"; fi' % (temp_subvolume_path, temp_subvolume_path))

    def retrieve_snapshot_names(self):
        """ Determine snapshot names. Snapshot names are sorted in reverse order (newest first).
        stored internally (self.snapshot_names) and also returned. """

        self._log_info('retrieving snapshot names')

        output = self.exec_check_output('btrfs sub list -o "%s"' % self.container_subvolume_path)

        # output is delivered as a byte sequence, decode to unicode string and split lines
        lines = output.decode().splitlines()

        subvolumes = list(map(lambda x: Subvolume.parse(x), lines))

        # verify snapshot subvolume path consistency
        if len(subvolumes) > 0:
            subvol_path = os.path.dirname(subvolumes[0].path)
            subvol_inconsistent_path = \
                next((s.path for s in subvolumes if os.path.dirname(s.path) != subvol_path), None)

            if subvol_inconsistent_path:
                raise Exception('inconsistent path detected at %s [%s != %s], indicating a nested'
                                ' folder/subvolume structure within a container subvolume.'
                                ' each backup job must have a dedicated source/destination container subvolume'
                                % (self.url.path, subvol_path, subvol_inconsistent_path))

        # sort and return
        snapshot_names = []
        for sv in subvolumes:
            try:
                snapshot_names.append(SnapshotName.parse(os.path.basename(sv.path)))
            except:
                # skip snapshot names which cannot be parsed
                pass

        self.__snapshot_names = sorted(snapshot_names, key=lambda sn: sn.timestamp, reverse=True)
        return self.__snapshot_names

    def create_snapshot(self, name):
        """ Creates a new (temporary) snapshot within container subvolume """
        # Create new temporary snapshot (source)
        self._log_info('creating snapshot')
        self.exec_check_output('btrfs sub snap -r "%s" "%s" && sync'
                               % (self.url.path, os.path.join(self.container_subvolume_path, name)))

    def remove_snapshots(self, snapshots: list):
        if not snapshots or len(snapshots) == 0:
            return

        cmd = 'cd "%s" && btrfs sub del %s' % (self.container_subvolume_path,
                                               ' '.join(map(lambda x: '"%s"' % x, snapshots)))

        self.exec_check_output(cmd)

    def remove_configuration(self):
        self._log_info('removing configuration')
        self.exec_check_output('rm "%s"' % self.configuration_filename)

    def cleanup_snapshots(self):
        """ Clean out excess backups/snapshots. The newst one (index 0) will always be kept. """
        if self.__retention is not None and len(self.__snapshot_names) > 1:
            (to_remove_by_condition, to_retain) = self.__retention.filter(self.__snapshot_names[1:],
                                                                          lambda sn: sn.timestamp)

            for c in to_remove_by_condition.keys():
                to_remove = to_remove_by_condition[c]

                self._log_info('removing %d snapshot%s due to retention [%s]: %s'
                               % (len(to_remove),
                                  's' if len(to_remove) > 1 else '',
                                  str(c), ', '.join(list(map(lambda x: str(x), to_remove)))))
                self.remove_snapshots(list(map(lambda x: str(x), to_remove)))

    def destroy(self, purge=False):
        """
        Destroy this backup location.
        Removes configuration file and (optionally) all snapshots
        :param purge: Purgs all snapshots in addition
        """
        self.retrieve_snapshot_names()

        if purge:
            self._log_info('purging all snapshots')
            self.remove_snapshots(list(map(lambda x: str(x), self.snapshot_names)))
            self.snapshot_names.clear()

        self.remove_configuration()

        if (len(self.snapshot_names) == 0 and
                self.location_type == JobLocation.TYPE_SOURCE and
                self.container_subvolume_relpath):
            self.remove_subvolume(self.container_subvolume_path)

    def transfer_snapshot(self, name: str, target: 'Location'):
        # Create source snapshot
        self.create_snapshot(self.__TEMP_SUBVOL_NAME)

        # Transfer temporary snapshot
        self._log_info('transferring snapshot')

        temp_source_path = os.path.join(self.container_subvolume_path, self.__TEMP_SUBVOL_NAME)
        temp_dest_path = os.path.join(target.container_subvolume_path, self.__TEMP_SUBVOL_NAME)

        # btrfs send command/subprocess
        if len(self.snapshot_names) == 0:
            send_command_str = 'btrfs send "%s"' % temp_source_path
        else:
            send_command_str = 'btrfs send -p "%s" "%s"' % (
                os.path.join(self.container_subvolume_path, str(self.snapshot_names[0])),
                temp_source_path)

        if self.compress:
            send_command_str += ' | lzop -1'

        send_process = subprocess.Popen(self.create_subprocess_args(send_command_str),
                                        stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE)

        # pv command/subprocess for progress indication
        pv_process = None
        if shell.exists('pv'):
            pv_process = subprocess.Popen(['pv'], stdin=send_process.stdout, stdout=subprocess.PIPE)

        # btrfs receive command/subprocess
        receive_command_str = 'btrfs receive "%s"' % target.url.path
        if self.compress:
            receive_command_str = 'lzop -d | ' + receive_command_str

        receive_process = subprocess.Popen(target.create_subprocess_args(receive_command_str),
                                           stdin=pv_process.stdout if pv_process is not None else send_process.stdout,
                                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

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

        # Wait for commands to complete
        send_returncode = send_process.wait()
        receive_returncode = receive_process.wait()
        if send_returncode:
            raise subprocess.CalledProcessError(send_process.returncode,
                                                send_process.args,
                                                None)
        if receive_returncode:
            raise subprocess.CalledProcessError(receive_process.returncode,
                                                receive_process.args,
                                                receive_process.stdout.read())

        # After successful transmission, rename source and destination-side
        # snapshot subvolumes (from pending to timestamp-based name)
        final_source_path = os.path.join(self.container_subvolume_path, str(name))
        final_target_path = os.path.join(target.url.path, str(name))
        self.exec_check_output('mv "%s" "%s"' % (temp_source_path, final_source_path))
        try:
            target.exec_check_output('mv "%s" "%s"' % (temp_dest_path, final_target_path))
        except Exception as e:
            # Try to avoid inconsistent state by removing successfully created source snapshot
            try:
                self.remove_subvolume(final_source_path)
            except Exception as e2:
                self.__logger.error(e2)
            raise e

    def write_configuration(self, corresponding_location: 'Location'):
        """ Write configuration file to container subvolume """
        if not self.location_type:
            raise ValueError('missing location type')

        if not corresponding_location.location_type:
            raise ValueError('missing corresponding location type')

        if self.location_type == corresponding_location.location_type:
            raise ValueError('invalid corresponding lcoation type [%s] for this location [%s]'
                             % (corresponding_location, self.location_type))

        if self.uuid != corresponding_location.uuid:
            raise ValueError('corresponding location has different uuid [%s != %s]'
                             % (self.uuid, corresponding_location.uuid))

        location_uuid = self.uuid
        source = None
        source_container = None
        destination = None
        retention = self.retention.expression_text if self.retention else None
        compress = self.compress

        # Set configuration fields to write
        both_remote_or_local = not (self.is_remote() ^ corresponding_location.is_remote())

        if self.location_type == JobLocation.TYPE_SOURCE:
            if both_remote_or_local:
                source = self.url.geturl()
                source_container = self.container_subvolume_relpath

            if both_remote_or_local or corresponding_location.is_remote():
                destination = corresponding_location.url.geturl()

        elif self.location_type == JobLocation.TYPE_DESTINATION:
            if both_remote_or_local:
                destination = self.url.geturl()

            if both_remote_or_local or corresponding_location.is_remote():
                source = corresponding_location.url.geturl()
                source_container = corresponding_location.container_subvolume_relpath

        # Configuration to string
        fileobject = io.StringIO()

        parser = ConfigParser()

        section = self.location_type
        parser.add_section(section)
        if location_uuid:
            parser.set(section, self.__KEY_UUID, str(location_uuid))
        if source:
            parser.set(section, self.__KEY_SOURCE, str(source))
        if source_container:
            parser.set(section, self.__KEY_SOURCE_CONTAINER, source_container)
        if destination:
            parser.set(section, self.__KEY_DESTINATION, str(destination))
        if retention:
            parser.set(section, self.__KEY_RETENTION, str(retention))
        if compress:
            parser.set(section, self.__KEY_COMPRESS, str(compress))
        parser.write(fileobject)

        config_str = fileobject.getvalue()

        # Write config file to location directory
        p = subprocess.Popen(self.create_subprocess_args('cat > "%s"' % self.configuration_filename),
                             stdin=subprocess.PIPE,
                             stderr=subprocess.STDOUT)
        (out, err) = p.communicate(input=bytes(config_str, 'utf-8'))
        if p.wait():
            raise subprocess.CalledProcessError(returncode=p.returncode, cmd=p.args, output=out)

    def read_configuration(self) -> 'Location':
        """
        Read configuration file from container subvolume
        :return: Corresponding location
        """
        # Read configuration file
        out = self.exec_check_output('cat "%s"' % self.configuration_filename)
        file = out.decode().splitlines()

        corresponding_location = None

        parser = ConfigParser()
        parser.read_file(file)

        section = parser.sections()[0]

        # Section name implies location type
        if section == JobLocation.TYPE_SOURCE:
            location_type = JobLocation.TYPE_SOURCE
        elif section == JobLocation.TYPE_DESTINATION:
            location_type = JobLocation.TYPE_DESTINATION
        else:
            raise ValueError('invalid section name/location type [%s]' % section)

        # Parse config string values
        location_uuid = parser.get(section, self.__KEY_UUID, fallback=None)
        source = parser.get(section, self.__KEY_SOURCE, fallback=None)
        source_container = parser.get(section, self.__KEY_SOURCE_CONTAINER, fallback=None)
        destination = parser.get(section, self.__KEY_DESTINATION, fallback=None)
        # Keep has been renamed to retention.
        # Supporting the old name for backward compatibility.
        retention = parser.get(section, self.__KEY_RETENTION, fallback=None)
        if not retention:
            retention = parser.get(section, self.__KEY_KEEP, fallback=None)

        # Convert to instances where applicable
        location_uuid = UUID(location_uuid) if location_uuid else None
        source = parse.urlsplit(source) if source else None
        source_container = source_container if source_container else None
        destination = parse.urlsplit(destination) if destination else None
        retention = RetentionExpression(retention) if retention else None
        compress = True if distutils.util.strtobool(parser.get(section, self.__KEY_COMPRESS, fallback='False')) \
            else False

        if location_type == JobLocation.TYPE_SOURCE:
            # Amend url/container relpath from current path for source locations
            # if container relative path was not provided
            if not self.container_subvolume_relpath:
                source_container = os.path.basename(self.container_subvolume_path.rstrip(os.path.sep))
                source = parse.SplitResult(self.url.scheme,
                                           self.url.netloc,
                                           os.path.abspath(os.path.join(self.url.path, os.path.pardir)),
                                           self.url.query, None)

                self.url = source
                self.container_subvolume_relpath = source_container

            if destination:
                corresponding_location = JobLocation(destination,
                                                     location_type=JobLocation.TYPE_DESTINATION)

        elif location_type == JobLocation.TYPE_DESTINATION:
            if source:
                corresponding_location = JobLocation(source,
                                                     location_type=JobLocation.TYPE_SOURCE,
                                                     container_subvolume_relpath=source_container)

        self.location_type = location_type
        self.uuid = location_uuid
        self.retention = retention
        self.compress = compress

        return corresponding_location

    def __str__(self):
        return self._format_log_msg('url [%s] %sretention [%s] compress [%s]'
                                    % (self.url.geturl(),
                                       ('container [%s] ' % self.container_subvolume_relpath)
                                       if self.container_subvolume_relpath else '',
                                       self.retention,
                                       self.compress))


class Job:
    """
    Backup job, comprises a source and destination job location and related tasks
    """

    def __init__(self, source: JobLocation, dest: JobLocation):
        self.__source = source
        self.__dest = dest

    @property
    def source(self):
        return self.__source

    @property
    def destination(self):
        return self.__dest

    @staticmethod
    def init(source_url: parse.SplitResult,
             dest_url: parse.SplitResult,
             source_retention: RetentionExpression=None,
             dest_retention: RetentionExpression=None,
             compress: bool=None) -> 'Job':
        """
        Initializes a new backup job
        :param source_url: Source url string
        :param dest_url: Destination url string
        :param source_retention: Source retention expression string
        :param dest_retention: Destination retention expression string
        :param compress: Compress flag
        :return: Backup job
        :rtype: Job
        """
        source = JobLocation(source_url, location_type=JobLocation.TYPE_SOURCE)
        dest = JobLocation(dest_url, location_type=JobLocation.TYPE_DESTINATION)

        if source.has_configuration():
            raise Error('source is already initialized')

        if dest.has_configuration():
            raise Error('destination is already initialized')

        # New uuid for both locations
        dest.uuid = source.uuid = uuid.uuid4()

        # Set parameters
        if source_retention:
            source.retention = source_retention
        if not source.retention:
            source.retention = Configuration.instance().source_retention
        if not source.retention:
            source.retention = RetentionExpression(_DEFAULT_RETENTION_SOURCE)

        if dest_retention:
            dest.retention = dest_retention
        if not dest.retention:
            dest.retention = Configuration.instance().destination_retention
        if not dest.retention:
            dest.retention = RetentionExpression(_DEFAULT_RETENTION_DESTINATION)

        if compress:
            source.compress = dest.compress = compress
        if not source.compress:
            source.compress = False
        if not dest.compress:
            dest.compress = False

        # Prepare environments
        _logger.info('preparing source and destination environment')
        source.prepare_environment()
        dest.prepare_environment()

        # Writing configurations
        source.write_configuration(dest)
        dest.write_configuration(source)

        _logger.info(source)
        _logger.info(dest)

        _logger.info('initialized successfully')

        return Job(source, dest)

    @staticmethod
    def load(url: parse.SplitResult, raise_errors: bool=True) -> 'Job':
        """
        Loads a backup job from an existing backup location (source or destination)
        :param url: Location URL
        :return: Backup job
        """

        def handle_error(e):
            if raise_errors:
                raise e
            else:
                _logger.error(str(e))

        location = JobLocation(url)

        corresponding_location = None
        try:
            if not location.has_configuration():
                location.container_subvolume_relpath = _DEFAULT_CONTAINER_RELPATH

            corresponding_location = location.read_configuration()
        except subprocess.CalledProcessError:
            handle_error(Error('could not read configuration [%s]' % location.configuration_filename))

        if corresponding_location:
            try:
                corresponding_location.read_configuration()
            except subprocess.CalledProcessError:
                handle_error(Error('could not read configuration [%s]' % corresponding_location.configuration_filename))

        if location.location_type == JobLocation.TYPE_SOURCE:
            source = location
            dest = corresponding_location
        else:
            dest = location
            source = corresponding_location

        if not dest:
            handle_error(Error('location nas no destination information'))

        if not source:
            handle_error(Error('location has no source information'))

        return Job(source, dest)

    def update(self, source_retention: RetentionExpression=None, dest_retention: RetentionExpression=None,
               compress: bool=None):
        """
        Update backup job parameters
        :param source_retention: Source retention
        :param dest_retention: Destination retention
        :param compress: Compress
        """
        if not self.source.uuid or not self.destination.uuid:
            raise Error('update of existing locations requires uuids. this backup job was presumably created'
                        ' with an older version.')

        if self.source.uuid != self.destination.uuid:
            raise Error('update of existing locations requires consistent location uuids,'
                        ' source [%s] != destination [%s].'
                        % (self.source.uuid, self.destination.uuid))

        _logger.info(self.source)
        _logger.info(self.destination)

        _logger.info('updating configurations')

        if source_retention:
            self.source.retention = source_retention

        if dest_retention:
            self.destination.retention = dest_retention

        if compress:
            self.source.compress = self.destination.compress = compress

        _logger.info(self.source)
        _logger.info(self.destination)

        self.source.write_configuration(self.destination)
        self.destination.write_configuration(self.source)

        _logger.info('updated successfully')

    def run(self):
        """ Performs backup run """
        starting_time = time.monotonic()

        _logger.info(self.source)
        _logger.info(self.destination)

        # Prepare environments
        _logger.info('preparing environment')
        self.source.prepare_environment()
        self.destination.prepare_environment()

        # Retrieve snapshot names of both source and destination
        self.source.retrieve_snapshot_names()
        self.destination.retrieve_snapshot_names()

        new_snapshot_name = SnapshotName()
        if len(self.source.snapshot_names) > 0 \
                and new_snapshot_name.timestamp <= self.source.snapshot_names[0].timestamp:
            raise Error('current snapshot name [%s] would be older than newest existing snapshot [%s] \
                                 which may indicate a system time problem'
                        % (new_snapshot_name, self.source.snapshot_names[0]))

        self.source.transfer_snapshot(str(new_snapshot_name), self.destination)

        # Update snapshot name lists
        self.source.snapshot_names.insert(0, new_snapshot_name)
        self.destination.snapshot_names.insert(0, new_snapshot_name)

        # Clean out excess backups/snapshots
        self.source.cleanup_snapshots()
        self.destination.cleanup_snapshots()

        _logger.info('backup %s created successfully in %s'
                     % (new_snapshot_name,
                        time.strftime("%H:%M:%S", time.gmtime(time.monotonic() - starting_time))))

    def destroy(self, purge=False):
        """
        Destroys both source and destination
        :param purge: Purge all snapshots
        """
        self.source.destroy(purge=purge)
        self.destination.destroy(purge=purge)

    def print_info(self):
        source = self.source
        dest = self.destination

        if self.source and source.location_type:
            try:
                self.source.retrieve_snapshot_names()
            except Exception as e:
                _logger.error(str(e))

        if self.destination and dest.location_type:
            try:
                self.destination.retrieve_snapshot_names()
            except Exception as e:
                _logger.error(str(e))

        if (source and source.location_type) or (dest and dest.location_type):
            t_inset = 3
            t_na = 'n/a'
            i = collections.OrderedDict()
            i['UUID'] = source.uuid if source else dest.uuid if dest else t_na
            i['Compress'] = str(source.compress) if source else dest.compress if dest else t_na
            i['Source URL'] = source.url.geturl().rstrip(os.path.sep) if source else t_na
            i['Source container'] = source.container_subvolume_relpath.rstrip(os.path.sep) if source else t_na
            i['Source retention'] = str(source.retention) if source else t_na
            i['Source snapshots'] = source.snapshot_names if source else t_na
            i['Destination URL'] = dest.url.geturl().rstrip(os.path.sep) if dest else t_na
            i['Destination retention'] = str(dest.retention) if dest else t_na
            i['Destination snapshots'] = dest.snapshot_names if dest else t_na

            width = len(max(i.keys(), key=lambda x: len(x))) + 1

            for label in i.keys():
                value = i[label]
                if value:
                    if isinstance(value, list):
                        for j in range(0, len(value)):
                            s = value[j]
                            label = label.ljust(width) if j == 0 else ''.ljust(width)
                            label = label.rjust(width + t_inset)
                            print('%s %s' % (label, s))
                    else:
                        print('%s %s' % (label.ljust(width).rjust(width + t_inset), i[label]))

