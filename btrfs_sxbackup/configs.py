import os
from configparser import ConfigParser
from distutils import util
from urllib import parse
from uuid import UUID

from btrfs_sxbackup.retention import RetentionExpression
from btrfs_sxbackup.entities import LocationType


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


class LocationConfiguration:
    """ btrfs-sxbackup configuration file """

    __KEY_UUID = 'uuid'
    __KEY_SOURCE = 'source'
    __KEY_SOURCE_CONTAINER = 'source-container'
    __KEY_DESTINATION = 'destination'
    __KEY_KEEP = 'keep'
    __KEY_RETENTION = 'retention'
    __KEY_COMPRESS = 'compress'

    def __init__(self, ltype: LocationType=None):
        """
        c'tor
        """
        self.__locationtype = ltype
        self.__uuid = None
        self.__source = None
        self.__destination = None
        self.__retention = None

        self.source_container = None
        self.compress = False

    @property
    def uuid(self) -> UUID:
        return self.__uuid

    @uuid.setter
    def uuid(self, uuid: UUID):
        self.__uuid = uuid

    @property
    def source(self) -> parse.SplitResult:
        return self.__source

    @source.setter
    def source(self, source: parse.SplitResult):
        self.__source = source

    @property
    def destination(self) -> parse.SplitResult:
        return self.__destination

    @destination.setter
    def destination(self, dest: parse.SplitResult):
        self.__destination = dest

    @property
    def retention(self) -> RetentionExpression:
        return self.__retention

    @retention.setter
    def retention(self, retention: RetentionExpression):
        self.__retention = retention

    @property
    def location_type(self) -> LocationType:
        return self.__locationtype

    @location_type.setter
    def location_type(self, ltype: LocationType):
        self.__locationtype = ltype

    @staticmethod
    def read(fileobject):
        """
        :param fileobject:
        :return: configuration
        :rtype: LocationConfiguration
        """
        config = LocationConfiguration()
        parser = ConfigParser()
        parser.read_file(fileobject)

        section = parser.sections()[0]

        if section == LocationType.Source.name:
            config.location_type = LocationType.Source
        elif section == LocationType.Destination.name:
            config.location_type = LocationType.Destination
        else:
            raise ValueError('Invalid section name / location type [%s]' % section)

        uuid = parser.get(section, config.__KEY_UUID, fallback=None)
        source = parser.get(section, config.__KEY_SOURCE, fallback=None)
        source_container = parser.get(section, config.__KEY_SOURCE_CONTAINER, fallback=None)
        destination = parser.get(section, config.__KEY_DESTINATION, fallback=None)
        # Keep has been renamed to retention.
        # Supporting the old name for backwards compatibility.
        retention = parser.get(section, config.__KEY_RETENTION, fallback=None)
        if not retention:
            retention = parser.get(section, config.__KEY_KEEP, fallback=None)

        config.uuid = UUID(uuid) if uuid else None
        config.source = parse.urlsplit(source.rstrip(os.path.sep)) if source else None
        config.source_container = source_container.rstrip(os.path.sep) if source_container else None
        config.destination = parse.urlsplit(destination.rstrip(os.path.sep)) if destination else None
        config.retention = RetentionExpression(retention) if retention else None
        config.compress = util.strtobool(parser.get(section, config.__KEY_COMPRESS, fallback='False'))

        return config

    def write(self, fileobject):
        parser = ConfigParser()

        section = self.__locationtype.name
        parser.add_section(section)
        if self.uuid:
            parser.set(section, self.__KEY_UUID, str(self.uuid))
        if self.source is not None:
            parser.set(section, self.__KEY_SOURCE, str(self.source))
        if self.source_container is not None:
            parser.set(section, self.__KEY_SOURCE_CONTAINER, self.source_container)
        if self.destination is not None:
            parser.set(section, self.__KEY_DESTINATION, str(self.destination))
        if self.retention is not None:
            parser.set(section, self.__KEY_RETENTION, str(self.retention))
        if self.compress is not None:
            parser.set(section, self.__KEY_COMPRESS, str(self.compress))
        parser.write(fileobject)
