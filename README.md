# 🤖 MeshBot — Meshtastic Auto-Responder

A lightweight Python bot for [Meshtastic](https://meshtastic.org/) mesh radios. Responds to keyword commands with weather, earthquake data, NWS alerts, and more — all over the mesh network.

No cloud services. No API keys. No Matrix required. Just a radio and a computer.

Built for [OKMesh](https://okmesh.org) — Oklahoma's Meshtastic community.

## Features

### Bot Commands

Type `cmd` on the mesh to discover all commands:

| Command | Description |
|---------|-------------|
| `cmd` / `commands` | List all available commands |
| `wx` / `weather` | Current weather (temp, humidity, wind, pressure) |
| `forecast` | 3-day weather forecast |
| `alerts` / `nws` | Active NWS weather alerts for your area |
| `sun` / `sunrise` / `sunset` | Sunrise and sunset times |
| `quake` / `eq` | Recent earthquakes from USGS |
| `nodes` | Active mesh node count and names |
| `ping` | Connectivity test ("pong 🏓") |
| `test` | Radio check confirmation |
| `time` | Current local time |
| `whoami` | Show sender's node ID |
| `info` / `motd` | Network info and map URL |
| `joke` | Random dad joke |
| `fortune` | Random quote |

### Design Philosophy

- **Low bandwidth** — responses are kept under 200 chars for reliable mesh delivery
- **No API keys** — all data sources are free public APIs
- **DM-first** — defaults to only responding to direct messages (won't spam channels)
- **Bridge-aware** — recognizes messages relayed through Matrix/Discord bridges
- **Community conventions** — uses `cmd` for bot discovery (compatible with meshing-around, 868meshbot)

## Quick Start

### Prerequisites

- Python 3.10+
- A Meshtastic radio (TCP/WiFi or USB serial)
- Internet connection (for weather/earthquake APIs)

### Installation

```bash
git clone https://github.com/dakotasnapshot/meshbot.git
cd meshbot

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp config.example.yaml config.yaml
# Edit config.yaml with your radio IP and location
```

### Configuration

Edit `config.yaml`:

```yaml
connection:
  type: "tcp"                    # or "serial"
  host: "192.168.1.100"         # radio IP
  port: 4403

bot:
  location: "Cushing, OK"       # for weather commands
  nws_zone: "OKC081"            # NWS alert zone
  quake_bounds: "33.5, 37.5, -103, -94.5"  # USGS area
  network_name: "OKMesh"
  timezone: "America/Chicago"
  units: "imperial"              # or "metric"
  respond_to: "dm"               # dm, all, or channel
```

### Run

```bash
# Direct
python meshbot.py

# As a systemd service (recommended for always-on)
sudo cp systemd/meshbot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now meshbot
```

### Connection Types

**TCP (WiFi radios):**
```yaml
connection:
  type: "tcp"
  host: "192.168.1.100"
  port: 4403
```

**Serial (USB radios):**
```yaml
connection:
  type: "serial"
  serial_port: "/dev/ttyUSB0"    # Linux
  # serial_port: "/dev/cu.usbserial-0001"  # macOS
  # serial_port: "COM3"          # Windows
```

### Response Modes

| Mode | Behavior |
|------|----------|
| `dm` | Only respond to direct messages (default, recommended) |
| `all` | Respond to DMs and all channel broadcasts |
| `channel` | Respond to DMs and specific channels only |

## Data Sources

All free, no API keys required:

| Data | API |
|------|-----|
| Weather & Forecast | [wttr.in](https://wttr.in) |
| Sunrise/Sunset | [wttr.in](https://wttr.in) |
| Earthquakes | [USGS FDSNWS](https://earthquake.usgs.gov/fdsnws/event/1/) |
| Weather Alerts | [NWS API](https://api.weather.gov/) |
| Dad Jokes | [icanhazdadjoke.com](https://icanhazdadjoke.com/) |

## Finding Your NWS Zone

Visit [https://alerts.weather.gov/](https://alerts.weather.gov/) and look up your county's zone code. Examples:
- `OKC081` — Payne County, Oklahoma
- `TXZ104` — Travis County, Texas
- `CAZ006` — Sacramento County, California

## Architecture

```
┌──────────────┐         ┌─────────────┐
│  Meshtastic  │◄───────►│  meshbot.py │──── wttr.in (weather)
│  Radio       │  mesh   │             │──── USGS (earthquakes)
│  (TCP/USB)   │         │             │──── NWS (alerts)
└──────────────┘         └─────────────┘──── icanhazdadjoke.com
```

## Also See

- **[meshtastic-matrix-bridge](https://github.com/dakotasnapshot/meshtastic-matrix-bridge)** — Our companion project that bridges Meshtastic to Matrix chat rooms (includes these same bot commands)
- **[meshing-around](https://github.com/SpudGunMan/meshing-around)** — Feature-rich Meshtastic BBS bot
- **[868meshbot](https://github.com/868meshbot/meshbot)** — EU-focused Meshtastic bot

## Contributing

Pull requests welcome! Ideas:
- BBS / message board functionality
- Satellite pass predictions
- APRS gateway
- More weather data (radar, UV index)
- Games (DopeWars, trivia)

## License

MIT — see [LICENSE](LICENSE).

## Credits

- Built with [meshtastic-python](https://github.com/meshtastic/python)
- Inspired by [meshing-around](https://github.com/SpudGunMan/meshing-around) and [868meshbot](https://github.com/868meshbot/meshbot)
- Made for the [OKMesh](https://okmesh.org) community 📡
