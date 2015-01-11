import re
from datetime import datetime

class SnapshotName:
    __regex = re.compile('^sx-([0-9]{4})([0-9]{2})([0-9]{2})-([0-9]{2})([0-9]{2})([0-9]{2})-utc$', re.IGNORECASE)

    def __init__(self, name=None, timestamp=None):
        """
        c'tor
        :param name: Snapshot name
        """
        if name is not None:
            # parse snapshot name timestamp
            match = SnapshotName.__regex.match(name)
            if match is None:
                raise ValueError('Invalid snapshot name [%s]' % name)
            self.timestamp = datetime(year=int(match.group(1)),
                                      month=int(match.group(2)),
                                      day=int(match.group(3)),
                                      hour=int(match.group(4)),
                                      minute=int(match.group(5)),
                                      second=int(match.group(6)))
        else:
            if timestamp is None:
                timestamp = datetime.utcnow()

            self.timestamp = timestamp

    def __repr__(self):
        return 'SnapshotName(timestamp=%s)' % self.timestamp

    def __str__(self):
        """ Create formatted snapshot name """
        return self.timestamp.strftime('sx-%Y%m%d-%H%M%S-utc')
