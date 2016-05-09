# Copyright (c) 2014 Marco Schindler
#
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the Free
# Software Foundation; either version 2 of the License, or (at your option)
# any later version.

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

from btrfs_sxbackup.entities import Snapshot
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
            value = parse.SplitResult(scheme=value.scheme,
                                      netloc=value.netloc,
                                      path=final_path,
                                      query=value.query,
                                      fragment=None)
        self.__url = value

    def _format_log_msg(self, msg) -> str:
        name = self.url.geturl()
        return '%s :: %s' % (name.lower(), msg) if name else msg

    def _log_info(self, msg):
        self.__logger.info(self._format_log_msg(msg))

    def _log_warn(self, msg):
        self.__logger.warn(self._format_log_msg(msg))

    def _log_error(self, msg):
        self.__logger.error(self._format_log_msg(msg))

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

    def build_subprocess_args(self, cmd) -> list:
        """
        Wrapper for shell.create_subprocess_args, autmoatically passing location url
        :param cmd: Command to execute
        :return: subprocess args
        """
        return shell.build_subprocess_args(cmd, self.url)

    def build_path(self, path: str) -> str:
        """
        Creates a path in the context of this location.
        Relative paths will be joined with the location's url path
        :param path: Base path
        :return: Contextual path
        """
        if not path:
            return self.url.path

        if path.startswith(os.path.sep):
            return path
        else:
            return os.path.join(self.url.path, path)

    def get_kernel_version(self):
        return self.exec_check_output('uname -srvo').decode().strip()

    def get_btrfs_progs_version(self):
        return self.exec_check_output('btrfs version').decode().strip()

    def dir_exists(self, path) -> bool:
        path = self.build_path(path)
        returncode = self.exec_call('if [ -d "%s" ]; then exit 10; fi' % path)
        return returncode == 10

    def touch(self, path):
        path = self.build_path(path)
        self.exec_check_output('touch "%s"' % path)

    def move_file(self, source_path: str, dest_path: str):
        source_path = self.build_path(source_path)
        dest_path = self.build_path(dest_path)
        self._log_debug('moving file [%s] -> [%s]' % (source_path, dest_path))
        self.exec_check_output('mv "%s" "%s"' % (source_path, dest_path))

    def remove_btrfs_subvolume(self, subvolume_path):
        subvolume_path = self.build_path(subvolume_path)
        self._log_info('removing subvolume [%s]' % subvolume_path)
        self.exec_check_output('if [ -d "%s" ]; then btrfs sub del "%s"; fi' % (subvolume_path, subvolume_path))

    def create_btrfs_snapshot(self, source_path, dest_path):
        source_path = self.build_path(source_path)
        dest_path = self.build_path(dest_path)

        # Create new temporary snapshot (source)
        self._log_info('creating snapshot')
        self.exec_check_output('btrfs sub snap -r "%s" "%s" && sync'
                               % (source_path, dest_path))

    def transfer_btrfs_snapshot(self,
                                dest: 'Location',
                                source_path: str = None,
                                dest_path: str = None,
                                source_parent_path: str = None,
                                compress: bool = False):

        source_path = self.build_path(source_path)
        source_parent_path = self.build_path(source_parent_path) if source_parent_path else None
        dest_path = dest.build_path(dest_path)

        name = os.path.basename(source_path.rstrip(os.path.sep))
        final_dest_path = os.path.join(dest_path, name)

        if len(name) == 0:
            raise ValueError('source base name cannot be empty')

        if dest.dir_exists(final_dest_path):
            raise Error('destination path [%s] already exists' % final_dest_path)

        # Transfer temporary snapshot
        self._log_info('transferring snapshot')

        # btrfs send command/subprocess
        if source_parent_path:
            send_command_str = 'btrfs send -p "%s" "%s"' % (source_parent_path, source_path)
        else:
            send_command_str = 'btrfs send "%s"' % source_path

        if compress:
            send_command_str += ' | lzop -1'

        try:
            send_process = subprocess.Popen(self.build_subprocess_args(send_command_str),
                                            stdout=subprocess.PIPE,
                                            stderr=subprocess.PIPE)

            # pv command/subprocess for progress indication
            pv_process = None
            if shell.exists('pv'):
                pv_process = subprocess.Popen(['pv'], stdin=send_process.stdout, stdout=subprocess.PIPE)

            # btrfs receive command/subprocess
            receive_command_str = 'btrfs receive "%s"' % dest_path
            if compress:
                receive_command_str = 'lzop -d | ' + receive_command_str

            receive_process = subprocess.Popen(dest.build_subprocess_args(receive_command_str),
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

            def log_process_error(proc_returncode, proc_args, proc_out):
                proc_out_fmt = proc_out.read().decode().strip()
                self._log_error('Command %s failed with error code %d (%s)'
                                % (proc_args, proc_returncode, proc_out_fmt))

            if receive_returncode:
                log_process_error(receive_process.returncode, receive_process.args, receive_process.stdout)

            if send_returncode:
                log_process_error(send_process.returncode, send_process.args, send_process.stderr)

            if receive_returncode or send_returncode:
                raise Error("Transferring snapshot failed")

        except BaseException as e:
            try:
                # Try to remove incomplete destination subvolume
                dest.remove_btrfs_subvolume(final_dest_path)
            except Exception as e2:
                self._log_warn('could not remove incomplete destination subvolume [%s]' % final_dest_path)
            raise e

    def __str__(self):
        return self._format_log_msg('url [%s]' % (self.url.geturl()))


class JobLocation(Location):
    """
    Backup job location
    """
    __CONFIG_FILENAME = '.btrfs-sxbackup'
    __TEMP_BASENAME = '.temp'

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
                 container_subvolume_relpath: str = None):
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
        self.__snapshots = []

        self.location_type = location_type

        if self.location_type == JobLocation.TYPE_SOURCE and container_subvolume_relpath is None:
            self.container_subvolume_relpath = _DEFAULT_CONTAINER_RELPATH
        else:
            self.container_subvolume_relpath = container_subvolume_relpath

    def _format_log_msg(self, msg) -> str:
        name = self.__location_type
        return '%s :: %s' % (name.lower(), msg) if name else msg

    @property
    def snapshots(self) -> list:
        """
        Most recently retrieved snapshot names
        """
        return self.__snapshots

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
        returncode = self.exec_call('if [ -f "%s" ]; then exit 10; fi' % self.configuration_filename)
        return returncode == 10

    def create_temp_name(self):
        return '%s.%s' % (self.__TEMP_BASENAME, uuid.uuid4().hex)

    def prepare_environment(self):
        """ Prepare location environment """

        # Create container subvolume if it does not exist
        self.exec_check_output('if [ ! -d "%s" ]; then btrfs sub create "%s"; fi' % (
            self.container_subvolume_path, self.container_subvolume_path))

        # Check if path is actually a subvolume
        self.exec_check_output('btrfs sub show "%s"' % self.container_subvolume_path)

        # Check and remove temporary snapshot volume (possible leftover of previously interrupted backup)
        temp_subvolume_path = os.path.join(self.container_subvolume_path, self.__TEMP_BASENAME)
        self.exec_check_output(
            'if [ -d "%s"* ]; then btrfs sub del "%s"*; fi' % (temp_subvolume_path, temp_subvolume_path))

    def retrieve_snapshots(self):
        """ Determine snapshot names. Snapshot names are sorted in reverse order (newest first).
        stored internally (self.snapshot_names) and also returned. """

        self._log_info('retrieving snapshots')

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
        snapshots = []
        for sv in subvolumes:
            try:
                snapshots.append(Snapshot(SnapshotName.parse(os.path.basename(sv.path)), sv))
            except:
                # skip snapshot names which cannot be parsed
                pass

        self.__snapshots = sorted(snapshots, key=lambda s: s.name.timestamp, reverse=True)
        return self.__snapshots

    def create_snapshot(self, name):
        """
        Creates a new snapshot within container subvolume
        :param name: Name of snapshot
        """
        # Touch source volume root, updating its mtime
        self.touch(self.url.path)

        # Create new temporary snapshot (source)
        dest_path = os.path.join(self.container_subvolume_path, name)
        self.create_btrfs_snapshot(self.url.path, dest_path)
        return dest_path

    def remove_snapshots(self, snapshots: list):
        """
        Remove snapshots from container subvolume
        :param snapshots: Names of snapshots to remove
        """
        if not snapshots or len(snapshots) == 0:
            return

        cmd = 'cd "%s" && btrfs sub del %s' % (self.container_subvolume_path,
                                               ' '.join(map(lambda x: '"%s"' % x, snapshots)))

        self.exec_check_output(cmd)

    def remove_configuration(self):
        """
        Remove backup job configuration file
        """
        self._log_info('removing configuration')
        self.exec_check_output('rm "%s"' % self.configuration_filename)

    def purge_snapshots(self, retention: RetentionExpression = None):
        """
        Purge snapshots
        :param retention: Optional override of location's retention
        :type retention: RetentionExpression
        """
        if retention is None:
            retention = self.__retention
        else:
            self._log_info('Retention expression override [%s]' % retention)

        """ Clean out excess backups/snapshots. The newest one (index 0) will always be kept. """
        if retention is not None and len(self.__snapshots) > 1:
            (to_remove_by_condition, to_retain) = retention.filter(self.__snapshots[1:],
                                                                   lambda sn: sn.name.timestamp)

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
        self.retrieve_snapshots()

        if purge:
            self._log_info('purging all snapshots')
            self.remove_snapshots(list(map(lambda x: str(x.name), self.snapshots)))
            self.snapshots.clear()

        self.remove_configuration()

        if (len(self.snapshots) == 0 and
                    self.location_type == JobLocation.TYPE_SOURCE and
                self.container_subvolume_relpath):
            self.remove_btrfs_subvolume(self.container_subvolume_path)

    def write_configuration(self, corresponding_location: 'JobLocation'):
        """ Write configuration file to container subvolume 
        :type corresponding_location: JobLocation
        """
        if not self.location_type:
            raise ValueError('missing location type')

        if corresponding_location:
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
        both_remote_or_local = not (
            self.is_remote() ^ (corresponding_location is not None and corresponding_location.is_remote()))

        if self.location_type == JobLocation.TYPE_SOURCE:
            if both_remote_or_local:
                source = self.url.geturl()
                source_container = self.container_subvolume_relpath

            if corresponding_location and (both_remote_or_local or corresponding_location.is_remote()):
                destination = corresponding_location.url.geturl()

        elif self.location_type == JobLocation.TYPE_DESTINATION:
            if both_remote_or_local:
                destination = self.url.geturl()

            if corresponding_location and (both_remote_or_local or corresponding_location.is_remote()):
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
        p = subprocess.Popen(self.build_subprocess_args('cat > "%s"' % self.configuration_filename),
                             stdin=subprocess.PIPE,
                             stderr=subprocess.STDOUT)
        (out, err) = p.communicate(input=bytes(config_str, 'utf-8'))
        if p.wait():
            raise subprocess.CalledProcessError(returncode=p.returncode, cmd=p.args, output=out)

    def read_configuration(self) -> 'JobLocation':
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
                source = parse.SplitResult(scheme=self.url.scheme,
                                           netloc=self.url.netloc,
                                           path=os.path.abspath(os.path.join(self.url.path, os.path.pardir)),
                                           query=self.url.query,
                                           fragment=None)

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
             source_retention: RetentionExpression = None,
             dest_retention: RetentionExpression = None,
             compress: bool = None) -> 'Job':
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
        dest = JobLocation(dest_url, location_type=JobLocation.TYPE_DESTINATION) if dest_url else None

        if source.has_configuration():
            raise Error('source is already initialized')

        if dest and dest.has_configuration():
            raise Error('destination is already initialized')

        # New uuid for both locations
        source.uuid = uuid.uuid4()
        if dest:
            dest.uuid = source.uuid

        # Set parameters
        if source_retention:
            source.retention = source_retention
        if not source.retention:
            source.retention = Configuration.instance().source_retention
        if not source.retention:
            source.retention = RetentionExpression(_DEFAULT_RETENTION_SOURCE)

        if dest:
            if dest_retention:
                dest.retention = dest_retention
            if not dest.retention:
                dest.retention = Configuration.instance().destination_retention
            if not dest.retention:
                dest.retention = RetentionExpression(_DEFAULT_RETENTION_DESTINATION)

        if compress:
            source.compress = compress
            if dest:
                dest.compress = compress
        if not source.compress:
            source.compress = False
        if dest and not dest.compress:
            dest.compress = False

        # Prepare environments
        _logger.info('preparing source and destination environment')
        source.prepare_environment()
        if dest:
            dest.prepare_environment()

        # Writing configurations
        source.write_configuration(dest)
        if dest:
            dest.write_configuration(source)

        _logger.info(source)
        if dest:
            _logger.info(dest)

        _logger.info('initialized successfully')

        return Job(source, dest)

    @staticmethod
    def load(url: parse.SplitResult, raise_errors: bool = True) -> 'Job':
        """
        Loads a backup job from an existing backup location (source or destination)
        :param url: Location URL
        :param raise_errors: just print errors instead of raising exceptions
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

        if not source:
            handle_error(Error('location has no source information'))

        return Job(source, dest)

    def update(self, source_retention: RetentionExpression = None, dest_retention: RetentionExpression = None,
               compress: bool = None):
        """
        Update backup job parameters
        :param source_retention: Source retention
        :param dest_retention: Destination retention
        :param compress: Compress
        """
        if not self.source.uuid or (self.destination and not self.destination.uuid):
            raise Error('update of existing locations requires uuids. this backup job was presumably created'
                        ' with an older version.')

        if self.destination and self.source.uuid != self.destination.uuid:
            raise Error('update of existing locations requires consistent location uuids,'
                        ' source [%s] != destination [%s].'
                        % (self.source.uuid, self.destination.uuid))

        _logger.info('updating configurations')

        if source_retention:
            self.source.retention = source_retention

        if dest_retention:
            if self.destination is None:
                raise Error('backup job has no destination')
            self.destination.retention = dest_retention

        if compress is not None:
            self.source.compress = compress
            if self.destination:
                self.destination.compress = compress

        self.print_info(include_snapshots=False)

        self.source.write_configuration(self.destination)
        if self.destination:
            self.destination.write_configuration(self.source)

        _logger.info('updated successfully')

    def purge(self, source_retention: RetentionExpression = None, dest_retention: RetentionExpression = None):
        """
        Purge backups/snapshots
        :param source_retention: Optional source retention override
        :param dest_retention: Optional destination retention override
        :return:
        """
        _logger.info(self.source)
        if self.destination:
            _logger.info(self.destination)

        # Retrieve snapshot names of both source and destination
        self.source.retrieve_snapshots()
        if self.destination:
            self.destination.retrieve_snapshots()

        # Clean out excess backups/snapshots
        self.source.purge_snapshots(
            retention=source_retention if source_retention is not None else None)
        if self.destination:
            self.destination.purge_snapshots(
                retention=dest_retention if dest_retention is not None else None)

    def run(self):
        """ Performs backup run """
        starting_time = time.monotonic()

        _logger.info(self.source)
        if self.destination:
            _logger.info(self.destination)

        # Prepare environments
        _logger.info('preparing environment')
        self.source.prepare_environment()
        if self.destination:
            self.destination.prepare_environment()

        # Retrieve snapshot names of both source and destination
        self.source.retrieve_snapshots()
        if self.destination:
            self.destination.retrieve_snapshots()

        new_snapshot_name = SnapshotName()
        if len(self.source.snapshots) > 0 \
                and new_snapshot_name.timestamp <= self.source.snapshots[0].name.timestamp:
            raise Error(('current snapshot name [%s] would be older than newest existing snapshot [%s] '
                         'which may indicate a system time problem')
                        % (new_snapshot_name, self.source.snapshots[0].name))

        temp_name = self.source.create_temp_name()

        # btrfs send command/subprocess
        source_parent_path = None
        if len(self.source.snapshots) > 0:
            # Latest source and destination snapshot timestamp has to match for incremental transfer
            if self.source.snapshots[0].name.timestamp == self.destination.snapshots[0].name.timestamp:
                source_parent_path = os.path.join(self.source.container_subvolume_path,
                                                  str(self.source.snapshots[0].name))
            else:
                _logger.warn(
                    ('Latest timestamps of source [%s] and destination [%s] do not match. A full snapshot will '
                     'be transferred')
                    % (self.source.snapshots[0].name.timestamp, self.destination.snapshots[0].name.timestamp))

        # Create source snapshot
        temp_source_path = self.source.create_snapshot(temp_name)

        # Recovery handler, swallows all exceptions and logs them
        def recover(l, warn_msg: str):
            try:
                l()
            except Exception as e:
                _logger.error(str(e))
                _logger.warn(warn_msg)

        temp_dest_path = None
        final_dest_path = None
        # Transfer temporary snapshot
        if self.destination:
            temp_dest_path = self.destination.build_path(temp_name)
            final_dest_path = os.path.join(self.destination.url.path, str(new_snapshot_name))

            try:
                self.source.transfer_btrfs_snapshot(self.destination,
                                                    source_path=temp_source_path,
                                                    source_parent_path=source_parent_path,
                                                    compress=self.source.compress)
            except BaseException as e:
                recover(lambda: self.source.remove_btrfs_subvolume(temp_source_path),
                        'could not remove temporary source snapshot [%s]' % temp_source_path)
                raise e

        try:
            final_source_path = os.path.join(self.source.container_subvolume_path, str(new_snapshot_name))

            # Rename temporary source snapshot to final snapshot name
            self.source.move_file(temp_source_path, final_source_path)
        except BaseException as e:
            recover(lambda: self.source.remove_btrfs_subvolume(temp_source_path),
                    'could not remove temporary source snapshot [%s]' % temp_source_path)
            if self.destination:
                recover(lambda: self.destination.remove_btrfs_subvolume(temp_dest_path),
                        'could not remove temporary destination snapshot [%s]' % temp_dest_path)
            raise e

        if self.destination:
            try:
                # Rename temporary destination snapshot to final snapshot name
                self.destination.move_file(temp_dest_path, final_dest_path)
            except Exception as e:
                # Try to avoid inconsistent state by removing successfully created source snapshot
                recover(lambda: self.source.remove_btrfs_subvolume(final_source_path),
                        'could not remove source snapshot [%s] after failed finalization of destination snapshot'
                        % final_source_path)
                recover(lambda: self.destination.remove_btrfs_subvolume(temp_dest_path),
                        'could not remove temporary destination snapshot [%s]' % temp_dest_path)
                raise e

        # Update snapshot name lists
        self.source.snapshots.insert(0, Snapshot(new_snapshot_name, None))
        if self.destination:
            self.destination.snapshots.insert(0, Snapshot(new_snapshot_name, None))

        # Clean out excess backups/snapshots
        self.source.purge_snapshots()
        if self.destination:
            self.destination.purge_snapshots()

        _logger.info('backup %s created successfully in %s'
                     % (new_snapshot_name,
                        time.strftime("%H:%M:%S", time.gmtime(time.monotonic() - starting_time))))

    def destroy(self, purge=False):
        """
        Destroys both source and destination
        :param purge: Purge all snapshots
        """
        self.source.destroy(purge=purge)
        if self.destination:
            self.destination.destroy(purge=purge)

    def print_info(self, include_snapshots=True):
        src = self.source
        dst = self.destination

        if include_snapshots:
            if src and src.location_type:
                try:
                    src.retrieve_snapshots()
                except Exception as e:
                    _logger.error(str(e))

            if dst and dst.location_type:
                try:
                    dst.retrieve_snapshots()
                except Exception as e:
                    _logger.error(str(e))

        if (src and src.location_type) or (dst and dst.location_type):
            t_inset = 3
            t_na = 'n/a'
            i = collections.OrderedDict()
            i['UUID'] = src.uuid if src else dst.uuid if dst else t_na
            i['Compress'] = str(src.compress) if src else dst.compress if dst else t_na
            i['Source URL'] = src.url.geturl().rstrip(os.path.sep) if src else t_na
            i['Source info'] = '%s, %s' % (src.get_kernel_version(), src.get_btrfs_progs_version())
            i['Source container'] = src.container_subvolume_relpath.rstrip(os.path.sep) if src else t_na
            i['Source retention'] = str(src.retention) if src else t_na
            if include_snapshots:
                i['Source snapshots'] = list(map(lambda x: x.format(), src.snapshots)) if src else t_na
            if dst:
                i['Destination URL'] = dst.url.geturl().rstrip(os.path.sep) if dst else t_na
                i['Destination info'] = '%s, %s' % (dst.get_kernel_version(), dst.get_btrfs_progs_version())
                i['Destination retention'] = str(dst.retention) if dst else t_na
                if include_snapshots:
                    i['Destination snapshots'] = list(map(lambda x: x.format(), dst.snapshots)) if dst else t_na

            width = len(max(i.keys(), key=lambda x: len(x))) + 1

            for label in i.keys():
                value = i[label]
                if value:
                    if isinstance(value, list):
                        for j in range(0, len(value)):
                            src = value[j]
                            label = label.ljust(width) if j == 0 else ''.ljust(width)
                            label = label.rjust(width + t_inset)
                            print('%s %s' % (label, src))
                    else:
                        print('%s %s' % (label.ljust(width).rjust(width + t_inset), i[label]))
