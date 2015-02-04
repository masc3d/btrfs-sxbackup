import logging
import io
import os
import subprocess
import uuid
import distutils.util
import time
from urllib import parse
from configparser import ConfigParser
from uuid import UUID

from btrfs_sxbackup import shell
from btrfs_sxbackup.entities import LocationType
from btrfs_sxbackup.retention import RetentionExpression
from btrfs_sxbackup.entities import SnapshotName
from btrfs_sxbackup.entities import Subvolume


class Location:
    """ Backup location """

    __TEMP_BACKUP_NAME = 'temp'
    __CONFIG_FILENAME = '.btrfs-sxbackup'

    # Configuration file keys
    __KEY_UUID = 'uuid'
    __KEY_SOURCE = 'source'
    __KEY_SOURCE_CONTAINER = 'source-container'
    __KEY_DESTINATION = 'destination'
    __KEY_KEEP = 'keep'
    __KEY_RETENTION = 'retention'
    __KEY_COMPRESS = 'compress'

    def __init__(self, url: parse.SplitResult, location_type: LocationType=None, container_subvolume_relpath: str=None):
        """
        c'tor
        :param url: Location URL
        """
        if not url:
            raise ValueError('Location url is mandatory')

        self.__logger = logging.getLogger(self.__class__.__name__)

        self.__location_type = location_type
        self.__url = None
        self.__container_subvolume_relpath = None
        self.__uuid = uuid.uuid4()
        self.__retention = None
        self.__compress = False
        self.__snapshot_names = []

        self.url = url

        if location_type == LocationType.Source and container_subvolume_relpath is None:
            self.container_subvolume_relpath = '.sxbackup'
        else:
            self.container_subvolume_relpath = container_subvolume_relpath

    def __format_log_msg(self, msg) -> str:
        name = self.__location_type.name if self.__location_type else None
        return '%s :: %s' % (name, msg)

    def _log_info(self, msg):
        self.__logger.info(self.__format_log_msg(msg))

    def _log_debug(self, msg):
        self.__logger.debug(self.__format_log_msg(msg))

    @property
    def snapshot_names(self) -> list:
        """
        Most recently retrieved snapshot names
        """
        return self.__snapshot_names

    @property
    def location_type(self) -> LocationType:
        return self.__location_type

    @location_type.setter
    def location_type(self, location_type):
        self.__location_type = location_type

    @property
    def uuid(self) -> UUID:
        return self.__uuid

    @uuid.setter
    def uuid(self, value: UUID):
        self.__uuid = value

    @property
    def url(self) -> parse.SplitResult:
        return self.__url

    @url.setter
    def url(self, value: parse.SplitResult):
        if not value.path.endswith(os.path.sep):
            value = parse.SplitResult(value.scheme,
                                      value.netloc,
                                      value.path + os.path.sep,
                                      value.query, None)
        self.__url = value

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

    def is_remote(self) -> bool:
        return self.url.hostname is not None

    def _exec_check_output(self, cmd) -> bytes:
        """
        Wrapper for shell.exec_check_output
        :param cmd: Command to execute
        :return: output
        """
        return shell.exec_check_output(cmd, self.url)

    def _exec_call(self, cmd) -> int:
        """
        Wrapper for shell.exec_call
        :param cmd: Command to execute
        :return: returncode
        """
        return shell.exec_call(cmd, self.url)

    def _shell_create_subprocess_args(self, cmd) -> list:
        """
        Wrapper for shell.create_subprocess_args, autmoatically passing location url
        :param cmd: Command to execute
        :return: subprocess args
        """
        return shell.create_subprocess_args(cmd, self.url)

    def has_configuration(self):
        returncode = self._exec_call('if [ -f "%s" ] ; then exit 10; fi' % self.configuration_filename)
        return returncode == 10

    def prepare_environment(self):
        """ Prepare location environment """

        temp_subvolume_path = os.path.join(self.container_subvolume_path, self.__TEMP_BACKUP_NAME)

        # Create container subvolume if it does not exist
        self._exec_check_output('if [ ! -d "%s" ] ; then btrfs sub create "%s"; fi' % (
                self.container_subvolume_path, self.container_subvolume_path))

        # Check if path is actually a subvolume
        self._exec_check_output('btrfs sub show "%s"' % self.container_subvolume_path)

        # Check and remove temporary snapshot volume (possible leftover of previously interrupted backup)
        self._exec_check_output('if [ -d "%s" ] ; then btrfs sub del "%s"; fi' % (temp_subvolume_path, temp_subvolume_path))

    def retrieve_snapshot_names(self):
        """ Determine snapshot names. Snapshot names are sorted in reverse order (newest first).
        stored internally (self.snapshot_names) and also returned. """

        self._log_info('Retrieving snapshot names')

        output = self._exec_check_output('btrfs sub list -o "%s"' % self.container_subvolume_path)

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
        self._log_info('Creating snapshot')
        self._exec_check_output('btrfs sub snap -r "%s" "%s" && sync'
                   % (self.url.path, os.path.join(self.container_subvolume_path, name)))

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

                self._exec_check_output(cmd)

    def transfer_snapshot(self, name: str, target: 'Location'):
        # Create source snapshot
        self.create_snapshot(self.__TEMP_BACKUP_NAME)

        # Transfer temporary snapshot
        self._log_info('Transferring snapshot')

        temp_source_path = os.path.join(self.container_subvolume_path, self.__TEMP_BACKUP_NAME)
        temp_dest_path = os.path.join(target.container_subvolume_path, self.__TEMP_BACKUP_NAME)

        # btrfs send command/subprocess
        if len(self.snapshot_names) == 0:
            send_command_str = 'btrfs send "%s"' % temp_source_path
        else:
            send_command_str = 'btrfs send -p "%s" "%s"' % (
                os.path.join(self.container_subvolume_path, str(self.snapshot_names[0])),
                temp_source_path)

        if self.compress:
            send_command_str += ' | lzop -1'

        send_process = subprocess.Popen(self._shell_create_subprocess_args(send_command_str),
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

        receive_process = subprocess.Popen(target._shell_create_subprocess_args(receive_command_str),
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
        self._exec_check_output('mv "%s" "%s"' % (temp_source_path,
                                     os.path.join(self.container_subvolume_path, str(name))))
        self._exec_check_output('mv "%s" "%s"' % (temp_dest_path,
                                     os.path.join(target.url.path, str(name))))

    def write_configuration(self, corresponding_location: 'Location'):
        """ Write configuration file to container subvolume """
        if not self.location_type:
            raise ValueError('Missing location type')

        if not corresponding_location.location_type:
            raise ValueError('Missing corresponding location type')

        if self.location_type == corresponding_location.location_type:
            raise ValueError('Invalid corresponding lcoation type [%s] for this location [%s]'
                             % (corresponding_location, self.location_type.name))

        if self.uuid != corresponding_location.uuid:
            raise ValueError('Corresponding location has different uuid [%s != %s]'
                             % (self.uuid, corresponding_location.uuid))

        location_uuid = self.uuid
        source = None
        source_container = None
        destination = None
        retention = self.retention.expression_text if self.retention else None
        compress = self.compress

        # Set configuration fields to write
        both_remote_or_local = not (self.is_remote() ^ corresponding_location.is_remote())

        if self.location_type == LocationType.Source:
            if both_remote_or_local:
                source = self.url.geturl()
                source_container = self.container_subvolume_relpath

            if both_remote_or_local or corresponding_location.is_remote():
                destination = corresponding_location.url.geturl()

        elif self.location_type == LocationType.Destination:
            if both_remote_or_local:
                destination = self.url.geturl()

            if both_remote_or_local or corresponding_location.is_remote():
                source = corresponding_location.url.geturl()
                source_container = corresponding_location.container_subvolume_relpath

        # Configuration to string
        fileobject = io.StringIO()

        parser = ConfigParser()

        section = self.location_type.name
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
        p = subprocess.Popen(self._shell_create_subprocess_args('cat > "%s"' % self.configuration_filename),
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
        out = self._exec_check_output('cat "%s"' % self.configuration_filename)
        file = out.decode().splitlines()

        corresponding_location = None

        parser = ConfigParser()
        parser.read_file(file)

        section = parser.sections()[0]

        # Section name implies location type
        if section == LocationType.Source.name:
            location_type = LocationType.Source
        elif section == LocationType.Destination.name:
            location_type = LocationType.Destination
        else:
            raise ValueError('Invalid section name/location type [%s]' % section)

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

        if location_type == LocationType.Source:
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
                corresponding_location = Location(destination,
                                                  location_type=LocationType.Destination)

        elif location_type == LocationType.Destination:
            if source:
                corresponding_location = Location(source,
                                                  location_type=LocationType.Source,
                                                  container_subvolume_relpath=source_container)

        self.location_type = location_type
        self.uuid = location_uuid
        self.retention = retention
        self.compress = compress

        return corresponding_location

    def __str__(self):
        return self.__format_log_msg('Url [%s] snapshot container subvolume [%s] retention [%s] compress [%s]'
                                     % (self.url.geturl(), self.container_subvolume_relpath, self.retention, self.compress))

