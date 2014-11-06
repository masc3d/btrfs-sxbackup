#!/usr/bin/python3

__version__ = '0.2.5'
__author__ = 'masc'
__email__ = 'masc@disappear.de'
__maintainer__ = 'masc@disappear.de'
__license__ = 'GPL'
__copyright__ = 'Copyright 2014, Marco Schindler'

import datetime
import os
import logging
import sys
import subprocess
import urllib
import time

from logging import StreamHandler
from argparse import ArgumentParser
from datetime import datetime
from urllib import parse

class SxBackup:
    TEMP_BACKUP_NAME = 'temp'

    def __init__(self, source_url, source_snapshot_subvolume, source_max_snapshots, dest_url, dest_max_snapshots):
        ''' c'tor '''
        self.__logger = logging.getLogger(self.__class__.__name__)

        self.source_url = source_url
        self.source_snapshot_subvolume = source_snapshot_subvolume
        self.source_max_snapshots = source_max_snapshots
        self.dest_url = dest_url
        self.dest_max_snapshots = dest_max_snapshots

    def __create_subprocess_args(self, url, cmd):
        ''' Create command/args array for subprocess, wraps command into ssh call if url host name is not None '''
        # in case cmd is a regular value, convert to list
        cmd = cmd if cmd is list else [cmd]
        # wrap into bash or ssh command respectively, depending if command is executed locally (host==None) or remotely
        return ['bash', '-c'] + cmd if url.hostname == None else ['ssh', '-o', 'ServerAliveInterval=5', '-o', 'ServerAliveCountMax=3', '%s@%s' % (url.username, url.hostname)] + cmd

    def __create_snapshot_name(self):
        ''' Create formatted snapshot name '''
        return datetime.utcnow().strftime('%Y%m%d-%H%M%S-UTC')

    def __create_cleanup_bash_command(self, snapshot_subvolume, snapshot_names):
        ''' Creates bash comand string to remove multiple snapshots within a btrfs subvolume '''
        return " && ".join(map(lambda x: 'btrfs sub del %s' % (os.path.join(snapshot_subvolume, x)), snapshot_names))

    def __retrieve_snapshot_names(self, url, snapshot_subvolume):
        ''' Determine snapshot names. Snapshot names returned are sorted in reverse order (newest first) '''

        self.__logger.info('Retrieving snapshot names from [%s] [%s]' % (url.geturl(), snapshot_subvolume))
        output = subprocess.check_output(self.__create_subprocess_args(url, 'ls -1 %s' % (snapshot_subvolume)))
        # output is delivered as a byte sequence, decode to unicode string and split lines
        lines = output.decode().splitlines()
        return sorted(lines, reverse=True)

    def __snapshots_to_remove(self, snapshot_names, max_count):
        ''' Determine snapshots to remove from a list of snapshot names, given maximum count.
        Returns a trimmed list of snapshots '''

        remove_count = len(snapshot_names) - max_count
        return snapshot_names[-remove_count:]

    def run(self):
        ''' Performs backup run '''

        self.__logger.info('Preparing source and destination environment')
        # Check for and create source snapshot volume if required
        subprocess.check_output(self.__create_subprocess_args(self.source_url, \
            'if [ ! -d %s ] ; then btrfs sub create %s; fi' % (self.source_snapshot_subvolume, self.source_snapshot_subvolume)))

        # Paths for subvolumes of current backup run (called pending on both sides)
        # Subvolumes will be renmed to timestamp based name on both side if successful.
        source_temp_subvolume = os.path.join(self.source_snapshot_subvolume, self.TEMP_BACKUP_NAME)
        dest_temp_subvolume = os.path.join(self.dest_url.path, self.TEMP_BACKUP_NAME)

        # Check and remove temporary snapshot volume (possible leftover of previously interrupted backup)
        subprocess.check_output(self.__create_subprocess_args(self.source_url, \
            'if [ -d %s ] ; then btrfs sub del %s; fi' % (source_temp_subvolume, source_temp_subvolume)))

        subprocess.check_output(self.__create_subprocess_args(self.dest_url, \
            'if [ -d %s ] ; then btrfs sub del %s; fi' % (dest_temp_subvolume, dest_temp_subvolume)))

        # Retrieve source snapshots and print
        source_snapshot_names = self.__retrieve_snapshot_names(self.source_url, self.source_snapshot_subvolume)
        dest_snapshot_names = self.__retrieve_snapshot_names(self.dest_url, self.dest_url.path)

        new_snapshot_name = self.__create_snapshot_name()

        # Create new temporary snapshot (source)
        self.__logger.info('Creating source snapshot')
        subprocess.check_output(self.__create_subprocess_args(self.source_url, \
            'btrfs sub snap -r %s %s && sync' % (self.source_url.path, source_temp_subvolume)))

        # Transfer pending snapshot
        self.__logger.info('Sending snapshot')

        # btrfs send command/subprocess
        send_command = ''
        if len(source_snapshot_names) == 0:
            send_command = self.__create_subprocess_args(self.source_url, \
                'btrfs send %s' % (source_temp_subvolume))
        else:
            send_command = self.__create_subprocess_args(self.source_url, \
                'btrfs send -p %s %s' % (os.path.join(self.source_snapshot_subvolume, source_snapshot_names[0]), source_temp_subvolume))
        send_process = subprocess.Popen(send_command, stdout=subprocess.PIPE)

        # pv command/subprocess for progress indication
        pv_command = ['pv']
        pv_process = subprocess.Popen(pv_command, stdin=send_process.stdout, stdout=subprocess.PIPE)

        # btrfs receive command/subprocess
        receive_command = self.__create_subprocess_args(self.dest_url, \
            'btrfs receive %s' % (self.dest_url.path))
        receive_process = subprocess.Popen(receive_command, stdin=pv_process.stdout)

        # wait for commands to complete
        send_returncode = send_process.wait()
        receive_returncode = receive_process.wait()

        if send_returncode != 0:
            raise subprocess.CalledProcessError(send_returncode, send_command, None)
        if receive_returncode != 0:
            raise subprocess.CalledProcessError(receive_returncode, receive_command, None)

        # After successful transmission, rename source and destinationside snapshot subvolumes (from pending to timestamp-based name)
        self.__logger.info('Finalizing backup')
        subprocess.check_output(self.__create_subprocess_args(self.source_url, \
            'mv %s %s' % (source_temp_subvolume, os.path.join(self.source_snapshot_subvolume, new_snapshot_name))))
        subprocess.check_output(self.__create_subprocess_args(self.dest_url, \
            'mv %s %s' % (dest_temp_subvolume, os.path.join(self.dest_url.path, new_snapshot_name))))

        # Update snapshot name lists
        source_snapshot_names = [new_snapshot_name] + source_snapshot_names
        dest_snapshot_names = [new_snapshot_name] + dest_snapshot_names

        # Clean out excess backups/snapshots
        if len(source_snapshot_names) >= self.source_max_snapshots:
            snapshots_to_remove = self.__snapshots_to_remove(source_snapshot_names, self.source_max_snapshots)
            self.__logger.info('Removing source snapshots [%s]' % (", ".join(snapshots_to_remove)))

            command = self.__create_cleanup_bash_command(self.source_snapshot_subvolume, snapshots_to_remove)
            subprocess.check_output(self.__create_subprocess_args(self.source_url, command))

        if len(dest_snapshot_names) >= self.dest_max_snapshots:
            snapshots_to_remove = self.__snapshots_to_remove(dest_snapshot_names, self.dest_max_snapshots)
            self.__logger.info('Removing destination snapshots [%s]' % (", ".join(snapshots_to_remove)))

            command = self.__create_cleanup_bash_command(self.dest_snapshot_subvolume, snapshots_to_remove)
            subprocess.check_output(self.__create_subprocess_args(self.dest_url, command))

        self.__logger.info('Backup [%s] created successfully' % (new_snapshot_name))

    def __str__(self):
        return 'Source [%s] snapshot container subvolume [%s] Destination [%s]' % \
            (self.source_url.geturl(), self.source_snapshot_subvolume, self.dest_url.geturl())


# Initialize logging
logger = logging.getLogger('')
logger.addHandler(StreamHandler(sys.stdout))
logger.setLevel(logging.INFO)

logger.info('%s v%s by %s' % (os.path.basename(__file__), __version__, __author__))

# Parse arguments
parser = ArgumentParser()
parser.add_argument('source_subvolume', type=str, help='Source subvolume to snapshot/backup. Local path or SSH url.')
parser.add_argument('destination_snapshot_subvolume', type=str, help='Destination subvolume storing received snapshots. Local path or SSH url.')
parser.add_argument('-sm', '--source-max-snapshots', type=int, default=10, help='Maximum number of source snapshots to keep (defaults to 10).')
parser.add_argument('-dm', '--destination-max-snapshots', type=int, default=10, help='Maximum number of destination snapshots to keep (defaults to 10).')
parser.add_argument('-ss', '--source-snapshot-subvolume', type=str, default='sxbackup', help='Override path to source snapshot container subvolume. Both absolute and relative paths are possible. Relative paths relate ot source subvolume. (defaults to sxbackup relative to source subvolume)')
args = parser.parse_args()

source_url = parse.urlsplit(args.source_subvolume)
dest_url = parse.urlsplit(args.destination_snapshot_subvolume)
source_snapshot_subvolume = args.source_snapshot_subvolume if args.source_snapshot_subvolume[0] == os.pathsep else os.path.join(source_url.path, args.source_snapshot_subvolume)

logger.info(source_snapshot_subvolume)
exit(0)

sxbackup = SxBackup(\
    source_url = source_url,\
    source_snapshot_subvolume = source_snapshot_subvolume,\
    source_max_snapshots = args.source_max_snapshots,\
    dest_url = dest_url,\
    dest_max_snapshots = args.destination_max_snapshots)

logger.info(sxbackup)

# Perform actual backup
sxbackup.run()
exit(0)
