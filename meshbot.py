#!/usr/bin/env python3
"""
MeshBot — Meshtastic Auto-Responder Bot

A lightweight bot that connects to a Meshtastic radio and responds to
keyword commands with weather, earthquake data, NWS alerts, and more.

Follows community conventions (meshing-around / 868meshbot style).
Works standalone — no Matrix, no cloud services, no API keys required.

Configuration: Copy config.example.yaml to config.yaml and edit.
"""

import json
import os
import random
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

import yaml
from pubsub import pub
from meshtastic.tcp_interface import TCPInterface
from meshtastic.serial_interface import SerialInterface

try:
    import urllib.request
    HAS_INTERNET = True
except ImportError:
    HAS_INTERNET = False

# ---------------------------
# Configuration
# ---------------------------

CONFIG_PATH = Path(__file__).parent / "config.yaml"


def load_config() -> dict:
    """Load config from YAML file or environment variables."""
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            return yaml.safe_load(f) or {}

    return {
        "connection": {
            "type": os.environ.get("MESH_CONNECTION", "tcp"),
            "host": os.environ.get("MESH_HOST", "127.0.0.1"),
            "port": int(os.environ.get("MESH_PORT", "4403")),
            "serial_port": os.environ.get("MESH_SERIAL", "/dev/ttyUSB0"),
        },
        "bot": {
            "location": os.environ.get("BOT_LOCATION", "Your City, State"),
            "nws_zone": os.environ.get("BOT_NWS_ZONE", ""),
            "quake_bounds": os.environ.get("BOT_QUAKE_BOUNDS", ""),
            "network_name": os.environ.get("BOT_NETWORK_NAME", "MeshNet"),
            "network_url": os.environ.get("BOT_NETWORK_URL", ""),
            "timezone": os.environ.get("BOT_TIMEZONE", "UTC"),
            "units": os.environ.get("BOT_UNITS", "imperial"),
            "motd": os.environ.get("BOT_MOTD", ""),
            "respond_to": os.environ.get("BOT_RESPOND_TO", "dm"),  # dm, all, channel
            "channels": [],
        },
    }


cfg = load_config()

# Connection
CONN_TYPE = cfg.get("connection", {}).get("type", "tcp")
CONN_HOST = cfg.get("connection", {}).get("host", "127.0.0.1")
CONN_PORT = cfg.get("connection", {}).get("port", 4403)
CONN_SERIAL = cfg.get("connection", {}).get("serial_port", "/dev/ttyUSB0")

# Bot settings
BOT_LOCATION = cfg.get("bot", {}).get("location", "Unknown")
BOT_NWS_ZONE = cfg.get("bot", {}).get("nws_zone", "")
BOT_QUAKE_BOUNDS = cfg.get("bot", {}).get("quake_bounds", "")
BOT_NETWORK_NAME = cfg.get("bot", {}).get("network_name", "MeshNet")
BOT_NETWORK_URL = cfg.get("bot", {}).get("network_url", "")
BOT_TIMEZONE = cfg.get("bot", {}).get("timezone", "UTC")
BOT_UNITS = cfg.get("bot", {}).get("units", "imperial")
BOT_MOTD = cfg.get("bot", {}).get("motd", "")
BOT_RESPOND_TO = cfg.get("bot", {}).get("respond_to", "dm")
BOT_CHANNELS = cfg.get("bot", {}).get("channels", [])

UNIT_FLAG = "&u" if BOT_UNITS == "imperial" else "&m"
MESHTASTIC_BIN = shutil.which("meshtastic") or "meshtastic"

# ---------------------------
# Dedup
# ---------------------------

class Deduper:
    """Prevents responding to the same message twice within TTL."""
    def __init__(self, ttl: int = 30):
        self.ttl = ttl
        self.cache: Dict[str, float] = {}

    def seen(self, key: str) -> bool:
        t = self.cache.get(key)
        if t and time.time() - t < self.ttl:
            return True
        return False

    def mark(self, key: str):
        self.cache[key] = time.time()
        # Prune old entries
        cutoff = time.time() - self.ttl * 2
        self.cache = {k: v for k, v in self.cache.items() if v > cutoff}


dedup = Deduper(30)

# ---------------------------
# Bot Commands
# ---------------------------

def _fetch(url: str, headers: dict = None, timeout: int = 10) -> str:
    """Fetch URL content as string."""
    hdrs = headers or {"User-Agent": "meshbot/1.0"}
    req = urllib.request.Request(url, headers=hdrs)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode().strip()


def cmd_weather() -> str:
    """Current weather from wttr.in."""
    try:
        loc = BOT_LOCATION.replace(" ", "+")
        return f"WX {BOT_LOCATION}: {_fetch(f'https://wttr.in/{loc}?format=%c+%t+%h+%w+%P{UNIT_FLAG}')}"
    except Exception as e:
        return f"WX unavailable: {e}"


def cmd_forecast() -> str:
    """3-day weather forecast."""
    try:
        loc = BOT_LOCATION.replace(" ", "+")
        result = _fetch(f"https://wttr.in/{loc}?format=%c+%t(%f)+%w+%p{UNIT_FLAG}&T")
        return result[:200]
    except Exception as e:
        return f"Forecast unavailable: {e}"


def cmd_sun() -> str:
    """Sunrise and sunset times."""
    try:
        loc = BOT_LOCATION.replace(" ", "+")
        line = _fetch(f"https://wttr.in/{loc}?format=%S+%s{UNIT_FLAG}")
        parts = line.split()
        if len(parts) >= 2:
            return f"☀️ {BOT_LOCATION} — Sunrise: {parts[0]} / Sunset: {parts[1]}"
        return f"☀️ {BOT_LOCATION} — {line}"
    except Exception as e:
        return f"Sun data unavailable: {e}"


def cmd_alerts() -> str:
    """Active NWS weather alerts."""
    if not BOT_NWS_ZONE:
        return "⚠️ NWS alerts not configured"
    try:
        data = json.loads(_fetch(
            f"https://api.weather.gov/alerts/active?zone={BOT_NWS_ZONE}",
            headers={"User-Agent": "meshbot/1.0", "Accept": "application/geo+json"}
        ))
        features = data.get("features", [])
        if not features:
            return "⚠️ No active weather alerts"
        lines = ["⚠️ Active alerts:"]
        for f in features[:3]:
            p = f["properties"]
            headline = p.get("headline", p.get("event", "Unknown"))
            lines.append(headline[:120])
        return "\n".join(lines)
    except Exception as e:
        return f"Alert check failed: {e}"


def cmd_earthquake() -> str:
    """Recent earthquakes from USGS."""
    if not BOT_QUAKE_BOUNDS:
        return "🌍 Earthquake monitoring not configured"
    try:
        parts = [p.strip() for p in BOT_QUAKE_BOUNDS.split(",")]
        minlat, maxlat, minlon, maxlon = parts
        url = (f"https://earthquake.usgs.gov/fdsnws/event/1/query?"
               f"format=geojson&minlatitude={minlat}&maxlatitude={maxlat}"
               f"&minlongitude={minlon}&maxlongitude={maxlon}"
               f"&minmagnitude=2.5&orderby=time&limit=3")
        data = json.loads(_fetch(url))
        features = data.get("features", [])
        if not features:
            return "🌍 No M2.5+ earthquakes in area (7 days)"
        lines = ["🌍 Recent quakes:"]
        for f in features[:3]:
            p = f["properties"]
            dt = datetime.fromtimestamp(p.get("time", 0) / 1000)
            lines.append(f"M{p.get('mag','?')} {p.get('place','?')} ({dt.strftime('%b %d %I:%M%p')})")
        return "\n".join(lines)
    except Exception as e:
        return f"Quake data unavailable: {e}"


def cmd_nodes() -> str:
    """Active mesh node count."""
    try:
        host_flag = ["--host", CONN_HOST] if CONN_TYPE == "tcp" else ["--port", CONN_SERIAL]
        result = subprocess.run(
            [MESHTASTIC_BIN] + host_flag + ["--nodes"],
            capture_output=True, text=True, timeout=15
        )
        lines = result.stdout.strip().split("\n")
        node_lines = [l for l in lines if "│" in l and "User" not in l and "───" not in l]
        count = len(node_lines)
        names = []
        for l in node_lines:
            parts = [p.strip() for p in l.split("│") if p.strip()]
            if len(parts) >= 2:
                names.append(parts[1][:20])
        if names:
            msg = f"📡 {count} nodes: {', '.join(names[:8])}"
            if count > 8:
                msg += f" +{count-8} more"
            return msg
        return f"📡 {count} nodes seen"
    except Exception as e:
        return f"📡 Node check failed: {e}"


def cmd_time() -> str:
    """Current local time."""
    try:
        from zoneinfo import ZoneInfo
        now = datetime.now(ZoneInfo(BOT_TIMEZONE))
        return f"🕐 {now.strftime('%I:%M %p %Z — %A, %B %d')}"
    except Exception:
        now = datetime.now()
        return f"🕐 {now.strftime('%I:%M %p — %A, %B %d')}"


def cmd_joke() -> str:
    """Random dad joke."""
    try:
        joke = _fetch("https://icanhazdadjoke.com/", headers={
            "Accept": "text/plain", "User-Agent": "meshbot/1.0"
        })
        return f"😄 {joke[:200]}"
    except Exception:
        return "😄 Couldn't fetch a joke right now."


def cmd_fortune() -> str:
    """Random fortune/quote."""
    try:
        result = subprocess.run(["fortune", "-s"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0 and result.stdout.strip():
            return f"🔮 {result.stdout.strip()[:200]}"
    except Exception:
        pass
    quotes = [
        "The best time to plant a tree was 20 years ago. The second best time is now.",
        "Not all who wander are lost. — Tolkien",
        "In the middle of difficulty lies opportunity. — Einstein",
        "Stay hungry, stay foolish. — Steve Jobs",
        "It always seems impossible until it's done. — Mandela",
    ]
    return f"🔮 {random.choice(quotes)}"


def cmd_info() -> str:
    """Network MOTD / info."""
    if BOT_MOTD:
        return BOT_MOTD
    lines = [f"📡 {BOT_NETWORK_NAME}"]
    if BOT_NETWORK_URL:
        lines.append(f"Map: {BOT_NETWORK_URL}")
    lines.append(f"Bot active | {BOT_LOCATION}")
    lines.append("Type 'cmd' for commands")
    return "\n".join(lines)


def cmd_list() -> str:
    """List available commands."""
    return (
        f"🤖 {BOT_NETWORK_NAME} Bot:\n"
        "wx — weather | forecast — 3-day\n"
        "alerts — NWS alerts | sun — rise/set\n"
        "quake — earthquakes | nodes — mesh nodes\n"
        "ping — pong | test — radio check\n"
        "time — local time | info — network info\n"
        "joke — dad joke | fortune — quote"
    )


# Command dispatch table
COMMANDS = {
    r"(cmd|commands)": cmd_list,
    r"(wx|weather)": cmd_weather,
    r"forecast": cmd_forecast,
    r"(alerts?|nws)": cmd_alerts,
    r"sun(rise|set)?": cmd_sun,
    r"(quake|eq|earthquake)": cmd_earthquake,
    r"nodes": cmd_nodes,
    r"time": cmd_time,
    r"(info|motd)": cmd_info,
    r"joke": cmd_joke,
    r"fortune": cmd_fortune,
}


def handle_message(text: str, from_id: str = "") -> Optional[str]:
    """Process a message and return a response, or None if not a command."""
    body = text.lower().strip()

    # Simple commands
    if re.fullmatch(r"ping[.!?\s]*", body):
        return "pong 🏓"
    if re.fullmatch(r"test[.!?\s]*", body):
        return "roger that, reading you loud and clear ✅"
    if re.fullmatch(r"whoami[.!?\s]*", body):
        return f"👤 You are: {from_id}"

    # Dispatch table commands
    for pattern, handler in COMMANDS.items():
        if re.fullmatch(pattern + r"[.!?\s]*", body):
            return handler()

    return None


# ---------------------------
# Meshtastic Packet Handler
# ---------------------------

interface: Optional[object] = None


def on_receive(packet, iface):
    """Handle incoming Meshtastic packets."""
    decoded = (packet or {}).get("decoded") or {}
    text = decoded.get("text")
    if not text:
        return

    from_id = packet.get("fromId", "unknown")
    to_id = packet.get("toId", "")
    channel = packet.get("channel", 0)

    # Determine if we should respond
    is_dm = to_id and to_id != "^all"
    is_broadcast = to_id == "^all" or not to_id

    if BOT_RESPOND_TO == "dm" and not is_dm:
        return
    if BOT_RESPOND_TO == "channel" and BOT_CHANNELS and channel not in BOT_CHANNELS:
        return

    # Dedup
    dkey = f"{from_id}:{text}"
    if dedup.seen(dkey):
        return
    dedup.mark(dkey)

    # Parse message — check for bridged message format
    # e.g., "📡 Mesh [ch0] !abc123 (snr=10): wx"
    actual_text = text
    match = re.match(r"📡\s*Mesh.*?:\s*(.+)", text, re.DOTALL)
    if match:
        actual_text = match.group(1).strip()

    # Also handle "(username) message" prefix from Matrix bridge
    match2 = re.match(r"\([\w.-]+\)\s+(.+)", actual_text, re.DOTALL)
    if match2:
        actual_text = match2.group(1).strip()

    print(f"[RX] {from_id} → {to_id or 'broadcast'} ch{channel}: {actual_text}")

    response = handle_message(actual_text, from_id)
    if not response:
        return

    print(f"[TX] → {from_id}: {response[:80]}...")

    try:
        if is_dm:
            iface.sendText(response, destinationId=from_id, wantAck=False)
        else:
            iface.sendText(response, channelIndex=channel, wantAck=False)
    except Exception as e:
        print(f"[ERROR] Failed to send: {e}")


# ---------------------------
# Main
# ---------------------------

def main():
    global interface

    print(f"🤖 MeshBot starting — {BOT_NETWORK_NAME}")
    print(f"   Location: {BOT_LOCATION} | Units: {BOT_UNITS}")
    print(f"   Respond to: {BOT_RESPOND_TO}")

    if CONN_TYPE == "serial":
        print(f"   Connection: Serial {CONN_SERIAL}")
        interface = SerialInterface(CONN_SERIAL)
    else:
        print(f"   Connection: TCP {CONN_HOST}:{CONN_PORT}")
        interface = TCPInterface(hostname=CONN_HOST, portNumber=CONN_PORT)

    pub.subscribe(on_receive, "meshtastic.receive")

    print("✅ MeshBot is LIVE — type 'cmd' on mesh to see commands")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n👋 MeshBot shutting down")
        interface.close()


if __name__ == "__main__":
    main()
