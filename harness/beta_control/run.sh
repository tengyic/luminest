#!/bin/sh
# Start the Luminest closed-beta control server on a small device / local Mac.
# Standard library only -- no pip install, no database server.
#
#   LUMINEST_BETA_ADMIN_TOKEN=choose-a-long-random-string sh run.sh
#
# The server binds 0.0.0.0:$PORT (default 8788), so an iPad or another Mac on the
# same LAN can reach http://<this-mac-ip>:8788 . For an internet link, put it
# behind a reverse proxy / tunnel (or publish with the sites deploy, which injects
# PORT). All state lives in beta.db next to this script.
set -eu
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
: "${PORT:=8788}"
: "${LUMINEST_SITE_DIR:=$HERE/site}"
export PORT LUMINEST_SITE_DIR
exec python3 "$HERE/server.py"
