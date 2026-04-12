---
title: Torznab Export
order: 7
description: Use Trove as an aggregated indexer backend for Sonarr, Radarr, and friends.
---

# Torznab Export

Trove exposes its own **Torznab-compatible API** at `/torznab/api`. That means Sonarr, Radarr, Lidarr and any other tool that speaks Torznab can treat Trove as a single unified indexer — and Trove forwards their searches to all your configured indexers + the local RSS cache.

This is the cleanest way to use Trove alongside the *Arr stack: configure all your trackers once in Trove, and Sonarr/Radarr only need to know about Trove.

## Finding your endpoint + key

Go to **Settings → Torznab export** in the Trove UI. That panel shows:

- A ready-to-paste **Sonarr / Radarr URL** with the apikey already baked in
- The **API key** on its own, with show/hide and copy buttons
- An **example search** URL you can curl directly to sanity-check

Click the copy icon next to whichever field you need and paste it into Sonarr / Radarr. No shell access to the Trove host required.

Under the hood the API key is the first 32 characters of your `config/session.secret` — the same secret we use to sign session cookies. We reuse it instead of generating a separate token to keep setup simple. If you restore from a backup the apikey also moves across automatically.

## Endpoint format

```
http://<trove-host>:8000/torznab/api?apikey=<YOUR_KEY>&t=caps
```

Replace `<trove-host>` with wherever Trove is reachable from your Sonarr/Radarr host, and `<YOUR_KEY>` with what the Settings panel shows.

## Configuring Sonarr

1. Sonarr → Settings → Indexers → **+** → Torznab (Custom)
2. **Name**: `Trove`
3. **URL**: `http://<trove-host>:8000/torznab/api`
4. **API Key**: paste from Trove → Settings → Torznab export → API key
5. **Categories**: `5000, 5070` (TV + Anime)
6. Click **Test** — should succeed
7. Click **Save**

## Configuring Radarr

Same as Sonarr but use categories `2000` (Movies) and point the URL at the same `/torznab/api` endpoint.

## What gets returned

When Sonarr queries Trove for a show, Trove:

1. Parses the query (`q=The.Bear.S03E04`)
2. Runs the full search pipeline (live indexers + local RSS cache)
3. De-duplicates on infohash + fuzzy title
4. Converts hits back to Torznab XML
5. Returns the top results

Sonarr sees it as one indexer with potentially hundreds of releases per query — exactly the same as if you'd configured all your sources individually in Sonarr.

## Tips

- **Rate limiting**: Sonarr retries heavily. If your Trove indexers have daily caps, aggressive Sonarr polling can burn through them. Set Sonarr's "RSS Sync Interval" to 15+ minutes
- **Seeders**: Trove reports seeders if the source has them (Newznab attr). Private tracker RSS often doesn't expose seeders in the feed, so Sonarr may see `?/?` — that's fine, Sonarr won't reject it
- **Category mapping**: Trove maps Torznab category IDs to internal categories (2000→movies, 5000→tv, 1000→games, 4000→software, 7000→books)
- **Cross-seeding**: Sonarr's "prefer reused seeder" logic doesn't apply here since Trove aggregates across sources

## Security note

The `/torznab/api` endpoint is **NOT protected by login**. It uses the `apikey` query parameter for authentication, which is standard Torznab practice. If you expose Trove to the internet, make sure to put HTTPS in front of it — the API key is sent in the query string and would leak otherwise.

A future version will support rotating the Torznab key separately from the session secret.
