# pv-control

... controlling an electric car charger to charge from solar energy as efficient as possible.

For the deployment on a k8s cluster and the used hardware, see the related project [pv-monitoring](https://github.com/stephanme/pv-monitoring).

pv-control contains:
- A control loop implemented in Python that reads energy data from the inverter and sets the charge current of the wallbox.
- Some logic to control 1-phase vs 3-phase charging of the go-e wallbox via an external relay. Therefore, pv-control must run on a Raspberry PI.
- A we-connect client to read the SOC for an VW ID3.
- A number of REST endpoints to control the operation like setting charge mode and to get basic info about energy consumption.
- A simple UI implemented in Angular optimized for mobile phones.
- A Prometheus endpoint for monitoring the charging process.

PV-Control implements the following charge modes/strategies:
- OFF
- PV only - Try to charge with solar power only.
- PV all - Try to charge all available solar power into the car.
- Max - Charge with full power, i.e. 11 kW (3x 16A).
- Manual - Wallbox is manually controlled e.g. by the go-e app.

'PV only' and 'PV all' use different strategies when working around the limitations of the wallbox and electric car, i.e. the minimal charging current of 6A and the charging current steps of 1A. Additionally, PV-Control allows to prioritize between car charging and home battery charging:
- Auto -  charge home battery until 50% (configurable), then charge car before home battery
- Home - charge home battery before car
- Car - charge car before home battery
The home battery is not used for charging the car in the 'PV' modi.

Automatic phase switching between 1 and 3 phases for the PV modes is implemented but not yet tested in practice because my 7 kW peak solar power system gives little opportunity of 3 phase charging. Currently, the 'Auto' mode selects 1-phase charging for 'PV only' and 'PV all' and 3-phase charging for 'Max'.

## UI

![pv-control screen shot](pvcontrol-screenshot.jpg)

## Wiring of Wallbox and Phase Switching Relay

A relay allows to switch between 1 phase and 3 phase charging. The control loop ensures that phase switching happens only when the wallbox is not charging. After switching, the go-e wallbox needs a reset.

Restarting pv-control (e.g. for updates) doesn't change the state of the relay. A reboot of the Raspberry initializes the relay to 1-phase charging.

![wallbox and phase switching relay](wallbox.png)

## Configuration

```
python -m pvcontrol --help
usage: __main__.py [-h] [-m METER] [-w WALLBOX] [-r RELAY] [-a CAR] [-c CONFIG] [--hostname HOSTNAME] [--host HOST] [--port PORT] [--basehref BASEHREF]

PV Control

optional arguments:
  -h, --help            show this help message and exit
  -m METER, --meter METER
  -w WALLBOX, --wallbox WALLBOX
  -r RELAY, --relay RELAY
  -a CAR, --car CAR
  -c CONFIG, --config CONFIG
  --hostname HOSTNAME   server hostname, can be used to enable/disable phase relay on k8s
  --host HOST           server host (default: 0.0.0.0)
  --port PORT           server port (default: 8080)
```

METER, WALLBOX and CAR refer to implementation classes for the energy meter, the wallbox and the car:
- METER = KostalMeter|FroniusMeter|SimulatedMeter
- WALLBOX = GoeWallbox|SimulatedWallbox|SimulatedWallboxWithRelay
- RELAY = RaspiPhaseRelay|SimulatedPhaseRelay
- CAR = VolkswagenIDCar|SimulatedCar|NoCar

CONFIG is a json with 'meter', 'wallbox', 'relay', 'car' and 'controller' configuration structures. The config parameters depend on the METER, WALLBOX, RELAY and CAR type. See the corresponding ...Config data classes
in the source files `meter.py`, `wallbox.py`, `car.py` and `chargecontroller.py`.

HOST, PORT and BASEHREF configure the web server. BASEHREF can be used to add a prefix to the web server url so that it matches `ng build --base-href BASEHREF/` if not running behind an ingres on k8s.

HOSTNAME should be set to the host or node name where pvcontrol is running (e.g. by k8s metadata). Allows to automatically disable the phase relay when not deployed on correct hardware, i.e. pv-control still works but with
reduced functionality.

## Installation

Pre-requisites:
- Raspberry Pi 2 with Raspberry Pi OS Lite (Debian 12), or newer model
- [Raspberry Pi Expansion Board, Power Relay](https://www.waveshare.com/rpi-relay-board.htm)
- Python 3.13, pip
  - installation using [uv](https://docs.astral.sh/uv/getting-started/installation/)
- download `pv-control.tar.gz` package (release artifacts or from github actions)

The following procedure installs pvcontrol behind an nginx on port 80.

```
# preparation
sudo apt install libffi-dev

# pvcontrol
mkdir -p ~/pvcontrol
tar -xzf pv-control.tar.gz -C ~/pvcontrol
uv sync --project pvcontrol --locked --no-dev
sudo mv ./pvcontrol /usr/local/bin/pvcontrol

sudo cp /usr/local/bin/pvcontrol/pvcontrol.service /etc/systemd/system
# adapt configuration in /etc/systemd/system/pvcontrol.service
sudo systemctl daemon-reload
sudo systemctl start pvcontrol.service
sudo systemctl enable pvcontrol.service

sudo apt install nginx
sudo cp /usr/local/bin/pvcontrol/pvcontrol.nginx /etc/nginx/sites-available/pvcontrol.nginx
# adapt pvcontrol.nginx if needed (e.g. multiple apps running on same raspi)
sudo ln -s /etc/nginx/sites-available/pvcontrol.nginx /etc/nginx/sites-enabled/pvcontrol.nginx
sudo rm /etc/nginx/sites-enabled/default
sudo systemctl start nginx

# journalctl -u pvcontrol.service -f
# http://pvcontrol.fritz.box
```

pvcontrol can be updated using the `update-pvcontrol.sh` script. Prerequisites:
- gh cli installed as described in https://github.com/cli/cli/blob/trunk/docs/install_linux.md
- successful github login, e.g. with `gh auth login -w`
- pvcontrol was installed as described above
- `update-pvcontrol.sh` script copied into home directory of raspberry
- Usage
  - `./update-pvcontrol.sh` - update to latest successful build result of main branch
  - `./update-pvcontrol.sh <version>` - update to specified version (github release tag, e.g. v4)

## Installation on k8s

Tested on Raspberry Pi 4 with Raspberry Pi OS Lite (Debian 12, 64 bit).

Example k8s manifest for deploying pv-control:
- https://github.com/stephanme/pv-monitoring/blob/main/pvcontrol/pvcontrol.yaml

## Development

pv-control contains a number of mock implementations for wallbox and inverter/power meter to allow testing and local development.

Basic setup:
- [uv](https://github.com/astral-sh/uv) - Python package and project manager
- a recent version of node and npm (see Angular requirements)

How to run locally:
```
# in pv-control/ui
npm install
ng build

# in pv-control
uv sync
uv run -m pvcontrol

# http://localhost:8080

# alternative with automatic reload
uv run uvicorn pvcontrol.app:app --port 8080 --reload --reload-dir ./pvcontrol
```

How to run Python tests:
```
uv run ruff check
uv run ruff format --check
uv run pyright
uv run -m unittest discover -s ./tests
```

How to run UI tests:
```
# in pv-control/ui
ng lint
npm run test
```

Local docker build:
```
docker build -t stephanme/pv-control .
docker run -p 8080:8080 stephanme/pv-control
docker run -it stephanme/pv-control bash
```

## CI and Release

A docker container [ghcr.io/stephanme/pv-control](https://github.com/stephanme/pv-control/pkgs/container/pv-control) is built for every commit via github actions. The arm image is intended to run on a k8s cluster on a Raspberry node.
