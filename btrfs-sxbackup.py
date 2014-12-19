#!/usr/bin/python3

__version__ = '0.3.0'
__author__ = 'Marco Schindler, Bernd Michael Helm'
__email__ = 'masc@disappear.de'
__maintainer__ = 'masc@disappear.de'
__license__ = 'GPL'
__copyright__ = 'Copyright 2014, Marco Schindler'

import datetime
import configparser
import io
import os
import logging
import logging.handlers
import sys
import subprocess
import urllib
import time
import traceback

from argparse import ArgumentParser
from configparser import ConfigParser
from datetime import datetime
from urllib import parse

class SxBackup:
    ''' Backup '''

    CONFIG_FILENAME = '/etc/btrfs-sxbackup.conf'

    class Error(Exception):
        pass

    class Configuration:
        def __init__(self, config_type):
            self.config_type = config_type
            self.source = None
            self.source_container = None
            self.destination = None
            self.keep = '1w > 2/d, 2w > daily, 1m > weekly, 2m > none'

        def read(self, fileobject):
            cparser = ConfigParser()
            cparser.read_file(fileobject)

            section = self.config_type
            self.source = cparser.get(section, 'source', fallback=None)
            self.source_container = cparser.get(section, 'source-container', fallback=None)
            self.destination = cparser.get(section, 'destination', fallback=None)
            self.keep = cparser.get(section, 'keep', fallback=self.keep)

        def write(self, fileobject):
            cparser = ConfigParser()

            section = self.config_type
            cparser.add_section(section)
            if self.source is not None:
                cparser.set(section, 'source', self.source)
            if self.source_container is not None:
                cparser.set(section, 'source-container', self.source_container)
            if self.destination is not None:
                cparser.set(section, 'destination', self.destination)
            if self.keep is not None:
                cparser.set(section, 'keep', self.keep)
            cparser.write(fileobject)

    class Location:
        TEMP_BACKUP_NAME = 'temp'
        ''' Backup location '''
        def __init__(self, url, container_subvolume, max_snapshots):
            self.__logger = logging.getLogger(self.__class__.__name__)
            self.url = url
            self.container_subvolume = os.path.join(url.path, container_subvolume)
            self.max_snapshots = max_snapshots
            self.snapshot_names = []
            self.configuration_filename = os.path.join(self.container_subvolume, '.btrfs-sxbackup')

            # Path of subvolume for current backup run
            # Subvolumes will be renamed from temp to timestamp based name on both side if successful.
            self.temp_subvolume = os.path.join(self.container_subvolume, self.TEMP_BACKUP_NAME)

            # Override configuration params
            self.configuration = SxBackup.Configuration(self.get_config_type())

        def get_config_type(self):
            ''' Returns the configuration type, used as section name in configuration file '''
            return ''

        def __format_log_msg(self, msg):
            return '%s :: %s' % (self.get_config_type(), msg)

        def log_info(self, msg):
            self.__logger.info(self.__format_log_msg(msg))

        def log_debug(self, msg):
            self.__logger.debug(self.__format_log_msg(msg))

        def is_remote(self):
            return self.url.hostname is not None

        def create_subprocess_args(self, cmd):
            ''' Create command/args array for subprocess, wraps command into ssh call if url host name is not None '''
            # in case cmd is a regular value, convert to list
            cmd = cmd if cmd is list else [cmd]
            # wrap into bash or ssh command respectively, depending if command is executed locally (host==None) or remotely
            subprocess_args = ['bash', '-c'] + cmd if self.url.hostname is None else \
                ['ssh', '-o', 'ServerAliveInterval=5', '-o', 'ServerAliveCountMax=3', '%s@%s'
                 % (self.url.username, self.url.hostname)] + cmd
            self.log_debug(subprocess_args)
            return subprocess_args
                
        def create_cleanup_bash_command(self, snapshot_names):
            ''' Creates bash comand string to remove multiple snapshots within a btrfs subvolume '''

            return " && ".join(map(lambda x: 'btrfs sub del %s' % (os.path.join(self.container_subvolume, x)), snapshot_names))

        def prepare_environment(self):
            ''' Prepare location environment '''

            # Check and remove temporary snapshot volume (possible leftover of previously interrupted backup)
            subprocess.check_output(self.create_subprocess_args(
                'if [ -d %s ] ; then btrfs sub del %s; fi' % (self.temp_subvolume, self.temp_subvolume)))

        def retrieve_snapshot_names(self):
            ''' Determine snapshot names. Snapshot names are sorted in reverse order (newest first).
            stored internally (self.snapshot_names) and also returned. '''

            self.log_info('Retrieving snapshot names')
            output = subprocess.check_output(self.create_subprocess_args('btrfs sub list -o %s' % (self.container_subvolume)))
            # output is delivered as a byte sequence, decode to unicode string and split lines
            lines = output.decode().splitlines()
            # extract snapshot names from btrfs sub list lines
            def strip_name(l):
                i = l.rfind(os.path.sep)
                return l[i+1:] if i >= 0 else l
            lines = map(lambda x: strip_name(x), lines)
            # sort and return
            self.snapshot_names = sorted(lines, reverse=True)
            return self.snapshot_names

        def cleanup_snapshots(self):
            ''' Clean out excess backups/snapshots '''

            if len(self.snapshot_names) > self.max_snapshots:
                remove_count = len(self.snapshot_names) - self.max_snapshots
                snapshots_to_remove = self.snapshot_names[-remove_count:]
                # self.log_info('Removing snapshots [%s]' % (", ".join(snapshots_to_remove)))
                self.log_info('Removing %d of %d snapshots (because >%d): %s'
                              % (remove_count, len(self.snapshot_names), self.max_snapshots, snapshots_to_remove))
                subprocess.check_output(self.create_subprocess_args(self.create_cleanup_bash_command(snapshots_to_remove)))

        def write_configuration(self):
            ''' Write configuration file to container subvolume '''
            # Configuration to string
            str_file = io.StringIO()
            self.configuration.write(str_file)
            config_str = str_file.getvalue() 
            # Write config file to location directory
            p = subprocess.Popen(self.create_subprocess_args('cat > %s' % (self.configuration_filename)), stdin=subprocess.PIPE)
            p.communicate(input=bytes(config_str, 'utf-8'))

        def read_configuration(self):
            ''' Read configuration file from container subvolume '''
            # Read via cat, ignore errors in case file does not exist
            p = subprocess.Popen(self.create_subprocess_args('cat %s' % (self.configuration_filename)), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            (out, err) = p.communicate()
            # Parse config
            self.configuration.read(out.decode().splitlines())

        def __str__(self):
            return self.__format_log_msg('Url [%s] snapshot container subvolume [%s]'
                                         % (self.url.geturl(), self.container_subvolume))

    class SourceLocation(Location):
        ''' Source location '''

        def get_config_type(self):
            return 'Source'

        def prepare_environment(self):
            ''' Prepares source environment '''
            # Source specific preparation, check and create source snapshot volume if required
            subprocess.check_output(self.create_subprocess_args(
                'if [ ! -d %s ] ; then btrfs sub create %s; fi' % (self.container_subvolume, self.container_subvolume)))

            # Generic location preparation
            super().prepare_environment()

        def create_snapshot(self):
            ''' Creates a new (temporary) snapshot within container subvolume '''
            # Create new temporary snapshot (source)
            self.log_info('Creating snapshot')
            subprocess.check_output(self.create_subprocess_args(
                'btrfs sub snap -r %s %s && sync' % (self.url.path, self.temp_subvolume)))

    class DestinationLocation(Location):
        def get_config_type(self):
            return 'Destination'

    def __init__(self, source_url, source_container_subvolume, source_max_snapshots, dest_url, dest_max_snapshots):
        ''' c'tor '''
        self.__logger = logging.getLogger(self.__class__.__name__)

        self.source = SxBackup.SourceLocation(source_url, source_container_subvolume, source_max_snapshots)
        self.dest = SxBackup.DestinationLocation(dest_url, "", dest_max_snapshots)

        self.compress = False

    def __create_snapshot_name(self):
        ''' Create formatted snapshot name '''
        return datetime.utcnow().strftime('sx-%Y%m%d-%H%M%S-utc')

    def __does_command_exist(self, url, command):
        ''' Verifies existence of a shell command '''
        type_cmd = ['type ' + command]
        if url is not None:
            type_cmd = self.__create_subprocess_args(url, type_cmd)

        type_prc = subprocess.Popen(type_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
        return type_prc.wait() == 0

    def run(self):
        ''' Performs backup run '''

        self.__logger.info(self.source)
        self.__logger.info(self.dest)

        starting_time = time.monotonic()
        # Read global configuration
        config = SxBackup.Configuration('Global')
        if os.path.exists(SxBackup.CONFIG_FILENAME):
            config.read(open(SxBackup.CONFIG_FILENAME))

        # Prepare environments
        self.__logger.info('Preparing environment')
        self.source.prepare_environment()
        self.dest.prepare_environment()

        # Read location configurations
        self.source.read_configuration()
        self.dest.read_configuration()

        # Update configuration parameters with current settings for this backup (both ways)
        both_remote_or_local = not (self.source.is_remote() ^ self.dest.is_remote())
        self.source.configuration.source = self.source.url.geturl() if both_remote_or_local else None
        self.source.configuration.source_container = self.source.container_subvolume if both_remote_or_local else None
        self.source.configuration.destination = self.dest.url.geturl() if self.dest.is_remote() or both_remote_or_local else None

        self.dest.configuration.source = self.source.url.geturl() if self.source.is_remote() or both_remote_or_local else None
        self.dest.configuration.source_container = self.source.container_subvolume if self.source.is_remote() or both_remote_or_local else None
        self.dest.configuration.destination = self.dest.url.geturl() if both_remote_or_local else None

        # Retrieve snapshot names of both source and destination 
        self.source.retrieve_snapshot_names()
        self.dest.retrieve_snapshot_names()

        new_snapshot_name = self.__create_snapshot_name()
        if len(self.source.snapshot_names) > 0 and new_snapshot_name <= self.source.snapshot_names[0]:
            raise SxBackup.Error('Current snapshot name [%s] would be older than newest existing snapshot [%s] \
                                 which may indicate a system time problem'
                                 % (new_snapshot_name, self.source.snapshot_names[0]))

        # Create source snapshot
        self.source.create_snapshot()

        # Transfer temporary snapshot
        self.__logger.info('Sending snapshot')

        # btrfs send command/subprocess
        if len(self.source.snapshot_names) == 0:
            send_command_str = 'btrfs send %s' % (self.source.temp_subvolume)
        else:
            send_command_str = 'btrfs send -p %s %s' % (os.path.join(self.source.container_subvolume, self.source.snapshot_names[0]), self.source.temp_subvolume)
       
        if self.compress:
            send_command_str += ' | lzop -1'

        send_command = self.source.create_subprocess_args(send_command_str)
        send_process = subprocess.Popen(send_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        # pv command/subprocess for progress indication
        pv_process = None 
        if self.__does_command_exist(None, 'pv'):
            pv_process = subprocess.Popen(['pv'], stdin=send_process.stdout, stdout=subprocess.PIPE)

        # btrfs receive command/subprocess
        receive_command_str = 'btrfs receive %s' % (self.dest.url.path)
        if self.compress:
            receive_command_str = 'lzop -d | ' + receive_command_str

        receive_command = self.dest.create_subprocess_args(receive_command_str)
        receive_process = subprocess.Popen(receive_command, stdin=pv_process.stdout if pv_process is not None else send_process.stdout, stdout=subprocess.PIPE)

        receive_returncode = None
        send_returncode = None
        while receive_returncode is None or send_returncode is None:
            receive_returncode = receive_process.poll()
            send_returncode = send_process.poll()

            if receive_returncode is not None and receive_returncode != 0:
                send_process.kill()
                break

            if send_returncode is not None and send_returncode != 0:
                receive_process.kill()
                break

            time.sleep(2)

        # wait for commands to complete
        send_returncode = send_process.wait()
        receive_returncode = receive_process.wait()

        if send_returncode != 0:
            raise subprocess.CalledProcessError(send_returncode, send_command, None)
        if receive_returncode != 0:
            raise subprocess.CalledProcessError(receive_returncode, receive_command, None)

        # After successful transmission, rename source and destinationside snapshot subvolumes (from pending to timestamp-based name)
        self.__logger.info('Finalizing backup')
        subprocess.check_output(self.source.create_subprocess_args(
            'mv %s %s' % (self.source.temp_subvolume, os.path.join(self.source.container_subvolume, new_snapshot_name))))
        subprocess.check_output(self.dest.create_subprocess_args(
            'mv %s %s' % (self.dest.temp_subvolume, os.path.join(self.dest.url.path, new_snapshot_name))))

        # Update snapshot name lists
        self.source.snapshot_names = [new_snapshot_name] + self.source.snapshot_names
        self.dest.snapshot_names = [new_snapshot_name] + self.dest.snapshot_names

        # Clean out excess backups/snapshots
        self.source.cleanup_snapshots()
        self.dest.cleanup_snapshots()

        self.source.write_configuration()
        self.dest.write_configuration()

        self.__logger.info('Backup %s created successfully in %s'
                           % (new_snapshot_name, time.strftime("%H:%M:%S", time.gmtime(time.monotonic()-starting_time))))

    def __str__(self):
        return 'Source %s \nDestination %s' % \
            (self.source, self.dest)


app_name = os.path.splitext(os.path.basename(__file__))[0]

# Parse arguments
parser = ArgumentParser()
parser.add_argument('source_subvolume', type=str,
                    help='Source subvolume to backup. Local path or SSH url.')
parser.add_argument('destination_container_subvolume', type=str,
                    help='Destination subvolume receiving snapshots. Local path or SSH url.')
parser.add_argument('-sm', '--source-max-snapshots', type=int, default=10,
                    help='Maximum number of source snapshots to keep (defaults to 10).')
parser.add_argument('-dm', '--destination-max-snapshots', type=int, default=10,
                    help='Maximum number of destination snapshots to keep (defaults to 10).')
parser.add_argument('-ss', '--source-container-subvolume', type=str, default='sxbackup',
                    help='Override path to source snapshot container subvolume. Both absolute and relative paths\
                     are possible. (defaults to \'sxbackup\', relative to source subvolume)')
parser.add_argument('-c', '--compress', action='store_true',
                    help='Enables compression, requires lzop to be installed on both source and destination')
parser.add_argument('-si', '--syslog-ident', dest='syslog_ident', type=str, default=app_name,
                    help='Set Syslog ident, default to script name')
parser.add_argument('-q', '--quiet', dest='quiet', action='store_true', default=False,
                    help='Do not log to STDOUT')
args = parser.parse_args()

# Initialize logging
logger = logging.getLogger()
if not args.quiet:
    logger.addHandler(logging.StreamHandler(sys.stdout))
log_syslog_handler = logging.handlers.SysLogHandler('/dev/log')
log_syslog_handler.setFormatter(logging.Formatter(app_name + '[%(process)d] %(message)s'))
log_syslog_handler.ident = args.syslog_ident+' '
logger.addHandler(log_syslog_handler)
logger.setLevel(logging.INFO)
logger.info('%s v%s by %s' % (app_name, __version__, __author__))

try:
    source_url = parse.urlsplit(args.source_subvolume)
    dest_url = parse.urlsplit(args.destination_container_subvolume)
    if args.source_container_subvolume[0] == os.pathsep:
        source_container_subvolume = args.source_container_subvolume
    else:
        source_container_subvolume = os.path.join(source_url.path, args.source_container_subvolume)

    sxbackup = SxBackup(
        source_url=source_url,
        source_container_subvolume=source_container_subvolume,
        source_max_snapshots=args.source_max_snapshots,
        dest_url=dest_url,
        dest_max_snapshots=args.destination_max_snapshots)

    sxbackup.compress = args.compress

    # Perform actual backup
    sxbackup.run()
except SystemExit as e:
    if e.code != 0:
        raise
except:
    logger.error('ERROR {0} {1}'.format(sys.exc_info(), traceback.extract_tb(sys.exc_info()[2])))
    raise

exit(0)