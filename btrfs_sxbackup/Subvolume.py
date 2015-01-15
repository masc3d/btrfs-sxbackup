import re


class Subvolume(object):
    __regex = re.compile('^ID ([0-9]+) gen ([0-9]+) top level ([0-9]+) path (.+)$', re.IGNORECASE)

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
