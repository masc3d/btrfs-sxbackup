import logging
import os
import subprocess
import time
from urllib import parse
import uuid

from btrfs_sxbackup import shell
from btrfs_sxbackup.configs import Configuration
from btrfs_sxbackup.configs import LocationConfiguration
from btrfs_sxbackup.locations import Location
from btrfs_sxbackup.locations import SourceLocation
from btrfs_sxbackup.locations import DestinationLocation
from btrfs_sxbackup.entities import SnapshotName
from btrfs_sxbackup.entities import LocationType
from btrfs_sxbackup.retention import RetentionExpression

_logger = logging.getLogger(__name__)
_DEFAULT_RETENTION = '10'


class Error(Exception):
    pass


def init(source_url: str,
         dest_url: str,
         source_retention: str=None,
         dest_retention: str=None,
         compress: bool=None):
    """
    :param source_url: Source url string
    :param dest_url: Destination url string
    :param source_retention: Source retention expression string
    :param dest_retention: Destination retention expression string
    :param compress: Compress flag
    """

    source_url = source_url.rstrip(os.path.sep)
    dest_url = dest_url.rstrip(os.path.sep)

    source = SourceLocation(parse.urlsplit(source_url))
    dest = DestinationLocation(parse.urlsplit(dest_url))

    newuuid = uuid.uuid4()

    # Read location configurations
    try:
        src_config = source.read_configuration()
    except subprocess.CalledProcessError:
        src_config = LocationConfiguration(LocationType.Source)
        src_config.uuid = newuuid

    try:
        dst_config = dest.read_configuration()
    except subprocess.CalledProcessError:
        dst_config = LocationConfiguration(LocationType.Destination)
        dst_config.uuid = newuuid

    if not src_config.uuid or not dst_config.uuid:
        raise Error('Update of existing locations requires uuids. This backup job was presumably created'
                    ' with an older version.')

    if src_config.uuid != dst_config.uuid:
        raise Error('Update of existing locations requires consistent location uuids,'
                    ' source [%s] != destination [%s].'
                    % (src_config.uuid, dst_config.uuid))

    # Update configuration parameters with current settings for this backup (both ways)
    both_remote_or_local = not (source.is_remote() ^ dest.is_remote())

    # Initialize/Update location configuration

    # Set source/container/destination depending on remote/local constellation
    src_config.source = None
    src_config.source_container = None
    src_config.destination = None
    dst_config.source = None
    dst_config.source_container = None
    dst_config.destination = None

    if both_remote_or_local:
        src_config.source = source.url.geturl()
        src_config.source_container = source.container_subvolume_relpath
        dst_config.destination = dest.url.geturl()

    if both_remote_or_local or dest.is_remote():
        src_config.destination = dest.url.geturl()

    if both_remote_or_local or source.is_remote():
        dst_config.source = source.url.geturl()
        dst_config.source_container = source.container_subvolume_relpath

    # Override backup settings with parameter values
    if source_retention:
        src_config.retention = source_retention

    if dest_retention:
        dst_config.retention = dest_retention

    if compress:
        src_config.compress = dst_config.compress = compress

    # Set defaults for remaining settings which are still unset
    if not src_config.retention:
        src_config.retention = Configuration.instance().source_retention

    if not dst_config.retention:
        dst_config.retention = Configuration.instance().destination_retention

    if not src_config.compress:
        src_config.compress = False

    if not dst_config.compress:
        dst_config.compress = False

    source.retention = src_config.retention if src_config.retention else RetentionExpression(_DEFAULT_RETENTION)
    dest.retention = dst_config.retention if dst_config.retention else RetentionExpression(_DEFAULT_RETENTION)

    _logger.info(source)
    _logger.info(dest)

    # Prepare environments
    _logger.info('Preparing source and destination environment')
    source.prepare_environment()
    dest.prepare_environment()

    # Writing configurations
    source.write_configuration(src_config)
    dest.write_configuration(dst_config)

    _logger.info('Initialized successfully')


def run(url_str: str):
    """ Performs backup run """

    starting_time = time.monotonic()
    url_str = url_str.rstrip(os.path.sep)
    url = parse.urlsplit(url_str)

    location = Location(url)

    try:
        config = location.read_configuration()
    except subprocess.CalledProcessError:
        raise Error('Could not read configuration [%s]' % location.configuration_filename)

    if config.location_type == LocationType.Source:
        src_config = config

        # The source volume url is parent
        container_relpath = os.path.basename(url.path)
        url = parse.SplitResult(url.scheme,
                                url.netloc,
                                os.path.abspath(os.path.join(url.path, os.path.pardir)),
                                url.query, None)
        source = SourceLocation(url, container_subvolume_relpath=container_relpath)

        if not src_config.destination:
            raise Error('Job cannot run from here, location nas no destination information')

        dest = DestinationLocation(config.destination)
        dst_config = dest.read_configuration()
    else:
        dst_config = config
        dest = DestinationLocation(url)

        if not dst_config.source:
            raise Error('Job cannot run from here, location has no source information')

        source = SourceLocation(config.source, container_subvolume_relpath=dst_config.source_container)
        src_config = source.read_configuration()

    source.retention = RetentionExpression(src_config.retention)
    dest.retention = RetentionExpression(dst_config.retention)

    compress = config.compress

    _logger.info(source)
    _logger.info(dest)

    # Prepare environments
    _logger.info('Preparing environment')
    source.prepare_environment()
    dest.prepare_environment()

    # Retrieve snapshot names of both source and destination
    source.retrieve_snapshot_names()
    dest.retrieve_snapshot_names()

    new_snapshot_name = SnapshotName()
    if len(source.snapshot_names) > 0 \
            and new_snapshot_name.timestamp <= source.snapshot_names[0].timestamp:
        raise Error('Current snapshot name [%s] would be older than newest existing snapshot [%s] \
                             which may indicate a system time problem'
                    % (new_snapshot_name, source.snapshot_names[0]))

    # Create source snapshot
    source.create_snapshot()

    # Transfer temporary snapshot
    _logger.info('Transferring snapshot')
    # btrfs send command/subprocess
    if len(source.snapshot_names) == 0:
        send_command_str = 'btrfs send "%s"' % source.temp_subvolume_path
    else:
        send_command_str = 'btrfs send -p "%s" "%s"' % (
            os.path.join(source.container_subvolume_path, str(source.snapshot_names[0])),
            source.temp_subvolume_path)

    if compress:
        send_command_str += ' | lzop -1'

    send_command = source.create_subprocess_args(send_command_str)
    send_process = subprocess.Popen(send_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    # pv command/subprocess for progress indication
    pv_process = None
    if shell.exists('pv'):
        pv_process = subprocess.Popen(['pv'], stdin=send_process.stdout, stdout=subprocess.PIPE)

    # btrfs receive command/subprocess
    receive_command_str = 'btrfs receive "%s"' % dest.url.path
    if compress:
        receive_command_str = 'lzop -d | ' + receive_command_str

    receive_command = dest.create_subprocess_args(receive_command_str)
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

    # After successful transmission, rename source and destination-side
    # snapshot subvolumes (from pending to timestamp-based name)
    subprocess.check_output(source.create_subprocess_args(
        'mv "%s" "%s"' % (
            source.temp_subvolume_path, os.path.join(source.container_subvolume_path, str(new_snapshot_name)))))
    subprocess.check_output(dest.create_subprocess_args(
        'mv "%s" "%s"' % (dest.temp_subvolume_path, os.path.join(dest.url.path, str(new_snapshot_name)))))

    # Update snapshot name lists
    source.snapshot_names.insert(0, new_snapshot_name)
    dest.snapshot_names.insert(0, new_snapshot_name)

    # Clean out excess backups/snapshots
    source.cleanup_snapshots()
    dest.cleanup_snapshots()

    _logger.info('Backup %s created successfully in %s'
                 % (new_snapshot_name,
                    time.strftime("%H:%M:%S", time.gmtime(time.monotonic() - starting_time))))

