#!/bin/bash
# VM1 startup script (Part 3): fetch Part 1's code and the service-account key from
# metadata, then run Part 1 to create VM2. No `set -x`, so secrets stay out of the log.
set -euo pipefail

MD="http://metadata.google.internal/computeMetadata/v1/instance/attributes"
md() { curl -sf -H "Metadata-Flavor: Google" "$MD/$1"; }

WORK=/srv/launcher
[ -f "$WORK/done" ] && exit 0   # only launch VM2 once, not on every reboot

mkdir -p "$WORK"
cd "$WORK"

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y python3 python3-venv
python3 -m venv venv
venv/bin/pip install --upgrade pip
venv/bin/pip install google-cloud-compute google-auth

md part1-py > part1.py
md vm2-startup-script > startup-script.sh
umask 077
md service-credentials > service-credentials.json

GOOGLE_APPLICATION_CREDENTIALS="$WORK/service-credentials.json" \
  venv/bin/python part1.py \
    --project "$(md project)" \
    --zone "$(md zone)" \
    --name "$(md vm2-name)" \
    --repo "$(md repo-url)" \
    --app-subdir "$(md app-subdir || true)" \
    --machine-type "$(md machine-type || echo f1-micro)" \
    --startup-script "$WORK/startup-script.sh"

shred -u service-credentials.json   # key no longer needed on disk
touch done
echo "vm1-startup: VM2 created"
