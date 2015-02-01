import logging
import os
import subprocess
import time

from btrfs_sxbackup import shell
from btrfs_sxbackup.configs import LocationConfiguration
from btrfs_sxbackup.locations import Location
from btrfs_sxbackup.locations import SourceLocation
from btrfs_sxbackup.locations import DestinationLocation
from btrfs_sxbackup.entities import SnapshotName
from btrfs_sxbackup.entities import LocationType
from btrfs_sxbackup.retention import KeepExpression

_logger = logging.getLogger(__name__)


class Error(Exception):
    pass


def init(source_url, dest_url, source_keep=None, dest_keep=None, compress=False):
    """  Performs initialization """

    source = SourceLocation(source_url, source_keep)
    dest = DestinationLocation(dest_url, dest_keep)

    _logger.info(source)
    _logger.info(dest)

    # Prepare environments
    _logger.info('Preparing environment')
    source.prepare_environment()
    dest.prepare_environment()

    # Read location configurations
    try:
        src_config = source.read_configuration()
    except subprocess.CalledProcessError:
        src_config = LocationConfiguration(LocationType.Source)

    try:
        dst_config = dest.read_configuration()
    except subprocess.CalledProcessError:
        dst_config = LocationConfiguration(LocationType.Destination)

    # Update configuration parameters with current settings for this backup (both ways)
    both_remote_or_local = not (source.is_remote() ^ dest.is_remote())

    # Update location configuration (in a meaningful way)
    src_config.source = None
    src_config.source_container = None
    src_config.destination = None
    if not source_keep:
        src_config.keep = None
    dst_config.source = None
    dst_config.source_container = None
    dst_config.destination = None
    if not dest_keep:
        dst_config.keep = None

    if both_remote_or_local:
        src_config.source = source.url.geturl()
        src_config.source_container = source.container_subvolume
        dst_config.destination = dest.url.geturl()

    if both_remote_or_local or dest.is_remote():
        src_config.destination = dest.url.geturl()

    if source.keep:
        src_config.keep = source.keep.expression_text

    if both_remote_or_local or source.is_remote():
        dst_config.source = source.url.geturl()
        dst_config.source_container = source.container_subvolume

    if dest.keep:
        dst_config.keep = dest.keep.expression_text

    src_config.compress = dst_config.compress = compress

    source.write_configuration(src_config)
    dest.write_configuration(dst_config)

    _logger.info('Initialized successfully')
    
    
def run(url):
    """ Performs backup run """

    starting_time = time.monotonic()

    location = Location(url)
    try:
        config = location.read_configuration()
    except subprocess.CalledProcessError:
        raise Error('Could not read configuration from [%s]' % url.geturl())

    if config.location_type == LocationType.Source:
        src_config = config
        source = SourceLocation(src_config.source)

        if not src_config.destination:
            raise Error('No destination information. Pull backups cannot be pushed.')
        dest = DestinationLocation(config.destination)

        dst_config = dest.read_configuration()
    else:
        dst_config = config
        dest = DestinationLocation(dst_config.destination)

        if not dst_config.source:
            raise Error('No source information. Push backups cannot be pulled.')
        source = SourceLocation(config.source)
        src_config = source.read_configuration()

    source.keep = KeepExpression(src_config.keep)
    dest.keep = KeepExpression(dst_config.keep)

    compress = dst_config.compress

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
        send_command_str = 'btrfs send "%s"' % source.temp_subvolume
    else:
        send_command_str = 'btrfs send -p "%s" "%s"' % (
            os.path.join(source.container_subvolume, str(source.snapshot_names[0])),
            source.temp_subvolume)

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
            source.temp_subvolume, os.path.join(source.container_subvolume, str(new_snapshot_name)))))
    subprocess.check_output(dest.create_subprocess_args(
        'mv "%s" "%s"' % (dest.temp_subvolume, os.path.join(dest.url.path, str(new_snapshot_name)))))

    # Update snapshot name lists
    source.snapshot_names.insert(0, new_snapshot_name)
    dest.snapshot_names.insert(0, new_snapshot_name)

    # Clean out excess backups/snapshots
    source.cleanup_snapshots()
    dest.cleanup_snapshots()

    _logger.info('Backup %s created successfully in %s'
                       % (new_snapshot_name,
                          time.strftime("%H:%M:%S", time.gmtime(time.monotonic() - starting_time))))

