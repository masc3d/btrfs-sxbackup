import logging
import subprocess
import time
from urllib import parse

from btrfs_sxbackup.configs import Configuration
from btrfs_sxbackup.locations import Location
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
    source = Location(parse.urlsplit(source_url), location_type=LocationType.Source)
    dest = Location(parse.urlsplit(dest_url), location_type=LocationType.Destination)

    # Read location configurations
    try:
        source.read_configuration()
    except subprocess.CalledProcessError as e:
        _logger.error(e)

    try:
        dest.read_configuration()
    except subprocess.CalledProcessError as e:
        _logger.error(e)
        dest.uuid = source.uuid

    if not source.uuid or not dest.uuid:
        raise Error('Update of existing locations requires uuids. This backup job was presumably created'
                    ' with an older version.')

    if source.uuid != dest.uuid:
        raise Error('Update of existing locations requires consistent location uuids,'
                    ' source [%s] != destination [%s].'
                    % (source.uuid, dest.uuid))

    if source_retention:
        source.retention = RetentionExpression(source_retention)
    if not source.retention:
        source.retention = Configuration.instance().source_retention
    if not source.retention:
        source.retention = RetentionExpression(_DEFAULT_RETENTION)

    if dest_retention:
        dest.retention = RetentionExpression(dest_retention)
    if not dest.retention:
        dest.retention = Configuration.instance().destination_retention
    if not dest.retention:
        dest.retention = RetentionExpression(_DEFAULT_RETENTION)

    if compress:
        source.compress = dest.compress = compress
    if not source.compress:
        source.compress = False
    if not dest.compress:
        dest.compress = False

    _logger.info(source)
    _logger.info(dest)

    # Prepare environments
    _logger.info('Preparing source and destination environment')
    source.prepare_environment()
    dest.prepare_environment()

    # Writing configurations
    source.write_configuration(dest)
    dest.write_configuration(source)

    _logger.info('Initialized successfully')


def info(url: str):
    location = Location(parse.urlsplit(url))
    location.read_configuration()


def run(url: str):
    """ Performs backup run """

    starting_time = time.monotonic()

    location = Location(parse.urlsplit(url))

    try:
        corresponding_location = location.read_configuration()
    except subprocess.CalledProcessError:
        raise Error('Could not read configuration [%s]' % location.configuration_filename)

    try:
        corresponding_location.read_configuration()
    except subprocess.CalledProcessError:
        raise Error('Could not read configuration [%s]' % corresponding_location.configuration_filename)

    if location.location_type == LocationType.Source:
        source = location
        dest = corresponding_location
    else:
        dest = location
        source = corresponding_location

    if not dest:
        raise Error('Job cannot run from here, location nas no destination information')

    if not source:
        raise Error('Job cannot run from here, location has no source information')

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

    source.transfer_snapshot(str(new_snapshot_name), dest)

    # Update snapshot name lists
    source.snapshot_names.insert(0, new_snapshot_name)
    dest.snapshot_names.insert(0, new_snapshot_name)

    # Clean out excess backups/snapshots
    source.cleanup_snapshots()
    dest.cleanup_snapshots()

    _logger.info('Backup %s created successfully in %s'
                 % (new_snapshot_name,
                    time.strftime("%H:%M:%S", time.gmtime(time.monotonic() - starting_time))))

