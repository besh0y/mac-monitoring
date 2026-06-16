import json, os

DS = {"type": "prometheus", "uid": "prometheus"}
RI = "$__rate_interval"

def ts(title, x, y, w, h, targets, unit, *, stack=False, fillOpacity=10, minv=None, maxv=None, desc=""):
    # spanNulls=False: don't interpolate across data gaps. With a 5s scrape and
    # Prometheus's 5m staleness, brief hiccups stay connected but real inactivity
    # (sleep / machine off, >5m) renders as an honest break instead of a fake line.
    fc_custom = {"drawStyle": "line", "lineInterpolation": "smooth", "fillOpacity": fillOpacity,
                 "showPoints": "never", "lineWidth": 2, "spanNulls": False}
    if stack:
        fc_custom["stacking"] = {"mode": "normal", "group": "A"}
    defaults = {"unit": unit, "custom": fc_custom}
    if minv is not None: defaults["min"] = minv
    if maxv is not None: defaults["max"] = maxv
    return {
        "type": "timeseries", "title": title, "datasource": DS, "description": desc,
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "fieldConfig": {"defaults": defaults, "overrides": []},
        "options": {"legend": {"displayMode": "list", "placement": "bottom", "calcs": ["lastNotNull", "max"]},
                    "tooltip": {"mode": "multi", "sort": "desc"}},
        "targets": targets,
    }

def stat(title, x, y, w, h, expr, unit, thresholds, desc=""):
    return {
        "type": "stat", "title": title, "datasource": DS, "description": desc,
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "fieldConfig": {"defaults": {"unit": unit, "thresholds": {"mode": "absolute", "steps": thresholds},
                                     "color": {"mode": "thresholds"}}, "overrides": []},
        "options": {"colorMode": "value", "graphMode": "area", "justifyMode": "auto",
                    "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
                    "textMode": "auto"},
        "targets": [{"expr": expr, "refId": "A", "datasource": DS}],
    }

def t(expr, legend, ref="A"):
    return {"expr": expr, "legendFormat": legend, "refId": ref, "datasource": DS}

PCT_TH = [{"color": "green", "value": None}, {"color": "yellow", "value": 70}, {"color": "red", "value": 90}]
LOAD_TH = [{"color": "green", "value": None}, {"color": "yellow", "value": 8}, {"color": "red", "value": 16}]

CPU_BUSY = f'100 * (1 - avg(rate(node_cpu_seconds_total{{mode="idle"}}[{RI}])))'
# macOS "Memory Used" (matches Activity Monitor): wired + compressed + app memory,
# where app memory ≈ internal (anonymous) pages minus purgeable. "active" is not
# used here because it includes reclaimable file-cache, which understates pressure.
MEM_USED_PCT = ('100 * (node_memory_wired_bytes + node_memory_compressed_bytes '
                '+ node_memory_internal_bytes - node_memory_purgeable_bytes) '
                '/ node_memory_total_bytes')
DISK = 'mountpoint="/System/Volumes/Data"'
DISK_USED_PCT = f'100 * (1 - node_filesystem_avail_bytes{{{DISK}}} / node_filesystem_size_bytes{{{DISK}}})'

MEM_DESC = ("macOS “Memory Used” = wired + compressed + app memory "
            "(internal − purgeable) ÷ total — matches Activity Monitor. "
            "“active” is excluded because it includes reclaimable file cache. "
            "Raw values verified against vm_stat.")
DISK_DESC = ("Used % = 1 − avail/size. Reads ~2 pp above Finder/df: on APFS, "
             "node_exporter reports free == avail and can’t see the container-"
             "shared/purgeable space df excludes, so Finder’s figure isn’t "
             "reproducible from the metrics. Size & avail themselves match df exactly.")

def build_panels():
    p = []
    # Row 0 — at-a-glance stats
    p.append(stat("CPU", 0, 0, 6, 4, CPU_BUSY, "percent", PCT_TH))
    p.append(stat("Memory", 6, 0, 6, 4, MEM_USED_PCT, "percent", PCT_TH, desc=MEM_DESC))
    p.append(stat("Disk (Data vol)", 12, 0, 6, 4, DISK_USED_PCT, "percent", PCT_TH, desc=DISK_DESC))
    p.append(stat("Load (1m)", 18, 0, 6, 4, "node_load1", "short", LOAD_TH))
    # Row 1 — CPU % and Memory %
    p.append(ts("CPU Usage %", 0, 4, 12, 8, [t(CPU_BUSY, "cpu busy")], "percent", minv=0, maxv=100))
    p.append(ts("Memory Usage %", 12, 4, 12, 8, [t(MEM_USED_PCT, "memory used")], "percent", minv=0, maxv=100, desc=MEM_DESC))
    # Row 2 — CPU by mode, Memory breakdown bytes
    p.append(ts("CPU by mode", 0, 12, 12, 8,
                [t(f'avg by (mode)(rate(node_cpu_seconds_total{{mode!="idle"}}[{RI}])) * 100', "{{mode}}")],
                "percent", stack=True, fillOpacity=30))
    p.append(ts("Memory breakdown", 12, 12, 12, 8, [
        t("node_memory_wired_bytes", "wired", "A"),
        t("node_memory_active_bytes", "active", "B"),
        t("node_memory_compressed_bytes", "compressed", "C"),
        t("node_memory_inactive_bytes", "inactive", "D"),
        t("node_memory_purgeable_bytes", "purgeable", "E"),
        t("node_memory_free_bytes", "free", "F"),
    ], "bytes", stack=True, fillOpacity=30))
    # Row 3 — Disk I/O, Network
    p.append(ts("Disk I/O", 0, 20, 12, 8, [
        t(f'sum(rate(node_disk_read_bytes_total[{RI}]))', "read", "A"),
        t(f'-sum(rate(node_disk_written_bytes_total[{RI}]))', "written", "B"),
    ], "binBps"))
    p.append(ts("Network throughput", 12, 20, 12, 8, [
        t(f'sum(rate(node_network_receive_bytes_total{{device!~"lo.*"}}[{RI}]))', "received", "A"),
        t(f'-sum(rate(node_network_transmit_bytes_total{{device!~"lo.*"}}[{RI}]))', "sent", "B"),
    ], "binBps"))
    # Row 4 — Load, Swap
    p.append(ts("Load average", 0, 28, 12, 8, [
        t("node_load1", "1m", "A"), t("node_load5", "5m", "B"), t("node_load15", "15m", "C"),
    ], "short"))
    p.append(ts("Swap used", 12, 28, 12, 8, [
        t("node_memory_swap_used_bytes", "swap used", "A"),
        t("node_memory_swap_total_bytes", "swap total", "B"),
    ], "bytes"))
    for i, panel in enumerate(p, 1):
        panel["id"] = i
    return p

VARIANTS = [
    ("mac-today",    "Mac System — Today",    "now-24h", "5s"),
    ("mac-monthly",  "Mac System — Monthly",  "now-30d", "5s"),
    ("mac-alltime",  "Mac System — All Time", "now-2y",  "5s"),
]

# Write into this repo's provisioning tree (deployed to Grafana by setup.sh).
_here = os.path.dirname(os.path.abspath(__file__))
out_dir = os.path.abspath(os.path.join(_here, "..", "config", "grafana",
                                        "provisioning", "dashboards", "json"))
os.makedirs(out_dir, exist_ok=True)
for uid, title, frm, refresh in VARIANTS:
    dash = {
        "uid": uid, "title": title, "schemaVersion": 39, "version": 1,
        "editable": True, "refresh": refresh, "tags": ["mac", "system"],
        "time": {"from": frm, "to": "now"},
        "timepicker": {}, "templating": {"list": []},
        "annotations": {"list": []},
        "panels": build_panels(),
    }
    with open(os.path.join(out_dir, uid + ".json"), "w") as f:
        json.dump(dash, f, indent=2)
    print("wrote", uid, "->", title, f"(from={frm})")
