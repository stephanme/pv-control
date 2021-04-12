from dataclasses import dataclass
import typing
import prometheus_client


@dataclass
class BaseConfig:
    pass


@dataclass
class BaseData:
    error: int = 0  # error counter, 0=OK


C = typing.TypeVar("C", bound=BaseConfig)  # type of configuration
D = typing.TypeVar("D", bound=BaseData)  # type of data


class BaseService(typing.Generic[C, D]):
    _metrics_pvc_error = prometheus_client.Gauge("pvcontrol_error", "Error counter per service. 0 = ok.", ["service"])

    def __init__(self, config: C):
        self._service_label = type(self).__name__  # assumes singleton services
        BaseService._metrics_pvc_error.labels(self._service_label).set(0)
        self._config = config

    def get_config(self) -> C:
        """ Get configuration. """
        return self._config

    def get_data(self) -> D:
        """ Get last data. """
        return self._data

    def _set_data(self, data: D) -> None:
        data.error = self.get_error_counter()
        self._data = data

    def get_error_counter(self) -> int:
        return int(BaseService._metrics_pvc_error.labels(self._service_label)._value.get())  # hacky

    def inc_error_counter(self) -> int:
        BaseService._metrics_pvc_error.labels(self._service_label).inc()
        errcnt = self.get_error_counter()
        self._data.error = errcnt
        return errcnt

    def reset_error_counter(self):
        BaseService._metrics_pvc_error.labels(self._service_label).set(0)
        self._data.error = 0
