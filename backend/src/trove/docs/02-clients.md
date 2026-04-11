---
title: Download clients
order: 2
description: Connect Trove to Deluge, Transmission, SABnzbd, or NZBGet.
---

# Download clients

Trove sends matched releases to a **download client** — the software that actually downloads torrents (Deluge, Transmission) or NZB files (SABnzbd, NZBGet). You can add as many clients as you want, mix protocols, and route different tasks to different clients.

Credentials for every client are encrypted with Fernet before being stored in the database. The encryption key is derived from `config/session.secret`, so keep that file backed up.

## Transmission

**URL**: `http://<host>:9091` (the web interface — Trove appends `/transmission/rpc` itself)

**Authentication**: Transmission only requires a username + password if RPC authentication is enabled in `settings.json`. If you have no auth, leave both fields blank.

**Categories**: Transmission has no real category concept, but Trove passes `labels` which modern Transmission versions support.

**Download location**: You can set a `default_save_path` per client, or override it per task.

Common issues:
- **401 Unauthorized** — wrong username/password, or RPC auth is off but you provided credentials
- **Connection refused** — check that Transmission is actually listening on the URL and that the firewall allows the port
- **CSRF error** — Trove handles Transmission's session-ID handshake automatically (retries on 409); if you still see this, your Transmission version is very old

## Deluge

**URL**: `http://<host>:8112` — base URL of the *web* UI, not the daemon RPC port (58846).

**Authentication**: Deluge Web UI uses a single password (not a username). Default is `deluge`.

**Label plugin**: Trove sets torrent labels if the Label plugin is enabled in Deluge. If not, label assignment is silently skipped.

**First-connect handshake**: When deluge-web runs detached from a daemon, Trove calls `web.connect` to the first available host automatically.

Common issues:
- **authentication failed** — wrong web UI password. Check `deluge-web` settings (NOT the daemon authentication)
- **Daemon not connected** — Trove tries to auto-connect but if you have multiple daemons, go to Preferences → Connection Manager in the web UI and connect manually first

## SABnzbd

**URL**: `http://<host>:8080`

**Authentication**: SABnzbd uses an **API key** instead of username/password. Find it in SABnzbd → Config → General → API Key.

**Categories**: Trove reads SABnzbd's configured categories via `mode=get_cats` and shows them in the client. Set a `default_category` on the client so tasks without an explicit category still route correctly.

Common issues:
- **API Key Incorrect** — you used the "NZB Key" instead of the "API Key". They're different keys in SABnzbd's config
- **Host not permitted** — SABnzbd has a "Host Whitelist" under Config → General. Add Trove's host or disable the whitelist

## NZBGet

**URL**: `http://<host>:6789`

**Authentication**: Basic auth with username + password (default: `nzbget` / `tegbzn6789`)

**Categories**: Trove reads NZBGet's categories from its config dump. Make sure categories are defined in NZBGet's `nzbget.conf`.

Common issues:
- **401 Unauthorized** — wrong basic auth
- **Categories list empty** — make sure `Category1.Name=...` entries exist in NZBGet's config

## Editing an existing client

On `/clients`, click **Edit** next to a client to change its name, URL, or save path. Credentials fields show a `•••••• (leave blank to keep)` placeholder — type new credentials only if you want to rotate them. The type (Transmission/Deluge/...) is locked in edit mode; to change type, delete and recreate the client.

## Testing connections

The **Test** button on each client row calls the client's status endpoint and shows the version + any error message. Use this whenever you change network config or rotate credentials.

The onboarding wizard also has an inline **Test connection** button before saving — great for verifying before you commit.
