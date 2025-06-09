#! /bin/bash
set -ex

# Usage: update-pvcontrol.sh [version]
# Updates pvcontrol installed in /usr/local/bin to latest build or to the specified version.
# assumes valid gh login (e.g. gh auth login -w)

rm -f pv-control.tar.gz
if [ -z "$1" ]; then
    gh run download -R stephanme/pv-control -n pv-control.tar.gz
else
    gh release download "$1" -R stephanme/pv-control --pattern 'pv-control.tar.gz' --output pv-control.tar.gz
fi
rm -rf pvcontrol
mkdir -p pvcontrol && tar -xzf pv-control.tar.gz -C ./pvcontrol
uv sync --project pvcontrol --locked --no-dev
sudo rm -rf /usr/local/bin/pvcontrol-old
sudo mv /usr/local/bin/pvcontrol /usr/local/bin/pvcontrol-old
sudo mv ./pvcontrol /usr/local/bin/pvcontrol
sudo systemctl restart pvcontrol.service
