# Copyright (c) 2014 Marco Schindler
#
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the Free
# Software Foundation; either version 2 of the License, or (at your option)
# any later version.

import re

from datetime import datetime
from datetime import timezone

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

