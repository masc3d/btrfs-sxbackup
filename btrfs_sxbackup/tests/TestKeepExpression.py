# Copyright (c) 2014 Marco Schindler
#
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the Free
# Software Foundation; either version 2 of the License, or (at your option)
# any later version.

import logging
import unittest
import sys
import time
from datetime import datetime
from datetime import timedelta
from datetime import timezone

from btrfs_sxbackup.entities import SnapshotName
from btrfs_sxbackup.retention import RetentionExpression


class TestKeepExpression(unittest.TestCase):
    def setUp(self):
        logger = logging.getLogger()
        logger.addHandler(logging.StreamHandler(sys.stdout))
        logger.setLevel(logging.DEBUG)

        # Generate series of snapshot names
        snapshot_names = list()
        now = datetime.now(timezone.utc)
        for i in range(0, 24 * 120):
            timestamp = now - timedelta(hours=i)
            sn = SnapshotName(timestamp=timestamp)
            snapshot_names.append(sn)

        self.snapshot_names = snapshot_names

    def test_filter(self):
        k = RetentionExpression('1d:4/d, 4d:daily, 1w:2/4d, 1m:weekly, 12m:1/y, 23m:none')
        #k = KeepExpression('10')

        start = time.perf_counter()
        (items_to_remove_by_condition, items_to_keep) = k.filter(self.snapshot_names, lambda x: x.timestamp)

        items_to_remove_amount = sum(map(lambda x: len(x), items_to_remove_by_condition.values()))
        items_to_keep_amount = len(items_to_keep)

        # for i in items_to_keep:
        #     print(i)
        #
        # for c in items_to_remove_by_condition.keys():
        #     print(c)
        #     for i in items_to_remove_by_condition[c]:
        #         print(i)

        print('Items to remove %d to keep %d' % (items_to_remove_amount, items_to_keep_amount))
        self.assertEqual(items_to_remove_amount + items_to_keep_amount, len(self.snapshot_names),
                         'Sum of items to keep and remove must be total number of items')
        print(time.perf_counter() - start)
