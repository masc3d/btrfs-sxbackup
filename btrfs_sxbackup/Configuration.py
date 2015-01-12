import os
from configparser import ConfigParser
from btrfs_sxbackup.KeepExpression import KeepExpression


class Configuration:
    """ btrfs-sxbackup global configuration file """

    __CONFIG_FILENAME = '/etc/btrfs-sxbackup.conf'

    __SECTION_NAME = 'Global'
    __KEY_KEEP = 'keep'
    __KEY_LOG_IDENT = 'log-ident'
    __key_EMAIL_RECIPIENT = 'email-recipient'

    def __init__(self):
        self.keep = None
        self.log_ident = None
        self.email_recipient = None

    def read(self):
        cparser = ConfigParser()

        if os.path.exists(self.__CONFIG_FILENAME):
            with open(self.__CONFIG_FILENAME, 'r') as file:
                cparser.read_file(file)

            keep_str = cparser.get(self.__SECTION_NAME, self.__KEY_KEEP, fallback=self.keep)
            self.keep = KeepExpression(keep_str) if keep_str else None
            self.log_ident = cparser.get(self.__SECTION_NAME, self.__KEY_LOG_IDENT, fallback=None)
            self.email_recipient = cparser.get(self.__SECTION_NAME, self.__key_EMAIL_RECIPIENT, fallback=None)
