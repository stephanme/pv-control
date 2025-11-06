import logging
from types import SimpleNamespace

import aiohttp

aiohttp_logger = logging.getLogger("aiohttp.trace")


async def on_request_start(_session: aiohttp.ClientSession, _trace_config_ctx: SimpleNamespace, params: aiohttp.TraceRequestStartParams):
    aiohttp_logger.debug(f"{params.method} {params.url}")


async def on_request_end(_session: aiohttp.ClientSession, _trace_config_ctx: SimpleNamespace, params: aiohttp.TraceRequestEndParams):
    aiohttp_logger.debug(f"{params.method} {params.url} - {params.response.status}")


aiohttp_trace_config = aiohttp.TraceConfig()
aiohttp_trace_config.on_request_start.append(on_request_start)
aiohttp_trace_config.on_request_end.append(on_request_end)
