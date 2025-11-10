#!/usr/bin/env python3
"""
Lightweight dashboard API to inspect and control selected Docker containers and
to expose basic host system metrics (disk/RAM/CPU). Intended to run *inside* a
container with:
  - Host /proc mounted at /hostproc (or another path via PSUTIL_PROCFS_PATH)
  - Host filesystem (or a root drive) mounted at /hostfs (read-only is fine)
  - Docker socket mounted at /var/run/docker.sock (read-only is fine for status)

Endpoints:
  GET  /api/status               -> per-service state + raw docker status/health
  POST /api/service/<key>/<action>  (action: start|stop|restart)
  GET  /api/sysinfo              -> disk/ram/cpu metrics from the host
"""

from __future__ import annotations

import os
import time
from typing import Dict, Any, Tuple

# Ensure psutil reads host /proc instead of container's /proc
os.environ.setdefault("PSUTIL_PROCFS_PATH", "/hostproc")

import psutil  # type: ignore
from flask import Flask, jsonify, abort, make_response
import docker  # type: ignore
from docker.errors import NotFound, APIError

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------

app = Flask(__name__)
docker_client = docker.from_env()

# Comma-separated whitelist of service *container names* allowed to be exposed.
# Example: SB_ALLOWED="qbittorrent,prowlarr,sonarr,radarr,joal,syncthing,caddy,auth,vpn"
def _parse_allowed(env_value: str | None) -> set[str]:
    raw = env_value or "qbittorrent,prowlarr,sonarr,radarr,joal,syncthing,caddy,auth,vpn"
    return {item.strip() for item in raw.split(",") if item.strip()}

ALLOWED: set[str] = _parse_allowed(os.environ.get("SB_ALLOWED"))

# Map dashboard "keys" to Docker container names. By default key == container name.
SERVICES: Dict[str, Dict[str, str]] = {
    "qbittorrent": {"container": "qbittorrent"},
    "prowlarr": {"container": "prowlarr"},
    "sonarr": {"container": "sonarr"},
    "radarr": {"container": "radarr"},
    "joal": {"container": "joal"},
    "syncthing": {"container": "syncthing"},
    # Infra (optionally displayed)
    "caddy": {"container": "caddy"},
    "auth": {"container": "auth"},
    "vpn": {"container": "vpn"},
}

# Normalize Docker container states to a small, UI-friendly set.
HEALTH_MAP: Dict[str, str] = {
    "running": "active",
    "created": "inactive",
    "restarting": "activating",
    "removing": "inactive",
    "paused": "inactive",
    "exited": "inactive",
    "dead": "failed",
}

HOSTFS_PATH = "/hostfs"  # mount a host filesystem root here (read-only is fine)

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def _map_status(state: str, health: str | None) -> str:
    """
    Map Docker state + (optional) health into a compact status string.
    Health overrides state when present.
    """
    mapped = HEALTH_MAP.get(state, "unknown")
    if health:
        if health == "healthy":
            return "active"
        if health == "unhealthy":
            return "failed"
    return mapped


def _container_status(container_name: str) -> Tuple[str, Dict[str, Any]]:
    """
    Return (mapped_status, raw_dict) for a container by name.
    If the container does not exist, returns ("unknown", {}).
    """
    try:
        c = docker_client.containers.get(container_name)
    except NotFound:
        return "unknown", {}

    state = getattr(c, "status", None)  # e.g. "running"
    health = c.attrs.get("State", {}).get("Health", {}).get("Status")
    mapped = _map_status(state or "unknown", health)
    raw = {"status": state, "health": health}
    return mapped, raw


def _json_error(status_code: int, message: str):
    """Return a JSON error with the given HTTP status code."""
    payload = {"ok": False, "error": {"code": status_code, "message": message}}
    return make_response(jsonify(payload), status_code)


# -----------------------------------------------------------------------------
# Routes
# -----------------------------------------------------------------------------

@app.get("/api/status")
def status():
    """
    Return per-service status for all SERVICES whose container name is in ALLOWED.
    Example:
      {
        "qbittorrent": {"state":"active","raw":{"status":"running","health":"healthy"}},
        "radarr": {"state":"inactive","raw":{"status":"exited","health":null}},
        ...
      }
    """
    out: Dict[str, Dict[str, Any]] = {}
    for key, meta in SERVICES.items():
        name = meta["container"]
        if name not in ALLOWED:
            continue
        mapped, raw = _container_status(name)
        if raw:
            out[key] = {"state": mapped, "raw": raw}
        else:
            out[key] = {"state": "unknown"}
    return jsonify(out)


@app.post("/api/service/<key>/<action>")
def service_action(key: str, action: str):
    """
    Control an allowed service: start|stop|restart.
    - 400 for invalid action
    - 404 for unknown service key
    - 403 if the resolved container is not in ALLOWED
    - 404 if container not found by Docker
    - 502 for Docker API errors
    """
    if action not in {"restart", "start", "stop"}:
        return _json_error(400, "Invalid action (allowed: start, stop, restart).")

    meta = SERVICES.get(key)
    if not meta:
        return _json_error(404, f"Unknown service key: {key}")

    name = meta["container"]
    if name not in ALLOWED:
        return _json_error(403, f"Container '{name}' is not allowed.")

    try:
        c = docker_client.containers.get(name)
    except NotFound:
        return _json_error(404, f"Container '{name}' not found.")

    try:
        if action == "restart":
            c.restart()
        elif action == "start":
            c.start()
        elif action == "stop":
            c.stop()
    except APIError as e:
        return _json_error(502, f"Docker API error while '{action}' on '{name}': {e.explanation or str(e)}")

    # Small delay to let state propagate before the client re-polls status.
    time.sleep(0.2)
    return jsonify({"ok": True})


@app.get("/api/sysinfo")
def sysinfo():
    """
    Return basic system metrics from the host:
      - disk usage for HOSTFS_PATH
      - RAM usage (from host /proc via psutil)
      - CPU percentage (short sample) and load averages
    """
    # Disk usage (HOSTFS_PATH should be a mount of the host filesystem root)
    try:
        du = psutil.disk_usage(f"{HOSTFS_PATH}/")
    except FileNotFoundError:
        return _json_error(500, f"Host filesystem mount not found at {HOSTFS_PATH}/")
    except Exception as e:
        return _json_error(500, f"Failed to read disk usage: {e}")

    # RAM and CPU from host /proc (psutil respects PSUTIL_PROCFS_PATH)
    try:
        vm = psutil.virtual_memory()
        cpu_pct = psutil.cpu_percent(interval=0.1)
    except Exception as e:
        return _json_error(500, f"Failed to read RAM/CPU stats: {e}")

    # Load averages: prefer os.getloadavg(); fallback to reading /hostproc/loadavg
    load1 = load5 = load15 = None
    try:
        load1, load5, load15 = os.getloadavg()
    except Exception:
        try:
            procfs = os.environ.get("PSUTIL_PROCFS_PATH", "/hostproc")
            with open(os.path.join(procfs, "loadavg"), "r") as f:
                parts = f.read().split()
                load1, load5, load15 = map(float, parts[:3])
        except Exception:
            # Keep None if not available (e.g., on non-Unix systems)
            pass

    return jsonify(
        {
            "disk": {
                "path": HOSTFS_PATH,
                "total": du.total,
                "used": du.used,
                "free": du.free,
                "percent": round(du.percent, 1),
            },
            "ram": {
                "total": vm.total,
                "used": vm.used,
                "free": vm.available,
                "percent": round(vm.percent, 1),
            },
            "cpu": {
                "percent": round(cpu_pct, 1),
                "load1": load1,
                "load5": load5,
                "load15": load15,
            },
        }
    )


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    # Bind to loopback by default. Change to "0.0.0.0" if you need external access.
    app.run(host="127.0.0.1", port=5005)
