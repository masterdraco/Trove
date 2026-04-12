---
title: Notifications
order: 10
description: Push events to Discord, Telegram, ntfy, or any webhook.
---

# Notifications

Trove can push real-time notifications to your messaging platforms whenever interesting things happen — a task grabs a release, a download finishes, a task fails, or a release gets removed from your client. No more F5'ing NZBGet to see whether Scream 7 landed.

Notifications are configured from **Notifications** (in the Settings sidebar) and run fire-and-forget: a broken webhook will **never** crash a task run or the download poller. Delivery failures are logged to each provider's row so you can see what's wrong without digging through server logs.

## Supported providers

### Discord webhook *(recommended for most users)*

The simplest setup — no bot, no OAuth, no token rotation. Each webhook maps to one channel.

1. In Discord: right-click the channel → **Edit Channel** → **Integrations** → **Webhooks** → **New Webhook**
2. Name it (e.g. "Trove"), pick the target channel, click **Copy Webhook URL**
3. In Trove: Settings → Notifications → **Add provider** → pick **Discord webhook**
4. Paste the URL, pick which events to receive, click Save
5. Click **Test** — a test message should appear in the Discord channel within a couple of seconds

Use multiple providers if you want different events in different channels (e.g. "#downloads" for `download.completed` and "#task-fails" for `task.send_failed`).

### Discord bot

More flexible — one bot token can post to any channel it's been invited to, so you can route different event kinds to different channels from a single credential. More setup.

1. Go to <https://discord.com/developers/applications> → **New Application**
2. Add a **Bot**, copy the token
3. Under **OAuth2 → URL Generator** pick `bot` scope with `Send Messages` + `Embed Links` permissions, open the generated URL, invite the bot to your server
4. Enable Developer Mode in Discord (User Settings → Advanced → Developer Mode)
5. Right-click the target channel → **Copy Channel ID**
6. In Trove: add a provider of type **Discord bot**, paste token + channel ID

### Telegram bot

1. Chat with [@BotFather](https://t.me/BotFather) → `/newbot` → follow the prompts, copy the token
2. Start a chat with your new bot (or add it to a group)
3. Find the chat ID — easiest way: send any message to the bot, then open `https://api.telegram.org/bot<TOKEN>/getUpdates` and copy the `chat.id` from the response (negative for groups, positive for DMs)
4. In Trove: add a provider of type **Telegram bot**, paste token + chat ID

### ntfy

[ntfy](https://ntfy.sh) is a minimal push-notification service that runs in a mobile app. Subscribe to a topic in the app, then any HTTP POST to that topic URL lights up your phone.

1. Pick a unique topic (e.g. `trove-masterdraco-xyz42`) — anyone who knows the topic name can read notifications, so make it non-guessable if you're using the public server
2. Install the ntfy app, subscribe to the topic
3. In Trove: add a provider of type **ntfy**, paste server URL (default `https://ntfy.sh`), topic name, and optional auth token if you use a private ntfy server

### Generic webhook

For anything the other providers don't cover — your own bridge, a logging endpoint, Zapier/IFTTT, etc. Trove POSTs a JSON body:

```json
{
  "kind": "download.completed",
  "title": "Completed: Scream.7.2026...",
  "description": "Scream.7.2026.Retail.DKsubs.2160p...",
  "fields": {
    "Task id": "7",
    "Title": "Scream.7.2026.Retail.DKsubs.2160p...",
    "Size": "21.7GB"
  },
  "link": null,
  "timestamp": "2026-04-12T02:15:00+00:00"
}
```

You can pick POST or PUT, and add custom headers via the backend API if needed.

## Event kinds

| Event | When it fires |
|---|---|
| `task.grabbed` | A task successfully handed a release to a client. Includes task name, client name, size. |
| `task.upgraded` | A quality upgrade replaced a previously-grabbed release with a better one. Includes old/new title, quality tier change, and score change. Only fires when `enable_upgrades: true` is set on the task. |
| `task.send_failed` | A task found a match that passed all filters but every configured client refused it (protocol mismatch, auth failure, etc.). |
| `task.error` | A task crashed with an unhandled exception. |
| `download.started` | State transitioned from `queued` → `downloading` on the client. Includes display title and size. |
| `download.completed` | State transitioned to `completed`. The file is actually on disk now. |
| `download.failed` | State transitioned to `failed` — typically par repair failed (NZB), hash check failed (torrent), or the user cancelled from inside the client. |
| `download.removed` | Client returned NOT_FOUND — the user (or a cleanup script) removed the download manually. Trove flips the row so the next task run re-grabs. |

Each provider picks its own subscription list. By default new providers get `task.grabbed`, `download.completed`, and `download.failed` — a reasonable baseline that fires on "it worked" and "it broke" without being chatty.

## How it reaches the event source

- **Task events** fire from inside `task_engine._send_to_clients` after the client responds — i.e. the moment we hand the release off.
- **Download state events** fire from the download poller (runs every 60s by default) when it observes a state transition on a previously-sent row. This is why you see `download.completed` a few seconds after the client actually finishes, not instantly.

## Testing

Every provider row has a **Test** button. Clicking it dispatches a synthetic `task.grabbed` event through that provider only, bypassing the subscription filter. The result (delivered / failed) is shown inline next to the row.

## Security

- All provider credentials (webhook URLs, bot tokens, auth tokens) are stored **encrypted** in `notification_provider.config_cipher` using the same Fernet key derived from `session.secret` that protects client credentials. They're never logged in plaintext.
- The settings UI treats bot tokens and auth tokens as password fields. Leaving them blank on edit keeps the existing value.
- Failures in delivery are recorded to `last_sent_message` so you can see what went wrong without reading the container logs.

## Troubleshooting

**Test button says "discord_webhook HTTP 404"** — the webhook URL is wrong or the webhook has been deleted on Discord's side. Delete and re-create the webhook.

**Test says "telegram HTTP 400: chat not found"** — the bot can't see that chat. Make sure you've started a chat with the bot (for DMs) or added it as a member (for groups/channels). For channels, the bot needs to be an admin with "Post Messages" permission.

**No notifications are firing even though the test button works** — check the provider's **events** list on its row. The default subscription is `task.grabbed`, `download.completed`, and `download.failed`; if you unchecked one of those you won't see it. Also check the provider is `enabled`.

**Notifications are delayed by a minute or two** — the download state events (`download.started`, `download.completed`, etc.) come from the poller, which runs every 60 seconds. This is deliberate to avoid hammering every client every second. The `task.grabbed` event is instant because it fires inline from the task engine.
