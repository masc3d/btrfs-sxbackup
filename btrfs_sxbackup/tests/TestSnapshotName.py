import unittest

from btrfs_sxbackup.entities import SnapshotName


class TestSnapshotName(unittest.TestCase):
    def test_instantiation(self):
        print(SnapshotName.parse('sx-20150102-132010-utc'))
