# Copyright (c) 2014 Marco Schindler
#
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the Free
# Software Foundation; either version 2 of the License, or (at your option)
# any later version.

import re
import sys
import os

from datetime import datetime
from datetime import timezone

from btrfs_sxbackup import shell

import logging

_logger = logging.getLogger(__name__)

class SnapshotName:
    """
    sxbackup snapshot name
    """

    __regex = re.compile('^sx-([0-9]{4})([0-9]{2})([0-9]{2})-([0-9]{2})([0-9]{2})([0-9]{2})-utc$', re.IGNORECASE)

    def __init__(self, timestamp=None):
        """
        c'tor
        :param timestamp: Timestamp
        """
        if timestamp is None:
            timestamp = datetime.now(timezone.utc)

        if timestamp.tzinfo is None:
            raise ValueError('Timestamp should be aware (have timezone info)')

        self.__timestamp = timestamp

    @property
    def timestamp(self):
        return self.__timestamp

    @staticmethod
    def parse(name):
        """
        Parse snapshot name
        :param name: Name to parse
        :return: Snapshot
        :rtype: SnapshotName
        """
        match = SnapshotName.__regex.match(name)
        if match is None:
            raise ValueError('Invalid snapshot name [%s]' % name)
        timestamp = datetime(year=int(match.group(1)),
                             month=int(match.group(2)),
                             day=int(match.group(3)),
                             hour=int(match.group(4)),
                             minute=int(match.group(5)),
                             second=int(match.group(6)),
                             tzinfo=timezone.utc)
        return SnapshotName(timestamp)

    def __repr__(self):
        return 'SnapshotName(timestamp=%s)' % self.__timestamp

    def __str__(self):
        """ Create formatted snapshot name """
        return self.__timestamp.strftime('sx-%Y%m%d-%H%M%S-utc')

    def format(self):
        return '%s: %s' % (self, self.__timestamp.astimezone().strftime("%c (%z)"))


class Subvolume(object):
    """
    btrfs subvolume
    """

    __regex = re.compile('^ID ([0-9]+).*gen ([0-9]+).*top level ([0-9]+).*path (.+).*$', re.IGNORECASE)

    def __init__(self, subvol_id, gen, top_level, path):
        self.__id = subvol_id
        self.__gen = gen
        self.__top_level = top_level
        self.__path = path

    def __repr__(self):
        return 'Subvolume(subvol_id=%d, gen=%d, top_level=%d, path=%s)' \
               % (self.__id, self.__gen, self.__top_level, self.__path)

    @property
    def id(self):
        return self.__id

    @property
    def gen(self):
        return self.__gen

    @property
    def top_level(self):
        return self.__top_level

    @property
    def path(self):
        return self.__path

    @staticmethod
    def parse(btrfs_sub_list_line):
        """
        :param btrfs_sub_list_line: Output line of btrfs sub list
        :return: Subvolume instance
        :rtype: Subvolume
        """

        m = Subvolume.__regex.match(btrfs_sub_list_line)
        if not m:
            raise ValueError('Invalid input for parsing subvolume [%s]' % btrfs_sub_list_line)

        return Subvolume(
            subvol_id=int(m.group(1)),
            gen=int(m.group(2)),
            top_level=int(m.group(3)),
            path=m.group(4))


class Snapshot:
    """
    sxbackup snapshot
    """

    def __init__(self, name: SnapshotName, subvolume):
        """
        :param name:
        :param subvolume:
        :type subvolume: Subvolume, None
        """
        self.__name = name
        self.__subvolume = subvolume

    @property
    def name(self):
        return self.__name

    @property
    def subvolume(self):
        return self.__subvolume

    def __repr__(self):
        return 'Snapshot(name=%s, subvolume=%s)' % self.name, self.subvolume

    def __str__(self):
        """ Create formatted snapshot name """
        return self.name.timestamp.strftime('sx-%Y%m%d-%H%M%S-utc')

    def format(self):
        return self.name.format()

class Filesystem:
    """
    Class to determine and compare the filesystem a path is on
    """
    
    __regex = re.compile('uuid: .*\\n')
    
    def __init__(self, path, url=None, ssh_options=None):
        self.__path = os.path.abspath(path)
        self.url = url
        self.ssh_options = ssh_options
    
    @property
    def path(self):
        return self.__path
    
    @property
    def uuid(self):
        currentpath = self.__path
        for x in range(0, len(currentpath.split(os.path.sep))):
            try:
                ret = shell.exec_check_output('btrfs fi show %s' % currentpath, self.url, self.ssh_options)
            except Exception as e:
                pass
            else:
                ret = ret.decode(sys.getdefaultencoding())
                ret = self.__regex.search(ret).group(0).strip().split(' ')[-1]                
                _logger.info('PATH %s has BTRFS filesystem uuid:%s' % (self.__path, ret))
                return ret
            currentpath = os.path.abspath(os.path.join(currentpath, os.pardir))
        raise ValueError('Did not find btrfs filesystem UUID. Is %s on a BTRFS filesystem?' % self.path)
    
    def __eq__(self, other):
        try:
            return self.uuid == other.uuid
        except Exception as e:
            _logger.error('Cannot compare filesystems of %s and %s. Error: %s' % (self.path, other.path, str(e)))
            _logger.error('Assuming filesystems are different')
            return False
        
    def __repr__(self):
        return self.uuid
