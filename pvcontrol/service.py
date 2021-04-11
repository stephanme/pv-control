from dataclasses import dataclass
import prometheus_client


@dataclass
class BaseConfig:
    pass


@dataclass
class BaseData:
    error: int = 0  # error counter, 0=OK


class BaseService:
    _config = BaseConfig()
    _data = BaseData()
    _metrics_pvc_error = prometheus_client.Gauge("pvcontrol_error", "Error counter per service. 0 = ok.", ["service"])

    def __init__(self):
        self._service_label = type(self).__name__  # assumes singleton services
        BaseService._metrics_pvc_error.labels(self._service_label).set(0)

    def get_error_counter(self) -> int:
        return int(BaseService._metrics_pvc_error.labels(self._service_label)._value.get())  # hacky

    def inc_error_counter(self) -> int:
        BaseService._metrics_pvc_error.labels(self._service_label).inc()
        return self.get_error_counter()

    def reset_error_counter(self):
        BaseService._metrics_pvc_error.labels(self._service_label).set(0)

    def get_config(self) -> BaseConfig:
        """ Get configuration. """
        return BaseService._config

    def get_data(self) -> BaseData:
        """ Get last data. """
        return BaseService._data
