import unittest
import time
from datetime import datetime
from datetime import timedelta
from btrfs_sxbackup.SnapshotName import SnapshotName
from btrfs_sxbackup.KeepExpression import KeepExpression


class TestKeepExpression(unittest.TestCase):
    def setUp(self):
        # Generate series of snapshot names
        snapshot_names = list()
        now = datetime.utcnow()
        for i in range(0, 24 * 120):
            timestamp = now + timedelta(hours=i)
            sn = SnapshotName(timestamp=timestamp)
            snapshot_names.append(sn)

        self.snapshot_names = snapshot_names

    def testKeepExpression(self):
        k = KeepExpression('1d = 4/d, 4d = daily, 1w = 2/d, 1m = weekly, 3m = none')

        start = time.perf_counter()
        (items_to_remove, items_to_keep) = k.filter(self.snapshot_names, lambda x: x.timestamp)
        print('Items to remove %d to keep %d' % (len(items_to_remove), len(items_to_keep)))
        self.assertEqual(len(items_to_remove) + len(items_to_keep), len(self.snapshot_names),
                         'Sum of items to keep and remove must be total number of items')
        print(time.perf_counter() - start)





