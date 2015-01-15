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
