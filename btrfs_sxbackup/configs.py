import os
from configparser import ConfigParser

from btrfs_sxbackup.retention import RetentionExpression


class Configuration:
    """ btrfs-sxbackup global configuration file """

    __instance = None

    __CONFIG_FILENAME = '/etc/btrfs-sxbackup.conf'

    __SECTION_NAME = 'Default'
    __KEY_SOURCE_RETENTION = 'source-retention'
    __KEY_DEST_RETENTION = 'destination-retention'
    __KEY_LOG_IDENT = 'log-ident'
    __key_EMAIL_RECIPIENT = 'email-recipient'

    def __init__(self):
        self.__source_retention = None
        self.__destination_retention = None
        self.__log_ident = None
        self.__email_recipient = None

    @staticmethod
    def instance():
        """
        :return: Singleton instance
        :rtype: Configuration
        """
        if not Configuration.__instance:
            Configuration.__instance = Configuration()
        return Configuration.__instance

    @property
    def source_retention(self):
        return self.__source_retention

    @property
    def destination_retention(self):
        return self.__destination_retention

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

            source_retention_str = cparser.get(self.__SECTION_NAME, self.__KEY_SOURCE_RETENTION, fallback=None)
            dest_retention_str = cparser.get(self.__SECTION_NAME, self.__KEY_DEST_RETENTION, fallback=None)
            self.__source_retention = RetentionExpression(source_retention_str) if source_retention_str else None
            self.__destination_retention = RetentionExpression(dest_retention_str) if dest_retention_str else None
            self.__log_ident = cparser.get(self.__SECTION_NAME, self.__KEY_LOG_IDENT, fallback=None)
            self.__email_recipient = cparser.get(self.__SECTION_NAME, self.__key_EMAIL_RECIPIENT, fallback=None)
