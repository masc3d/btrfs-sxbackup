# Copyright (c) 2014 Marco Schindler
#
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the Free
# Software Foundation; either version 2 of the License, or (at your option)
# any later version.

import unittest

from btrfs_sxbackup.entities import SnapshotName


class TestSnapshotName(unittest.TestCase):
    def test_instantiation(self):
        print(SnapshotName.parse('sx-20150102-132010-utc'))
