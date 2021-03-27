from dataclasses import dataclass


@dataclass
class BaseConfig:
    pass


@dataclass
class BaseData:
    pass


class BaseService:
    _config = BaseConfig()
    _data = BaseData()

    def get_config(self) -> BaseConfig:
        """ Get configuration. """
        return BaseService._config

    def get_data(self) -> BaseData:
        """ Get last data. """
        return BaseService._data
