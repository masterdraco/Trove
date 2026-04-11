---
title: Backup & Restore
order: 9
description: Export a complete Trove install and restore it on another host.
---

# Backup & Restore

Trove has a one-click backup/restore system that lets you take a full snapshot of your install and move it to another machine. It's the recommended way to migrate to a new host, to set up a second copy for testing, or to recover after a disk failure.

A Trove backup is a single **zip file** containing everything needed to recreate the install:

- **`trove.db`** — The SQLite database with every user, client, indexer, feed, cached RSS item, task, task run history, watchlist entry, AI cache, and app setting.
- **`session.secret`** — The 48-byte random secret that Trove uses to sign session cookies **and** to derive the Fernet key that encrypts all stored credentials. Without this file, every client password, indexer API key, and feed cookie becomes unreadable garbage.
- **`manifest.json`** — Metadata about the backup: format version, Trove version at export time, alembic migration revision, ISO timestamp, and a SHA-256 checksum per bundled file.

Both files are required for a complete restore. **If you only copy `trove.db` and leave `session.secret` behind, Trove can still read the rows, but every credential will fail to decrypt** — you'd have to re-enter all your client passwords and indexer API keys by hand.

## Downloading a backup

1. Go to **Settings** → scroll down to the **Backup & restore** panel
2. Click **Download .zip**
3. Trove checkpoints the SQLite WAL file (so pending writes are flushed into the main database) and streams a zip to your browser
4. The download is named `trove-backup-YYYYMMDD-HHMMSS.zip`

Keep these zips safe — anyone who gets the file gets all your credentials. They're stored encrypted inside `trove.db`, but the encryption key (`session.secret`) is right there next to them in the same archive. Treat a Trove backup like a password manager export.

**Good practice**: schedule a regular backup to an external location (rsync cron, restic, etc.) and keep at least the last 3 copies. For a media tool that's been polling feeds for months, losing the RSS cache is annoying but not fatal; losing credentials is annoying *and* means re-typing everything.

## Restoring on a new host

The backup is designed to move cleanly between Trove installs, including across hosts with different operating systems. The steps are:

1. **Install Trove on the new host** — `docker compose up -d` the usual way
2. **Run through the setup wizard** with any throwaway admin credentials. You just need to get past the "first run" gate — the restore will replace this user with your original one from the backup
3. **Log in** with the throwaway credentials
4. Go to **Settings** → **Backup & restore** → **Restore from backup**
5. Click the file picker, select the zip from your old host, click **Restore**
6. Confirm the destructive-action prompt
7. Wait for the green confirmation: *"Restored backup from ... (Trove X.Y.Z). Reload the page to see your restored data."*
8. **Hard refresh** the browser (Ctrl+Shift+R) — the session cookie from the throwaway account is no longer valid
9. **Log in with your original username/password** from the old host

Everything comes across: clients, indexers, feeds (including all cached RSS items within retention), tasks, task run history, watchlist, AI settings, and app settings.

## Under the hood

When you click Restore, Trove:

1. Reads the uploaded zip into memory
2. Parses `manifest.json` and rejects anything with an unknown format version
3. Writes the new files to a staging directory (`config/.restore-staging/`) so a mid-transfer failure doesn't corrupt your live database
4. Validates SHA-256 checksums against the manifest (catches corruption)
5. **Stops the APScheduler** so no feed poll or task run can write to the DB mid-swap
6. **Disposes the SQLAlchemy engine** to release file handles on the current `trove.db`
7. **Moves the current `trove.db` and `session.secret` to `config/.pre-restore/`** with a UNIX timestamp suffix — this is a safety net in case the new files are broken
8. Moves the staged files into place at `config/trove.db` and `config/session.secret`
9. Fixes permissions on `session.secret` to `0600`
10. Re-initialises the DB engine (picks up the new file)
11. **Restarts the APScheduler** — all feeds and tasks from the restored DB get re-scheduled automatically

If anything goes wrong mid-restore, you'll find the original files in `config/.pre-restore/` with names like `trove.db.1775913000` and `session.secret.1775913000`. Move them back to `config/trove.db` and `config/session.secret`, restart the container, and you're back to the pre-restore state.

## Format version and forward compatibility

The `manifest.json` declares a `format_version` field (currently `1`). Future Trove versions may introduce backup formats with additional files or different layouts; old Trove installs will refuse to restore newer-format backups with a clear error message. If you're restoring across very different Trove versions, apply alembic migrations before or after the restore depending on the direction — downgrading a restored database is generally not supported.

A restore always uses the schema that ships with the **running** Trove instance. If your backup has alembic revision `0008` and the new host is running a Trove with revision `0010`, you may see extra columns added; migrations are applied automatically at startup.

## Automation

If you want scheduled backups, the simplest path is a shell cron job that `curl`s the endpoint with your session cookie. For example:

```bash
#!/usr/bin/env bash
set -euo pipefail
OUT=/backups/trove-$(date -u +%Y%m%d-%H%M%S).zip
curl -fsS \
  --cookie "trove_session=$TROVE_SESSION" \
  -o "$OUT" \
  http://trove.lan:8000/api/backup
# Keep only last 7 daily backups
ls -t /backups/trove-*.zip | tail -n +8 | xargs -r rm --
```

Grab the cookie value from your browser dev tools after logging in, and store it in `$TROVE_SESSION` (e.g. in `/etc/default/trove-backup`). The cookie is valid for 30 days; rotate the secret or re-login to invalidate it.

A dedicated API-key-based endpoint for automation is on the roadmap — the current session-cookie approach is a short-term workaround.

## FAQ

**Q: Can I inspect a backup before restoring?**
Yes — it's a regular zip. Unzip it and look at `manifest.json` to check timestamps, version, and checksums. You can also open `trove.db` with any SQLite browser.

**Q: Does restore wipe my new host's data?**
Yes. Restore is destructive — it overwrites `trove.db` and `session.secret`. The original files on the new host are moved to `config/.pre-restore/` as a safety net, but the LIVE state becomes whatever's in the backup.

**Q: Can I restore just the clients or just the indexers, not the whole thing?**
Not through the UI. If you need partial restore, unzip the backup, open `trove.db` with a SQLite browser, and export the specific tables you want via SQL. Then re-import them manually into your live database.

**Q: Will the RSS poller start immediately after restore?**
Yes. When the scheduler restarts post-restore, it re-reads every enabled feed from the freshly-restored database and schedules them at their configured interval. The first poll will happen one interval-length after the restore completes.

**Q: What if my old host's Trove version is newer than my new host?**
Install the same version (or newer) on the new host first. Downgrading a database is not safe — alembic migrations only work forward.
