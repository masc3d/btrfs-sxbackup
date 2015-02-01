import logging
import logging.handlers
import sys
from subprocess import CalledProcessError
import traceback

from argparse import ArgumentParser
import btrfs_sxbackup.commands
from btrfs_sxbackup.commands import Error
from btrfs_sxbackup.configs import Configuration
from btrfs_sxbackup import mail
from btrfs_sxbackup import __version__

app_name = 'btrfs-sxbackup'

CMD_INIT = 'init'
CMD_RUN = 'run'

# Parse arguments
parser = ArgumentParser(prog=app_name)
parser.add_argument('-q', '--quiet', dest='quiet', action='store_true', default=False,
                    help='Do not log to STDOUT')
parser.add_argument('--trace', dest='trace', action='store_true', default=False, help='Enables trace output')
parser.add_argument('--version', action='version', version='%s v%s' % (app_name, __version__))

subparsers = parser.add_subparsers()
subparsers.required = True
subparsers.dest = 'command'

# Initialize command cmdline params
parser_init = subparsers.add_parser(CMD_INIT, help='initialize backup job')
parser_init.add_argument('source_subvolume', type=str,
                         help='Source subvolume to backup. Local path or SSH url.')
parser_init.add_argument('destination_subvolume', type=str,
                         help='Destination subvolume receiving backup snapshots. Local path or SSH url.')
parser_init.add_argument('-sr', '--source-retention', type=str, default=None,
                         help='Expression defining which source snapshots to retain/cleanup. Can be a static number'
                              ' (of backups) or more complex expression like "1d:4/d, 1w:daily, 2m:none" literally'
                              ' translating to: "1 day from now keep4 backups a day, 1 week from now keep daily backups,'
                              ' 2 months from now keep none". Defaults to global oonfiguration file setting or 10'
                              ' if it doesn''t exist.')
parser_init.add_argument('-dr', '--destination-retention', type=str, default=None,
                         help='Expression defining which destination snapshots to retain/cleanup. Can be a static number'
                              ' (of backups) or more complex expression (see --source-retention argument). Default is 10')
parser_init.add_argument('-c', '--compress', action='store_true',
                         help='Enables compression during transmission. Requires lzop to be installed on both source'
                              ' and destination')

# Run command cmdline params
parser_run = subparsers.add_parser(CMD_RUN, help='run backup job')
parser_run.add_argument('subvolume', type=str,
                        help='Source or destination subvolume. Local path or SSH url.')
parser_run.add_argument('-m', '--mail', type=str, nargs='?', const='',
                        help='Enables email notifications. If an email address is given, it overrides the'
                             ' default email-recipient setting in /etc/btrfs-sxbackup.conf')
parser_run.add_argument('-li', '--log-ident', dest='log_ident', type=str, default=None,
                        help='Log ident used for syslog logging, defaults to script name')

# Initialize logging
args = parser.parse_args()

# Read global configuration
Configuration.instance().read()

logger = logging.getLogger()

if not args.quiet:
    log_std_handler = logging.StreamHandler(sys.stdout)
    log_std_handler.setFormatter(logging.Formatter('%(levelname)s %(message)s'))
    logger.addHandler(log_std_handler)

# Syslog handler
log_syslog_handler = logging.handlers.SysLogHandler('/dev/log')
log_syslog_handler.setFormatter(logging.Formatter(app_name + '[%(process)d] %(levelname)s %(message)s'))
logger.addHandler(log_syslog_handler)
logger.setLevel(logging.INFO)

log_memory_handler = None
email_recipient = None

logger.info('%s v%s' % (app_name, __version__))

try:
    if args.command == CMD_RUN:
        # Log ident support
        if args.log_ident:
            log_ident = args.log_ident if args.log_ident else config.log_ident
            if log_ident:
                log_syslog_handler.ident = log_ident + ' '

        # Mail notification support
        if args.mail is not None:
            email_recipient = args.mail if len(args.mail) > 0 else config.email_recipient

            # Memory handler will buffer output for sending via mail later if needed
            log_memory_handler = logging.handlers.MemoryHandler(capacity=-1)
            log_memory_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
            logger.addHandler(log_memory_handler)

        btrfs_sxbackup.commands.run(args.subvolume)

    elif args.command == CMD_INIT:

        btrfs_sxbackup.commands.init(
            source_url=args.source_subvolume,
            source_retention=args.source_retention,
            dest_url=args.destination_subvolume,
            dest_retention=args.destination_retention,
            compress=args.compress)

except SystemExit as e:
    if e.code != 0:
        raise

except BaseException as e:
    # Log exception message
    e_msg = str(e)
    if len(e_msg) > 0:
        logger.error('%s' % e)

    if isinstance(e, CalledProcessError):
        logger.error('%s' % e.output.decode().strip())

    if args.trace:
        # Log stack trace
        logger.error(traceback.format_exc())

    # Email notification
    if email_recipient:
        # Format message and send
        msg = '\n'.join(map(lambda log_record: log_memory_handler.formatter.format(log_record),
                            log_memory_handler.buffer))
        mail.send(email_recipient, '%s FAILED' % app_name, msg)
    exit(1)

exit(0)

