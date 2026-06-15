# Mac Monitoring

A lightweight, self-managing system monitor for macOS. Tracks **CPU, memory,
disk, load, swap and network** and stores the history so you can look at
**daily, monthly, and all-time** trends in Grafana.

Everything is version-controlled here and installed by a single idempotent
script — clone the repo on any Mac and run `./setup.sh`.

```
┌─ node_exporter ─┐     ┌─ Prometheus ─┐     ┌─ Grafana ─┐
│  reads CPU/mem/ │ --> │ stores it,   │ --> │ dashboards│
│  disk from macOS│     │ 2y retention │     │  :31415   │
│  :9100          │     │  :9090       │     │           │
└─────────────────┘     └──────────────┘     └───────────┘
   (scrapes every 5s)
```

## What's in here

| Path | What it is |
|------|------------|
| `setup.sh` | One-shot, idempotent installer/updater (see below) |
| `config/prometheus/` | `prometheus.yml` (scrape config) + `prometheus.args` (flags incl. retention) |
| `config/node_exporter/` | `node_exporter.args` (bind address) |
| `config/grafana/provisioning/` | Datasource + dashboard provider + the three dashboard JSONs |
| `scripts/gen_dashboards.py` | Regenerates the three dashboards from one panel definition |
| `scripts/set_ini.py` | Helper used by `setup.sh` to set keys in `grafana.ini` idempotently |

## How it works

- **node_exporter** runs locally and exposes raw OS metrics on `127.0.0.1:9100`.
- **Prometheus** scrapes node_exporter **every 5 seconds** and stores the
  samples on disk with **2-year / 8 GB retention** (`config/prometheus/prometheus.args`).
- **Grafana** (on **port 31415**) reads from Prometheus and renders the
  dashboards. The Prometheus datasource and the dashboards are
  *provisioned* — defined as code in `config/grafana/provisioning/` and loaded
  on startup, so there's nothing to click-configure.
- All three run as **Homebrew/launchd services** that start at login and
  **auto-restart on crash** (`KeepAlive`), set up by `setup.sh`.

Three dashboards share one layout, differing only in default time range and
they all auto-refresh every 5s:

| Dashboard | Default range | URL |
|-----------|---------------|-----|
| Mac System — Today | last 24h | `http://localhost:31415` (Home) |
| Mac System — Monthly | last 30d | `http://localhost:31415/d/mac-monthly` |
| Mac System — All Time | last 2y | `http://localhost:31415/d/mac-alltime` |

## Prerequisites

- macOS (Apple Silicon recommended)
- [Homebrew](https://brew.sh)

## Setup

```bash
git clone https://github.com/besh0y/mac-monitoring.git
cd mac-monitoring
./setup.sh
```

Then open **http://localhost:31415** — first login is `admin` / `admin`
(you'll be prompted to change it). That's it: services are installed, running,
and set to start at login on this machine.

`setup.sh` is **idempotent** — re-run it any time after editing a config to
re-deploy and restart. It detects your Homebrew prefix automatically (so it
works on Intel Macs too).

## Maintaining / customizing

**Change a setting** (scrape interval, retention, ports, panels): edit the file
under `config/`, then re-run `./setup.sh`.

**Edit dashboards** — two ways:
1. In Grafana's UI (panels are editable), then export the JSON back into
   `config/grafana/provisioning/dashboards/json/`, **or**
2. Edit `scripts/gen_dashboards.py` (one panel list drives all three
   dashboards) and regenerate:
   ```bash
   python3 scripts/gen_dashboards.py   # rewrites the three JSON files
   ./setup.sh                          # deploy + restart
   ```

Commit and push, then `git pull && ./setup.sh` on your other Macs.

## Why this stack (and not Netdata)?

Netdata is the usual "one-click" pick, but its current stable release
(2.10.3) crashes on Apple-Silicon Macs running recent macOS — a stack-buffer
overflow in its `do_macos_mach_smi` collector, which is exactly the collector
that reads CPU and RAM, so it can't simply be disabled. node_exporter (Go)
reads CPU/memory/disk reliably on the same hardware, so this stack uses it.

## Useful commands

```bash
brew services list                       # status of all three services
launchctl kickstart -k gui/$(id -u)/homebrew.mxcl.prometheus   # restart w/o losing KeepAlive
tail -f $(brew --prefix)/var/log/grafana/grafana.log           # Grafana logs
curl -s localhost:9090/api/v1/targets    # check Prometheus scrape health
```

> Note: use `launchctl kickstart` (not `brew services restart`) to restart
> node_exporter/prometheus — `brew services restart` regenerates the launchd
> plist and drops the `KeepAlive` auto-restart. Re-running `./setup.sh`
> re-applies it either way.

## Uninstall

```bash
brew services stop grafana prometheus node_exporter
brew uninstall grafana prometheus node_exporter
```

Metrics data lives in `$(brew --prefix)/var/prometheus` if you want to delete it too.
