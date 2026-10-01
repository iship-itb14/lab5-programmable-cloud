#!/bin/bash
# Runs as root on every boot of the Part 1 VM (passed as the "startup-script" metadata key).
# No `set -x`: the repo URL may contain a GitHub token and would be echoed to the serial log.
set -euo pipefail

MD="http://metadata.google.internal/computeMetadata/v1/instance/attributes"
md() { curl -sf -H "Metadata-Flavor: Google" "$MD/$1" || true; }

APP_ROOT=/opt/app
PORT=5000

# Later boots, and VMs built from the Part 2 image: the app is already installed
# and enabled as a systemd service, so just make sure it is running.
if systemctl is-enabled --quiet webapp 2>/dev/null; then
  systemctl start webapp
  exit 0
fi

REPO_URL="$(md repo-url)"
APP_SUBDIR="$(md app-subdir)"
if [ -z "$REPO_URL" ]; then
  echo "startup-script: no repo-url metadata; nothing to install" >&2
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y git python3 python3-venv python3-pip

rm -rf "$APP_ROOT"
git clone --depth 1 "$REPO_URL" "$APP_ROOT"
# Strip any credentials from the saved remote so the token is not left on disk
# (or baked into the image built in Part 2).
git -C "$APP_ROOT" remote set-url origin "$(echo "$REPO_URL" | sed -E 's#//[^@/]+@#//#')"

APP_DIR="$APP_ROOT/$APP_SUBDIR"
python3 -m venv "$APP_ROOT/venv"
"$APP_ROOT/venv/bin/pip" install --upgrade pip

# ADJUST for your class repo if it installs differently (e.g. pip install -r requirements.txt).
"$APP_ROOT/venv/bin/pip" install -e "$APP_DIR"

# ADJUST: one-time app setup. The Flask tutorial ("flaskr") needs its database initialized.
cd "$APP_DIR"
"$APP_ROOT/venv/bin/flask" --app flaskr init-db

# Run the app as a service so it survives reboots and starts automatically on cloned VMs.
cat > /etc/systemd/system/webapp.service <<EOF
[Unit]
Description=Assignment web application
After=network-online.target
Wants=network-online.target

[Service]
WorkingDirectory=$APP_DIR
# ADJUST: the command that starts your app, listening on 0.0.0.0:$PORT
ExecStart=$APP_ROOT/venv/bin/flask --app flaskr run --host 0.0.0.0 --port $PORT
Restart=always

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now webapp
echo "startup-script: app installed and listening on port $PORT"
