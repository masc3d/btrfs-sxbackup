import os
from configparser import ConfigParser
from distutils import util
from urllib import parse

from btrfs_sxbackup.retention import KeepExpression
from btrfs_sxbackup.entities import LocationType


class Configuration:
    """ btrfs-sxbackup global configuration file """

    __instance = None

    __CONFIG_FILENAME = '/etc/btrfs-sxbackup.conf'

    __SECTION_NAME = 'Global'
    __KEY_KEEP = 'keep'
    __KEY_LOG_IDENT = 'log-ident'
    __key_EMAIL_RECIPIENT = 'email-recipient'

    def __init__(self):
        self.__keep = None
        self.__log_ident = None
        self.__email_recipient = None

    @staticmethod
    def instance():
        """
        :return: Singleton instance
        :rtype: Configuration
        """
        if not Configuration.__instance:
            Configuration._instance = Configuration()
        return Configuration.__instance

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


class LocationConfiguration:
    """ btrfs-sxbackup configuration file """

    __KEY_SOURCE = 'source'
    __KEY_SOURCE_CONTAINER = 'source-container'
    __KEY_DESTINATION = 'destination'
    __KEY_KEEP = 'keep'
    __KEY_COMPRESS = 'compress'

    def __init__(self, ltype: LocationType=None):
        """
        c'tor
        """
        self.__locationtype = ltype
        self.__source = None
        self.__destination = None
        self.__keep = None

        self.source_container = None
        self.compress = False

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
    def keep(self) -> KeepExpression:
        return self.__keep

    @keep.setter
    def keep(self, keep: KeepExpression):
        self.__keep = keep

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

        source = parser.get(section, config.__KEY_SOURCE, fallback=None)
        destination = parser.get(section, config.__KEY_DESTINATION, fallback=None)
        keep = parser.get(section, config.__KEY_KEEP, fallback=None)

        config.source = parse.urlsplit(source) if source else None
        config.source_container = parser.get(section, config.__KEY_SOURCE_CONTAINER, fallback=None)
        config.destination = parse.urlsplit(destination) if destination else None
        config.keep = KeepExpression(keep) if keep else None
        config.compress = util.strtobool(parser.get(section, config.__KEY_COMPRESS, fallback='False'))

        return config

    def write(self, fileobject):
        parser = ConfigParser()

        section = self.__locationtype.name
        parser.add_section(section)
        if self.source is not None:
            parser.set(section, self.__KEY_SOURCE, str(self.source))
        if self.source_container is not None:
            parser.set(section, self.__KEY_SOURCE_CONTAINER, self.source_container)
        if self.destination is not None:
            parser.set(section, self.__KEY_DESTINATION, str(self.destination))
        if self.keep is not None:
            parser.set(section, self.__KEY_KEEP, str(self.keep))
        if self.compress is not None:
            parser.set(section, self.__KEY_COMPRESS, str(self.compress))
        parser.write(fileobject)
