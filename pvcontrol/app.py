# for development run uvicorn with this module:
# uv run uvicorn pvcontrol.app:app --port 8080 --reload --reload-dir ./pvcontrol

from argparse import Namespace
from contextlib import asynccontextmanager
import logging
import re
from fastapi import FastAPI
from fastapi.routing import Mount
import prometheus_client
from starlette.responses import Response
from starlette.staticfiles import StaticFiles

from pvcontrol import api, dependencies

logger = logging.getLogger(__name__)


# Static files for the Angular app, with cache control for immutable resources
class AngularAppStaticFiles(StaticFiles):
    def __init__(self, *args, **kwargs):
        self.cachecontrol = "public, max-age=31536000, s-maxage=31536000, immutable"
        super().__init__(*args, **kwargs)

    def file_response(self, full_path: str, *args, **kwargs) -> Response:
        resp: Response = super().file_response(full_path, *args, **kwargs)
        if AngularAppStaticFiles.is_immutable_resource(full_path):
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
config = {"wallbox": {}, "meter": {}, "car": {}, "controller": {}, "relay": {}}


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting pvcontrol API server")
    await dependencies.init(args, config)
    yield
    await dependencies.shutdown()
    logger.info("Stopped pvcontrol")


app = FastAPI(lifespan=lifespan, title="PV Control", version=dependencies.version)
app.include_router(api.router)
# workaround to get /metrics working (not just /metrics/), https://github.com/prometheus/client_python/issues/1016
metrics_route = Mount("/metrics", prometheus_client.make_asgi_app())
metrics_route.path_regex = re.compile("^/metrics(?P<path>.*)$")
app.routes.append(metrics_route)
# static angular resources, must be mounted last
app.mount("", AngularAppStaticFiles(directory="./ui/dist/ui/browser", html=True), name="static")
