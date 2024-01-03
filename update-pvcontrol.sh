#! /bin/bash
set -x

# Usage: update-pvcontrol.sh [version]
# Updates pvcontrol installed in /usr/local/bin to latest build or to the specified version.
# assumes valid gh login (e.g. gh auth login -w)

rm pv-control.tar.gz
rm -rf pvcontrol
sudo rm -rf /usr/local/bin/pvcontrol-old
if [ -z "$1" ]; then
    gh run download -R stephanme/pv-control -n pv-control.tar.gz
else
    gh release download "$1" -R stephanme/pv-control --pattern 'pv-control.tar.gz' --output pv-control.tar.gz
fi
mkdir -p pvcontrol && tar -xzf pv-control.tar.gz -C ./pvcontrol
~/.env/bin/pip install -r pvcontrol/requirements.txt
sudo mv /usr/local/bin/pvcontrol /usr/local/bin/pvcontrol-old
sudo mv ./pvcontrol /usr/local/bin/pvcontrol
sudo systemctl restart pvcontrol.service
