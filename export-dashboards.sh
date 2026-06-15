#!/usr/bin/env bash
#
# export-dashboards.sh — pull the live dashboards from Grafana back into this
# repo, so UI edits become version-controlled.
#
# Why this is needed: the dashboards are *provisioned* with allowUiUpdates=true,
# which means edits you make in the Grafana UI are saved to Grafana's database,
# NOT back to the JSON files in this repo. This script fetches the current
# version of each dashboard from the API and overwrites the repo JSON, after
# which you can commit + push.
#
# Auth (the admin password was changed on first login, so pick one):
#   export GRAFANA_TOKEN=<service-account-token>     # recommended
#       Create one in Grafana: Administration → Users and access →
#       Service accounts → Add service account (Viewer role) → Add token.
#   — or —
#   export GRAFANA_USER=admin GRAFANA_PASS=<your-password>
#
# Usage:  ./export-dashboards.sh
#
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
JSON_DIR="$REPO/config/grafana/provisioning/dashboards/json"
GRAFANA_URL="${GRAFANA_URL:-http://localhost:31415}"

# Build auth args.
if [ -n "${GRAFANA_TOKEN:-}" ]; then
  AUTH=(-H "Authorization: Bearer $GRAFANA_TOKEN")
elif [ -n "${GRAFANA_USER:-}" ]; then
  AUTH=(-u "${GRAFANA_USER}:${GRAFANA_PASS:-}")
else
  AUTH=(-u "admin:admin")
fi

die() { printf '\033[1;31mERROR:\033[0m %s\n' "$*" >&2; exit 1; }
log() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }

[ -d "$JSON_DIR" ] || die "dashboard dir not found: $JSON_DIR"

# Quick auth/connectivity check.
code="$(curl -s -o /dev/null -w '%{http_code}' "${AUTH[@]}" "$GRAFANA_URL/api/search?type=dash-db" || true)"
case "$code" in
  200) ;;
  401|403) die "Grafana auth failed (HTTP $code). Set GRAFANA_TOKEN, or GRAFANA_USER/GRAFANA_PASS. See header of this script." ;;
  000) die "Can't reach Grafana at $GRAFANA_URL — is it running? (brew services list)" ;;
  *)   die "Unexpected response from Grafana (HTTP $code)." ;;
esac

shopt -s nullglob
files=("$JSON_DIR"/*.json)
[ ${#files[@]} -gt 0 ] || die "no dashboard JSON files in $JSON_DIR to refresh"

log "Exporting dashboards from $GRAFANA_URL"
exported=0
for f in "${files[@]}"; do
  uid="$(python3 -c "import json,sys;print(json.load(open(sys.argv[1])).get('uid',''))" "$f")"
  [ -n "$uid" ] || { echo "    skip $(basename "$f") (no uid)"; continue; }

  resp="$(curl -s "${AUTH[@]}" "$GRAFANA_URL/api/dashboards/uid/$uid" || true)"
  # Clean: keep the dashboard model, drop instance-specific fields, normalize.
  if printf '%s' "$resp" | python3 "$REPO/scripts/clean_dashboard.py" "$f" "$uid"; then
    exported=$((exported + 1))
  else
    echo "    WARN: failed to export uid=$uid"
    continue
  fi
done

log "Exported $exported dashboard(s)."
echo
echo "Review and commit:"
echo "  cd $REPO && git diff --stat && git add -A && git commit -m 'Update dashboards from Grafana'"
echo
echo "Note: this overwrites the generated JSON. If you later edit scripts/gen_dashboards.py"
echo "and regenerate, it will overwrite these UI exports — pick one source of truth per dashboard."
