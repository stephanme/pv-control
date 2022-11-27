#! /bin/bash
set -x
# updates pvcontrol installed in /usr/local/bin
# assumes gh auth login -w

rm pv-control.tar.gz
rm -rf pvcontrol
sudo rm -rf /usr/local/bin/pvcontrol-old
gh run download -R stephanme/pv-control -n pv-control.tar.gz
mkdir -p pvcontrol && tar -xzf pv-control.tar.gz -C ./pvcontrol
pip install -r pvcontrol/requirements.txt
sudo mv /usr/local/bin/pvcontrol /usr/local/bin/pvcontrol-old
sudo mv ./pvcontrol /usr/local/bin/pvcontrol
sudo systemctl restart pvcontrol.service
