# for development run uvicorn with this module:
# uv run uvicorn pvcontrol.app:app --port 8080 --reload --reload-dir ./pvcontrol

import logging
import re
from argparse import Namespace
from contextlib import asynccontextmanager
from typing import Any, final, override

import prometheus_client
from fastapi import FastAPI
from fastapi.routing import Mount
from starlette.responses import Response
from starlette.staticfiles import PathLike, StaticFiles

from pvcontrol import api, dependencies

logger = logging.getLogger(__name__)


# Static files for the Angular app, with cache control for immutable resources
@final
class AngularAppStaticFiles(StaticFiles):
    def __init__(self, *args: Any, **kwargs: Any):
        self.cachecontrol = "public, max-age=31536000, s-maxage=31536000, immutable"
        super().__init__(*args, **kwargs)

    @override
    def file_response(
        self,
        full_path: PathLike,
        stat_result: Any,
        scope: Any,
        status_code: int = 200,
    ) -> Response:
        resp: Response = super().file_response(full_path, stat_result, scope, status_code)
        if AngularAppStaticFiles.is_immutable_resource(full_path.__str__()):
            resp.headers.setdefault("Cache-Control", self.cachecontrol)
        return resp

    _angular_hashed_files_pattern = re.compile(r"\w+-[0-9a-zA-Z]{8,}\.\w+")

    @classmethod
    def is_immutable_resource(cls, path: str) -> bool:
        # short cut for
        if path == "index.html":
            return False
        # remove any path prefix
        path = path.split("/")[-1]
        return True if AngularAppStaticFiles._angular_hashed_files_pattern.match(path) is not None else False


# TODO: get rid of argsparse dependency
args = Namespace(
    meter="SimulatedMeter",
    wallbox="SimulatedWallbox",
    relay="SimulatedPhaseRelay",
    car="SimulatedCar",
    hostname="",
)
config: dict[str, Any] = {"wallbox": {}, "meter": {}, "car": {}, "controller": {}, "relay": {}}


@asynccontextmanager
async def lifespan(_app: FastAPI):
    logger.info("Starting pvcontrol API server")
    await dependencies.init(args, config)
    yield
    await dependencies.shutdown()
    logger.info("Stopped pvcontrol")


app = FastAPI(lifespan=lifespan, title="PV Control", version=dependencies.version)
app.include_router(api.router)
# workaround to get /metrics working (not just /metrics/), https://github.com/prometheus/client_python/issues/1016
metrics_route = Mount("/metrics", prometheus_client.make_asgi_app())  # pyright: ignore[reportUnknownArgumentType, reportUnknownMemberType]
metrics_route.path_regex = re.compile("^/metrics(?P<path>.*)$")
app.routes.append(metrics_route)
# static angular resources, must be mounted last
app.mount("", AngularAppStaticFiles(directory="./ui/dist/ui/browser", html=True), name="static")
