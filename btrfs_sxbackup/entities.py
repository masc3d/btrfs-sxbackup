import re

from datetime import datetime


class SnapshotName:
    __regex = re.compile('^sx-([0-9]{4})([0-9]{2})([0-9]{2})-([0-9]{2})([0-9]{2})([0-9]{2})-utc$', re.IGNORECASE)

    def __init__(self, timestamp=None):
        """
        c'tor
        :param timestamp: Timestamp
        """
        if timestamp is None:
            timestamp = datetime.utcnow()

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
                             second=int(match.group(6)))
        return SnapshotName(timestamp)

    def __repr__(self):
        return 'SnapshotName(timestamp=%s)' % self.__timestamp

    def __str__(self):
        """ Create formatted snapshot name """
        return self.__timestamp.strftime('sx-%Y%m%d-%H%M%S-utc')


class Subvolume(object):
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
