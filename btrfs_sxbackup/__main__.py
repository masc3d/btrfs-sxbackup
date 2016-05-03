# Copyright (c) 2014 Marco Schindler
#
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the Free
# Software Foundation; either version 2 of the License, or (at your option)
# any later version.

import logging
import logging.handlers
import sys
import traceback
import urllib.parse
from argparse import ArgumentParser
from subprocess import CalledProcessError

from btrfs_sxbackup.core import Location
from btrfs_sxbackup.core import Job
from btrfs_sxbackup.core import Configuration
from btrfs_sxbackup.retention import RetentionExpression
from btrfs_sxbackup import mail
from btrfs_sxbackup import __version__

_APP_NAME = 'btrfs-sxbackup'

_CMD_INIT = 'init'
_CMD_UPDATE = 'update'
_CMD_RUN = 'run'
_CMD_INFO = 'info'
_CMD_PURGE = 'purge'
_CMD_DESTROY = 'destroy'
_CMD_TRANSFER = 'transfer'
_CMD_FILES = 'files'
_CMD_FILES_NEW = 'new'


def main():
    # Parse arguments
    parser = ArgumentParser(prog=_APP_NAME)
    parser.add_argument('-q', '--quiet', dest='quiet', action='store_true', default=False,
                        help='do not log to stdout')
    parser.add_argument('--version', action='version', version='%s v%s' % (_APP_NAME, __version__))
    parser.add_argument('-v', dest='verbosity', action='count',
                        help='can be specified multiple times to increase verbosity')

    subparsers = parser.add_subparsers()
    subparsers.required = True
    subparsers.dest = 'command'

    # Reusable options
    compress_args = ['-c', '--compress']
    compress_kwargs = {'action': 'store_true',
                       'help': 'enables compression during transmission. Requires lzop to be installed on both source'
                               ' and destination',
                       'default': None}

    source_retention_args = ['-sr', '--source-retention']
    source_retention_kwargs = {'type': str,
                               'default': None,
                               'help': 'expression defining which source snapshots to retain/cleanup.'
                                       ' can be a static number (of backups) or more complex expression like'
                                       ' "1d:4/d, 1w:daily, 2m:none" literally translating to: "1 day from now keep'
                                       ' 4 backups a day, 1 week from now keep daily backups,'
                                       ' 2 months from now keep none"'}

    destination_retention_args = ['-dr', '--destination-retention']
    destination_retention_kwargs = {'type': str,
                                    'default': None,
                                    'help': 'expression defining which destination snapshots to retain/cleanup.'
                                            ' can be a static number (of backups) or more complex'
                                            ' expression (see --source-retention argument)'}

    subvolumes_args = ['subvolumes']
    subvolumes_kwargs = {'type': str,
                         'nargs': '+',
                         'metavar': 'subvolume',
                         'help': 'backup job source or destination subvolume. local path or SSH url'}

    # Initialize command cmdline params
    p_init = subparsers.add_parser(_CMD_INIT, help='initialize backup job')
    p_init.add_argument('source_subvolume', type=str, metavar='source-subvolume',
                        help='source subvolume tobackup. local path or ssh url')
    p_init.add_argument('destination_subvolume', type=str, metavar='destination-subvolume', nargs='?', default=None,
                        help='optional destination subvolume receiving backup snapshots. local path or ssh url')
    p_init.add_argument(*source_retention_args, **source_retention_kwargs)
    p_init.add_argument(*destination_retention_args, **destination_retention_kwargs)
    p_init.add_argument(*compress_args, **compress_kwargs)

    p_destroy = subparsers.add_parser(_CMD_DESTROY, help='destroy backup job by removing configuration files from source'
                                                         ' and destination. backup snapshots will be kept on both sides'
                                                         ' by default.')
    p_destroy.add_argument(*subvolumes_args, **subvolumes_kwargs)
    p_destroy.add_argument('--purge', action='store_true', help='removes all backup snapshots from source and destination')

    # Update command cmdline params
    p_update = subparsers.add_parser(_CMD_UPDATE, help='update backup job')
    p_update.add_argument(*subvolumes_args, **subvolumes_kwargs)
    p_update.add_argument(*source_retention_args, **source_retention_kwargs)
    p_update.add_argument(*destination_retention_args, **destination_retention_kwargs)
    p_update.add_argument(*compress_args, **compress_kwargs)
    p_update.add_argument('-nc', '--no-compress', action='store_true', help='disable compression during transmission')

    # Run command cmdline params
    p_run = subparsers.add_parser(_CMD_RUN, help='run backup job')
    p_run.add_argument(*subvolumes_args, **subvolumes_kwargs)
    p_run.add_argument('-m', '--mail', type=str, nargs='?', const='',
                       help='enables email notifications. If an email address is given, it overrides the'
                            ' default email-recipient setting in /etc/btrfs-sxbackup.conf')
    p_run.add_argument('-li', '--log-ident', dest='log_ident', type=str, default=None,
                       help='log ident used for syslog logging, defaults to script name')

    # Info command cmdline params
    p_info = subparsers.add_parser(_CMD_INFO, help='backup job info')
    p_info.add_argument(*subvolumes_args, **subvolumes_kwargs)

    # Purge command cmdline params
    p_purge = subparsers.add_parser(_CMD_PURGE, help="purge backups according to retention expressions")
    p_purge.add_argument(*subvolumes_args, **subvolumes_kwargs)
    purge_source_retention_kwargs = source_retention_kwargs.copy()
    purge_destination_retention_kwargs = destination_retention_kwargs.copy()
    purge_source_retention_kwargs['help'] = 'Optionally override %s' % purge_source_retention_kwargs['help']
    purge_destination_retention_kwargs['help'] = 'Optionally override %s' % purge_destination_retention_kwargs['help']
    p_purge.add_argument(*source_retention_args, **purge_source_retention_kwargs)
    p_purge.add_argument(*destination_retention_args, **purge_destination_retention_kwargs)

    # Transfer
    p_transfer = subparsers.add_parser(_CMD_TRANSFER, help='transfer snapshot')
    p_transfer.add_argument('source_subvolume', type=str, metavar='source-subvolume',
                            help='source subvolume to transfer. local path or ssh url')
    p_transfer.add_argument('destination_subvolume', type=str, metavar='destination-subvolume',
                            help='destination subvolume. local path or ssh url')
    p_transfer.add_argument(*compress_args, **compress_kwargs)

    # Initialize logging
    args = parser.parse_args()

    # Read global configuration
    Configuration.instance().read()

    logger = logging.getLogger()

    if not args.quiet:
        log_std_handler = logging.StreamHandler(sys.stdout)
        log_std_handler.setFormatter(logging.Formatter('%(levelname)s %(message)s'))
        logger.addHandler(log_std_handler)

    log_memory_handler = None
    log_trace = False
    email_recipient = None

    def handle_exception(ex: Exception):
        """
        Exception handler
        :param ex:
        :return:
        """

        # Log exception message
        if len(str(ex)) > 0:
            logger.error('%s' % str(ex))

        if isinstance(ex, CalledProcessError):
            if ex.output:
                output = ex.output.decode().strip()
                if len(output) > 0:
                    logger.error('%s' % output)

        if log_trace:
            # Log stack trace
            logger.error(traceback.format_exc())

        # Email notification
        if email_recipient:
            try:
                # Format message and send
                msg = '\n'.join(map(lambda log_record: log_memory_handler.formatter.format(log_record),
                                    log_memory_handler.buffer))
                mail.send(email_recipient, '%s FAILED' % _APP_NAME, msg)
            except Exception as ex:
                logger.error(str(ex))

    # Syslog handler
    if args.command == _CMD_RUN:
        log_syslog_handler = logging.handlers.SysLogHandler('/dev/log')
        log_syslog_handler.setFormatter(logging.Formatter(_APP_NAME + '[%(process)d] %(levelname)s %(message)s'))
        logger.addHandler(log_syslog_handler)

        # Log ident support
        if args.log_ident:
            log_ident = args.log_ident if args.log_ident else Configuration.instance().log_ident
            if log_ident:
                log_syslog_handler.ident = log_ident + ' '

        # Mail notification support
        if args.mail is not None:
            email_recipient = args.mail if len(args.mail) > 0 else Configuration.instance().email_recipient

            # Memory handler will buffer output for sending via mail later if needed
            log_memory_handler = logging.handlers.MemoryHandler(capacity=-1)
            log_memory_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
            logger.addHandler(log_memory_handler)

    if args.verbosity and args.verbosity >= 1:
        logger.setLevel(logging.DEBUG)
        log_trace = True
    else:
        logger.setLevel(logging.INFO)
    logger.info('%s v%s' % (_APP_NAME, __version__))

    exitcode = 0

    try:
        if args.command == _CMD_RUN:
            for subvolume in args.subvolumes:
                try:
                    job = Job.load(urllib.parse.urlsplit(subvolume))
                    job.run()
                except Exception as e:
                    handle_exception(e)
                    exitcode = 1

        elif args.command == _CMD_INIT:
            source_retention = RetentionExpression(args.source_retention) if args.source_retention else None
            destination_retention = RetentionExpression(args.destination_retention) if args.destination_retention else None
            job = Job.init(source_url=urllib.parse.urlsplit(args.source_subvolume),
                           source_retention=source_retention,
                           dest_url=urllib.parse.urlsplit(args.destination_subvolume) if args.destination_subvolume
                           else None,
                           dest_retention=destination_retention,
                           compress=args.compress)

        elif args.command == _CMD_UPDATE:
            source_retention = RetentionExpression(args.source_retention) if args.source_retention else None
            dest_retention = RetentionExpression(args.destination_retention) if args.destination_retention else None
            for subvolume in args.subvolumes:
                try:
                    job = Job.load(urllib.parse.urlsplit(subvolume))
                    job.update(source_retention=source_retention,
                               dest_retention=dest_retention,
                               compress=args.compress if args.compress else
                               not args.no_compress if args.no_compress else
                               None)
                except Exception as e:
                    handle_exception(e)
                    exitcode = 1

        elif args.command == _CMD_DESTROY:
            for subvolume in args.subvolumes:
                try:
                    job = Job.load(urllib.parse.urlsplit(subvolume))
                    job.destroy(purge=args.purge)
                except Exception as e:
                    handle_exception(e)
                    exitcode = 1

        elif args.command == _CMD_INFO:
            for subvolume in args.subvolumes:
                try:
                    job = Job.load(urllib.parse.urlsplit(subvolume), raise_errors=False)
                    job.print_info()
                except Exception as e:
                    handle_exception(e)
                    exitcode = 1

        elif args.command == _CMD_PURGE:
            source_retention = RetentionExpression(args.source_retention) if args.source_retention else None
            dest_retention = RetentionExpression(args.destination_retention) if args.destination_retention else None
            for subvolume in args.subvolumes:
                try:
                    job = Job.load(urllib.parse.urlsplit(subvolume))
                    job.purge(source_retention=source_retention, dest_retention=dest_retention)
                except Exception as e:
                    handle_exception(e)
                    exitcode = 1

        elif args.command == _CMD_TRANSFER:
            source = Location(urllib.parse.urlsplit(args.source_subvolume))
            destination = Location(urllib.parse.urlsplit(args.destination_subvolume))
            source.transfer_btrfs_snapshot(destination, compress=args.compress)

    except SystemExit as e:
        if e.code != 0:
            raise

    except KeyboardInterrupt as k:
        exitcode = 1

    except Exception as e:
        handle_exception(e)
        exitcode = 1

    exit(exitcode)

main()

