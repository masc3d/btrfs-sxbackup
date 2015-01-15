import unittest
from btrfs_sxbackup.SnapshotName import SnapshotName


class TestSnapshotName(unittest.TestCase):
    def testInstantiation(self):
        print(SnapshotName.parse('sx-20150102-132010-utc'))
