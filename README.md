# Docker Seedbox : HTTPS + Auth

## Overview

This stack deploys a **complete self‑hosted seedbox** (qBittorrent, Sonarr, Radarr, Prowlarr, JOAL, syncthing)  fully **secured with VPN, HTTPS, and Basic Auth**.
It uses only **official Docker images** and **Caddy** as the HTTPS reverse proxy.

---

## Stack Components

## Stack Components

| Service | Purpose | Port (host) |
|----------|----------|-------------|
| **Gluetun (VPN)** | VPN tunnel for all container traffic | NA |
| **qBittorrent** | Torrent client with web UI | 8081 |
| **Prowlarr** | Indexer manager for *arr applications | 9696 |
| **Sonarr** | TV series automation and management | 8989 |
| **Radarr** | Movie automation and management | 7878 |
| **JOAL** | Fake seeding client (ratio keeper) | 8003 |
| **Caddy** | HTTPS reverse proxy with automatic certificates | 443 |
| **Auth** | Authentication gateway (Basic Auth / Token) | 3000 |
| **Dashboard** | Static homepage with links to services | included |
| **Dashboard API** | Backend API providing stats and health data | 5005 |
| **Syncthing** | File synchronization service | 8384 |
| **Autocleaner** | Automatic cleanup of old torrents/files | NA |


> 💡 All traffic for these services runs **through the VPN** using `network_mode: service:vpn`.

---

## 🧠 Requirements

- Docker + Docker Compose
- A valid VPN account (PIA, Mullvad, NordVPN, etc.)
- (Optional) A domain name for HTTPS with Let's Encrypt
- Ports **80** and **443** opened and forwarded if using a public domain

---

## ⚙️ Setup Guide

### 1. Download & Extract

```bash
unzip seedbox-docker.zip
cd seedbox-docker
```

---

### 2. Configure environment variables

Copy the example file:

```bash
cp .env.example .env
```

Edit `.env` with your values:

```env
# ====== General ======
TZ=Europe/Paris

# ====== VPN (Gluetun) ======
VPN_SERVICE_PROVIDER=private internet access
OPENVPN_USER=pxxxxx
OPENVPN_PASSWORD=xxxxx
VPN_SERVER_REGIONS=DE Frankfurt

# ====== Ports (optional direct access) ======
QBITTORRENT_PORT=8081
PROWLARR_PORT=9696
SONARR_PORT=8989
RADARR_PORT=7878
LIDARR_PORT=8686
SABNZBD_PORT=8085
JOAL_PORT=8003
RESILIO_PORT=8888

# ====== HTTPS (Caddy) ======
DOMAIN=your_domain

# ====== JOAL ======
JOAL_PREFIX=joal
JOAL_SECRET=change_me

DASHBOARD_PORT=80

AUTH_SESSION_SECRET=xxxx
AUTH_USERNAME=seedbox
# to generate hash :docker compose exec auth node -e "console.log(require('bcryptjs').hashSync(process.argv[1],12))" -- password

AUTH_PASSWORD_HASH=xxxxxx

# Token to bypass auth redirection (needed by nzb360 for example)
AUTH_API_TOKENS=xxxxxx

```

---

### 3. Create Basic Auth credentials

Generate a bcrypt password hash:

```bash
docker compose exec auth node -e "console.log(require('bcryptjs').hashSync(process.argv[1],12))" -- password
```

Copy the generated hash (starts with `$2a$14$...`) and add it to `.env`:

---

### 4. (Optional) Caddy Root Certificate Installation

When running Caddy locally, it uses its own local Certificate Authority (CA) to issue HTTPS certificates for your services.  
To avoid browser warnings, you can install this root certificate manually.


**Copy the certificate to your host machine:**
   ```bash
   docker cp $(docker compose ps -q caddy):/data/caddy/pki/authorities/local/root.crt ./caddy_root.crt
   ```

And Add it to your system trust store.

---

### 5. Launch the stack

```bash
docker compose build .
docker compose up -d
```

### 6. Access your dashboard

With domain → `https://seedbox.example.com`

---

##  Security Summary

- **HTTPS (TLS)**  encrypted traffic via self‑signed
- **Auth**  password protection for the dashboard
-  **VPN routing**  all apps run inside Gluetun
-  **Minimal ports**  only 80/443 exposed externally
-  **Container isolation**  each service runs separately


---

## 🧾 Credits

- Base images: [LinuxServer.io](https://www.linuxserver.io/), [Gluetun](https://github.com/qdm12/gluetun), [Caddy](https://caddyserver.com/), [JOAL](https://github.com/anthonyraymond/joal)
- Stack design: Simplified Docker replacement for Swizzin

> **License:** Personal use only
