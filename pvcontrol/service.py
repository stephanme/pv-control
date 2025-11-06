from typing import Any
from dataclasses import dataclass
from prometheus_client import Gauge


@dataclass
class BaseConfig:
    pass


@dataclass
class BaseData:
    error: int = 0  # error counter, 0=OK


class BaseService[C: BaseConfig, D: BaseData]:
    _metrics_pvc_error: Gauge = Gauge("pvcontrol_error", "Error counter per service. 0 = ok.", ["service"])

    def __init__(self, config: C, data: D):
        self._service_label: str = type(self).__name__  # assumes singleton services
        BaseService._metrics_pvc_error.labels(self._service_label).set(0)
        self._config: C = config
        self._data: D = data

    def get_config(self) -> C:
        """Get configuration."""
        return self._config

    def get_data(self) -> D:
        """Get last data."""
        return self._data

    def _set_data(self, data: D) -> None:
        data.error = self.get_error_counter()
        self._data = data

    def get_error_counter(self) -> int:
        v: float | Any = BaseService._metrics_pvc_error.labels(self._service_label)._value.get()  # pyright: ignore[reportPrivateUsage, reportUnknownVariableType]
        if isinstance(v, (int, float)):
            return int(v)
        return 0

    def inc_error_counter(self) -> int:
        BaseService._metrics_pvc_error.labels(self._service_label).inc()
        errcnt = self.get_error_counter()
        self._data.error = errcnt
        return errcnt

    def reset_error_counter(self):
        BaseService._metrics_pvc_error.labels(self._service_label).set(0)
        self._data.error = 0
