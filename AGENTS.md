# AGENTS.md

This file provides guidance to AI coding agents (Pi) when working with code in this repository.

## Project Overview

pv-control is an electric car charging controller for photovoltaic (PV) systems. It controls a go-e wallbox to charge an EV using solar power as efficiently as possible, with optional phase switching (1P/3P) via a GPIO relay on Raspberry Pi and vehicle SOC monitoring via the MySkoda API (Skoda cars).

## Architecture

**Python backend** (FastAPI + uvicorn):

```
pvcontrol/
  __main__.py          # CLI entry point: parses args, runs uvicorn
  app.py               # FastAPI app: lifespan (init/shutdown), static file serving, /metrics mount
  api.py               # REST API routes under /api/pvcontrol/ (GET state, PUT mode/phase/priority)
  service.py           # BaseService[C, D] — shared pattern for all services: config, data, error counter, Prometheus metrics
  dependencies.py      # Global singleton initialization: creates relay → wallbox → meter → car → controller + schedulers
  chargecontroller.py  # Core control loop: read meter/wallbox, calculate setpoints, control charging power and phase switching
  meter.py             # Meter implementations: KostalMeter (Modbus TCP), SolarWattMeter (REST), SmaTripowerMeter (webconnect), SimulatedMeter, TestMeter
  wallbox.py           # Wallbox implementations: GoeWallbox (REST/MQTT to go-e), SimulatedWallbox, SimulatedWallboxWithRelay
  car.py               # Car implementations: SkodaCar (MySkoda API), SimulatedCar, NoCar
  relay.py             # Phase relay: PhaseRelay base, DisabledPhaseRelay, SimulatedPhaseRelay, PhaseRelayFactory
  raspi_relay.py       # Real GPIO relay driver (RPi.GPIO) — only loaded when configured and on Pi
  scheduler.py         # Scheduler (threading.Timer), AsyncScheduler (asyncio.gather + sleep)
  mqtt.py              # MQTT publisher with Home Assistant auto-discovery, state restore from retained messages
  utils.py             # aiohttp trace config for debug logging
```

**Key patterns**:

- Every hardware abstraction (meter, wallbox, car, relay) extends `BaseService[Config, Data]` with `read_data()`, error counting, and Prometheus Gauges.
- Factory classes (`MeterFactory`, `WallboxFactory`, `CarFactory`, `PhaseRelayFactory`) instantiate the correct implementation from a type string.
- `ChargeController.run()` is the core control loop, scheduled via `AsyncScheduler` at configurable cycle intervals (default 30s).
- Global dependencies are resolved in `dependencies.init()` and stored as module-level variables in `dependencies.py`.
- CLI args (`--meter`, `--wallbox`, `--relay`, `--car`, `--config JSON`) control which implementations are used — enabling simulation without code changes.

**Charge modes**: OFF, MAX, MANUAL, PV_ONLY, PV_ALL
**Priority modes**: AUTO (balance home battery vs car), HOME_BATTERY, CAR
**Phase modes**: DISABLED, AUTO, CHARGE_1P, CHARGE_3P

**Frontend**: Single-page Angular **v22** app (`ui/` — Angular 22.2.x, TypeScript 6.0 (Angular 22.2 requires `>=6.0 <6.1` — do not jump to TS 7), zoneless, no router, Angular Material 22, Vitest 5), built to `ui/dist/ui/browser/`, served as static files by the FastAPI app. The v22 conventions and the Angular CLI/MCP workflow are in the `angular-ui` skill (`.pi/skills/angular-ui/SKILL.md`).

## Agent tooling

Pi only. Sources of agent truth: **this file** (project-wide), **`.mcp.json`** (MCP servers), **`.pi/skills/`** (framework/repo skills).

- `.vscode/mcp.json` is a hand-maintained mirror of `.mcp.json` (VS Code can't read the latter) — keep both in sync when adding a server, or delete it if VS Code is no longer used here.
- Do **not** reintroduce other agents' config files (`.claude/`, `CLAUDE.md`, `.github/copilot-instructions.md`, `.github/instructions/*.instructions.md`, `.cursor/`, `.cursorrules`). Pi ignores them and they silently go stale.

## Development Commands

All Python commands use `uv run`. Install with `make install` (runs `uv sync` + `npm install` in ui/).

| Task | Command |
|------|---------|
| Install deps | `make install` or `uv sync --all-extras` |
| Run app locally | `uv run -m pvcontrol` |
| Run with auto-reload | `uv run uvicorn pvcontrol.app:app --port 8080 --reload --reload-dir ./pvcontrol` |
| Lint (Python) | `make lint` → `uv run ruff check`, `uv run ruff format --check`, `uv run ty check` |
| Lint (UI) | `make lint` → `(cd ui && ng lint)` |
| Type check | `uv run ty check` |
| Run Python tests | `uv run python -m unittest discover -v -s tests` or `make test` |
| Build UI | `(cd ui && ng build --configuration production)` |
| Build package | `make build` or `uv build` |
| Full dev cycle | `make` (default: install + lint + test) |
| Angular dev server (MCP) | `mcp` tool → `angular-cli` `devserver_start` / `devserver_wait_for_build` / `devserver_stop` |
| Angular docs lookup (MCP) | `mcp` tool → `angular-cli` `search_documentation` / `get_best_practices` |
| UI unit tests | `(cd ui && npm test)` (Vitest) |
| Clean | `make clean` |
| Upgrade deps | `make upgrade` or `uv sync --upgrade --all-extras --dev` |

## Testing

Tests are standard Python `unittest` in `tests/`, one file per module:

- `test_api.py`, `test_app.py` — API endpoint and app lifespan tests
- `test_chargecontroller.py` — core control loop logic (most complex test file)
- `test_meter.py`, `test_wallbox.py`, `test_car.py`, `test_relay.py` — service implementations
- `test_mqtt.py` — MQTT publishing and state restore
- `test_scheduler.py` — scheduler behavior

Use `TestMeter` (from `meter.py`) in tests to set PV/home power/SOC values directly. Use `SimulatedWallbox.set_car_status()` and `set_wb_error()` for controlled testing.

## Configuration

Configuration is JSON passed via `--config` or service file. The structure maps to component types:

```json
{
  "meter": { "host": "scb.fritz.box", ... },
  "wallbox": { "url": "http://go-echarger.fritz.box", ... },
  "relay": { "enable_phase_switching": true, "installed_on_host": "..." },
  "car": { "user": "...", "password": "...", "vin": "...", ... },
  "controller": { "cycle_time": 30, "line_voltage": 230, ... },
  "mqtt": { "broker": "localhost", "port": 1883, ... }
}
```

Config dataclasses live in each module: `ChargeControllerConfig` (chargecontroller.py), `*MeterConfig` (meter.py), `WallboxConfig`/`GoeWallboxConfig` (wallbox.py), `CarConfig`/`SkodaCarConfig` (car.py), `PhaseRelayConfig` (relay.py), `MqttConfig` (mqtt.py).

## Deployment

- **Raspberry Pi**: systemd service (`pvcontrol.service`) behind nginx (`pvcontrol.nginx`)
- **k8s**: Docker image built via GitHub Actions, published to `ghcr.io/stephanme/pv-control`
- **Docker**: `docker build -t stephanme/pv-control .` (multi-stage, Python 3.14)
- Uses `uv` for dependency management and building (see `pyproject.toml`, `uv.lock`)

## Key constraints

- Python >= 3.14 required
- RPi.GPIO only available on Linux ARM — guarded by runtime check and lazy import
- Line length: 140 chars (ruff config)
- `ty` (Python 3.14's type checker) is used for type checking instead of pyright/mypy
- `ruff` for linting + formatting; `httpx` in dev deps for API testing
- Prometheus metrics are module-level globals with `pvcontrol_` prefix
