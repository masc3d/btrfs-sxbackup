import logging
import logging.handlers
import os
import sys
import traceback

from argparse import ArgumentParser
from urllib import parse

from btrfs_sxbackup.Backup import Backup
from btrfs_sxbackup.KeepExpression import KeepExpression
from btrfs_sxbackup import __version__

app_name = 'btrfs-sxbackup'

# Parse arguments
parser = ArgumentParser(prog=app_name)
parser.add_argument('source_subvolume', type=str,
                    help='Source subvolume to backup. Local path or SSH url.')
parser.add_argument('destination_container_subvolume', type=str,
                    help='Destination subvolume receiving snapshots. Local path or SSH url.')
parser.add_argument('-sk', '--source-keep', type=str, default='10',
                    help='Expression defining source snapshots to keep.')
parser.add_argument('-dk', '--destination-keep', type=str, default='10',
                    help='Expression defining destination snapshots to keep.')
parser.add_argument('-ss', '--source-container-subvolume', type=str, default='sxbackup',
                    help='Override path to source snapshot container subvolume. Both absolute and relative paths\
                     are possible. (defaults to \'sxbackup\', relative to source subvolume)')
parser.add_argument('-c', '--compress', action='store_true',
                    help='Enables compression, requires lzop to be installed on both source and destination')
parser.add_argument('-li', '--log-ident', dest='log_ident', type=str, default=app_name,
                    help='Log ident used for syslog logging, defaults to script name')
parser.add_argument('-q', '--quiet', dest='quiet', action='store_true', default=False,
                    help='Do not log to STDOUT')
parser.add_argument('--version', action='version', version='%s v%s' % (app_name, __version__))
args = parser.parse_args()

# Initialize logging
logger = logging.getLogger()
if not args.quiet:
    logger.addHandler(logging.StreamHandler(sys.stdout))
log_syslog_handler = logging.handlers.SysLogHandler('/dev/log')
log_syslog_handler.setFormatter(logging.Formatter(app_name + '[%(process)d] %(message)s'))
log_syslog_handler.ident = args.log_ident+' '
logger.addHandler(log_syslog_handler)
logger.setLevel(logging.INFO)
logger.info('%s v%s' % (app_name, __version__))

try:
    source_url = parse.urlsplit(args.source_subvolume)
    dest_url = parse.urlsplit(args.destination_container_subvolume)
    if args.source_container_subvolume[0] == os.pathsep:
        source_container_subvolume = args.source_container_subvolume
    else:
        source_container_subvolume = os.path.join(source_url.path, args.source_container_subvolume)

    backup = Backup(
        source_url=source_url,
        source_container_subvolume=source_container_subvolume,
        source_keep=KeepExpression(args.source_keep),
        dest_url=dest_url,
        dest_keep=KeepExpression(args.destination_keep))

    backup.compress = args.compress

    # Perform actual backup
    backup.run()
except SystemExit as e:
    if e.code != 0:
        raise
except:
    logger.error('ERROR {0} {1}'.format(sys.exc_info(), traceback.extract_tb(sys.exc_info()[2])))
    raise

exit(0)

