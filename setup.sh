#!/usr/bin/env bash
#
# setup.sh — install & configure the Mac monitoring stack from this repo.
#
# Idempotent: safe to re-run after editing any config. It installs the three
# Homebrew packages (if missing), deploys the configs from this repo into the
# active Homebrew prefix, applies the Grafana settings, then starts all three
# services with auto-restart (launchd KeepAlive) enabled.
#
# Usage:  ./setup.sh
#
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LA="$HOME/Library/LaunchAgents"
GRAFANA_PORT=31415

log() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
die() { printf '\033[1;31mERROR:\033[0m %s\n' "$*" >&2; exit 1; }

command -v brew >/dev/null 2>&1 || die "Homebrew not found. Install it from https://brew.sh first."
BREW="$(brew --prefix)"
ETC="$BREW/etc"

# 1 — packages -------------------------------------------------------------
log "Installing packages (idempotent)…"
for pkg in node_exporter prometheus grafana; do
  if brew list --formula "$pkg" >/dev/null 2>&1; then
    echo "    $pkg already installed"
  else
    brew install "$pkg"
  fi
done

# 2 — Prometheus -----------------------------------------------------------
log "Deploying Prometheus config…"
install -m 644 "$REPO/config/prometheus/prometheus.yml" "$ETC/prometheus.yml"
# Rewrite the baked /opt/homebrew paths to the active prefix.
sed "s#/opt/homebrew#$BREW#g" "$REPO/config/prometheus/prometheus.args" > "$ETC/prometheus.args"

# 3 — node_exporter --------------------------------------------------------
log "Deploying node_exporter config…"
install -m 644 "$REPO/config/node_exporter/node_exporter.args" "$ETC/node_exporter.args"

# 4 — Grafana provisioning -------------------------------------------------
log "Deploying Grafana provisioning…"
PROV="$ETC/grafana/provisioning"
mkdir -p "$PROV/datasources" "$PROV/dashboards/json" \
         "$PROV/plugins" "$PROV/alerting" "$PROV/notifiers"   # empty dirs silence startup errors
install -m 644 "$REPO/config/grafana/provisioning/datasources/prometheus.yml" "$PROV/datasources/prometheus.yml"
sed "s#/opt/homebrew#$BREW#g" \
    "$REPO/config/grafana/provisioning/dashboards/dashboards.yml" > "$PROV/dashboards/dashboards.yml"
rm -f "$PROV/dashboards/json/"*.json
install -m 644 "$REPO"/config/grafana/provisioning/dashboards/json/*.json "$PROV/dashboards/json/"

# 5 — Grafana settings (port, home dashboard, provisioning path) -----------
log "Applying grafana.ini settings…"
python3 "$REPO/scripts/set_ini.py" "$ETC/grafana/grafana.ini" \
  "http_port=$GRAFANA_PORT" \
  "provisioning=$PROV" \
  "default_home_dashboard_path=$PROV/dashboards/json/mac-today.json"

# 6 — services + auto-restart ----------------------------------------------
log "Starting services & enabling auto-restart…"
ensure_service() {
  local name="$1"
  brew services start "$name" >/dev/null 2>&1 || true   # creates the launchd plist if missing
  local plist="$LA/homebrew.mxcl.$name.plist"
  [ -f "$plist" ] || { echo "    WARN: $plist not found, skipping KeepAlive"; return; }
  python3 - "$plist" <<'PY'
import plistlib, sys
p = sys.argv[1]
d = plistlib.load(open(p, "rb"))
d["KeepAlive"] = True
plistlib.dump(d, open(p, "wb"))
PY
  launchctl bootout   "gui/$(id -u)" "$plist" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$plist" 2>/dev/null || true
  echo "    $name running with auto-restart"
}
ensure_service node_exporter
ensure_service prometheus
ensure_service grafana

# 7 — wait for Grafana, report --------------------------------------------
log "Waiting for Grafana…"
for _ in $(seq 1 30); do
  sleep 2
  if [ "$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$GRAFANA_PORT/api/health")" = "200" ]; then
    break
  fi
done

cat <<EOF

✅ Done. Your dashboards:
   Home (Today): http://localhost:$GRAFANA_PORT
   Monthly:      http://localhost:$GRAFANA_PORT/d/mac-monthly
   All-Time:     http://localhost:$GRAFANA_PORT/d/mac-alltime

First login is admin / admin (you'll be asked to set a new password).
EOF
