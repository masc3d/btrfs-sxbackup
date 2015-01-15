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
        self.__keep = None
        self.__log_ident = None
        self.__email_recipient = None

    @property
    def keep(self):
        return self.__keep

    @property
    def log_ident(self):
        return self.__log_ident

    @property
    def email_recipient(self):
        return self.__email_recipient

    def read(self):
        cparser = ConfigParser()

        if os.path.exists(self.__CONFIG_FILENAME):
            with open(self.__CONFIG_FILENAME, 'r') as file:
                cparser.read_file(file)

            keep_str = cparser.get(self.__SECTION_NAME, self.__KEY_KEEP, fallback=self.__keep)
            self.__keep = KeepExpression(keep_str) if keep_str else None
            self.__log_ident = cparser.get(self.__SECTION_NAME, self.__KEY_LOG_IDENT, fallback=None)
            self.__email_recipient = cparser.get(self.__SECTION_NAME, self.__key_EMAIL_RECIPIENT, fallback=None)
