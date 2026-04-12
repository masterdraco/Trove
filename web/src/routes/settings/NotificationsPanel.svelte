<script lang="ts">
  import { onMount } from "svelte";
  import {
    api,
    type NotificationOut,
    type NotificationProviderType,
    type NotificationEventKind,
    type NotificationMeta
  } from "$lib/api";
  import {
    Bell,
    Plus,
    Pencil,
    Trash2,
    Loader2,
    CheckCircle2,
    XCircle,
    Send
  } from "lucide-svelte";

  const ALL_EVENTS: NotificationEventKind[] = [
    "task.grabbed",
    "task.send_failed",
    "task.error",
    "download.started",
    "download.completed",
    "download.failed",
    "download.removed"
  ];

  const EVENT_LABELS: Record<NotificationEventKind, string> = {
    "task.grabbed": "Task grabbed a release",
    "task.send_failed": "Task couldn't send to any client",
    "task.error": "Task crashed with an error",
    "download.started": "Download started",
    "download.completed": "Download completed",
    "download.failed": "Download failed",
    "download.removed": "Download removed from client"
  };

  const TYPE_LABELS: Record<NotificationProviderType, string> = {
    discord_webhook: "Discord webhook",
    discord_bot: "Discord bot",
    telegram: "Telegram bot",
    ntfy: "ntfy",
    webhook: "Generic webhook"
  };

  type Form = {
    name: string;
    type: NotificationProviderType;
    events: NotificationEventKind[];
    enabled: boolean;
    // Per-type config fields (only the relevant ones are posted)
    webhook_url: string;
    bot_token: string;
    channel_id: string;
    chat_id: string;
    server_url: string;
    topic: string;
    auth_token: string;
    url: string;
    method: string;
  };

  const empty = (): Form => ({
    name: "",
    type: "discord_webhook",
    events: ["task.grabbed", "download.completed", "download.failed"],
    enabled: true,
    webhook_url: "",
    bot_token: "",
    channel_id: "",
    chat_id: "",
    server_url: "https://ntfy.sh",
    topic: "",
    auth_token: "",
    url: "",
    method: "POST"
  });

  let providers = $state<NotificationOut[]>([]);
  let meta = $state<NotificationMeta | null>(null);
  let loading = $state(true);
  let showForm = $state(false);
  let editingId = $state<number | null>(null);
  let form = $state<Form>(empty());
  let saving = $state(false);
  let testingId = $state<number | null>(null);
  let testResults = $state<Record<number, { ok: boolean; msg: string }>>({});
  let formError = $state<string | null>(null);

  async function load() {
    loading = true;
    try {
      [providers, meta] = await Promise.all([api.notifications.list(), api.notifications.meta()]);
    } finally {
      loading = false;
    }
  }

  onMount(load);

  function openForm() {
    form = empty();
    editingId = null;
    formError = null;
    showForm = true;
  }

  function openEdit(p: NotificationOut) {
    // Credentials are write-only — the existing form fields start blank.
    form = { ...empty(), name: p.name, type: p.type, events: [...p.events], enabled: p.enabled };
    editingId = p.id;
    formError = null;
    showForm = true;
  }

  function buildConfig(): Record<string, unknown> {
    switch (form.type) {
      case "discord_webhook":
        return form.webhook_url ? { webhook_url: form.webhook_url } : {};
      case "discord_bot":
        return {
          ...(form.bot_token ? { bot_token: form.bot_token } : {}),
          ...(form.channel_id ? { channel_id: form.channel_id } : {})
        };
      case "telegram":
        return {
          ...(form.bot_token ? { bot_token: form.bot_token } : {}),
          ...(form.chat_id ? { chat_id: form.chat_id } : {})
        };
      case "ntfy":
        return {
          ...(form.server_url ? { server_url: form.server_url } : {}),
          ...(form.topic ? { topic: form.topic } : {}),
          ...(form.auth_token ? { auth_token: form.auth_token } : {})
        };
      case "webhook":
        return {
          ...(form.url ? { url: form.url } : {}),
          method: form.method || "POST"
        };
    }
  }

  async function save() {
    saving = true;
    formError = null;
    try {
      const cfg = buildConfig();
      if (editingId !== null) {
        const payload: Record<string, unknown> = {
          name: form.name,
          events: form.events,
          enabled: form.enabled
        };
        if (Object.keys(cfg).length > 0) payload.config = cfg;
        await api.notifications.update(editingId, payload);
      } else {
        await api.notifications.create({
          name: form.name,
          type: form.type,
          events: form.events,
          enabled: form.enabled,
          config: cfg
        });
      }
      showForm = false;
      await load();
    } catch (e: unknown) {
      const err = e as { detail?: string };
      formError = err.detail || "Failed to save";
    } finally {
      saving = false;
    }
  }

  async function testOne(p: NotificationOut) {
    testingId = p.id;
    try {
      const result = await api.notifications.test(p.id);
      testResults = {
        ...testResults,
        [p.id]: { ok: result.ok, msg: result.message || (result.ok ? "delivered" : "failed") }
      };
    } catch (e: unknown) {
      const err = e as { detail?: string };
      testResults = { ...testResults, [p.id]: { ok: false, msg: err.detail || "request failed" } };
    } finally {
      testingId = null;
    }
  }

  async function remove(p: NotificationOut) {
    if (!confirm(`Delete notification provider "${p.name}"?`)) return;
    await api.notifications.remove(p.id);
    await load();
  }

  function toggleEvent(kind: NotificationEventKind) {
    if (form.events.includes(kind)) {
      form.events = form.events.filter((e) => e !== kind);
    } else {
      form.events = [...form.events, kind];
    }
  }
</script>

<div class="surface p-6">
  <div class="flex items-start justify-between gap-3">
    <div class="flex items-center gap-3">
      <div
        class="flex h-10 w-10 items-center justify-center rounded-xl bg-fuchsia-500/20 text-fuchsia-400"
      >
        <Bell class="h-5 w-5" />
      </div>
      <div>
        <h3 class="text-base font-semibold">Notifications</h3>
        <p class="text-xs text-muted-foreground">
          Push events to Discord, Telegram, ntfy, or any webhook when tasks grab and
          downloads finish. One provider = one channel/destination.
        </p>
      </div>
    </div>
    <button class="btn-primary inline-flex items-center gap-1" onclick={openForm}>
      <Plus class="h-3.5 w-3.5" />
      Add provider
    </button>
  </div>

  {#if loading}
    <div class="mt-5 text-sm text-muted-foreground">Loading…</div>
  {:else if providers.length === 0}
    <div
      class="mt-5 rounded-xl border border-dashed border-border/60 bg-background/30 p-6 text-center text-sm text-muted-foreground"
    >
      No providers configured. Add one to start receiving notifications.
    </div>
  {:else}
    <div class="mt-5 space-y-3">
      {#each providers as p (p.id)}
        <div
          class="rounded-xl border border-border/60 bg-background/40 p-4"
          class:opacity-60={!p.enabled}
        >
          <div class="flex items-start justify-between gap-3">
            <div class="min-w-0 flex-1">
              <div class="flex items-center gap-2">
                <span class="truncate font-semibold">{p.name}</span>
                <span
                  class="rounded-full bg-muted px-2 py-0.5 text-[10px] uppercase tracking-wide"
                >
                  {TYPE_LABELS[p.type]}
                </span>
                {#if !p.enabled}
                  <span class="text-[10px] uppercase text-muted-foreground">disabled</span>
                {/if}
              </div>
              <div class="mt-2 flex flex-wrap gap-1">
                {#each p.events as ev (ev)}
                  <span
                    class="rounded-full border border-border/60 bg-background/60 px-2 py-0.5 text-[10px] text-muted-foreground"
                  >
                    {ev}
                  </span>
                {/each}
              </div>
              {#if p.last_sent_at}
                <div class="mt-2 flex items-center gap-1.5 text-xs">
                  {#if p.last_sent_ok}
                    <CheckCircle2 class="h-3 w-3 text-green-500" />
                    <span class="text-muted-foreground"
                      >Last sent {new Date(p.last_sent_at).toLocaleString()}</span
                    >
                  {:else}
                    <XCircle class="h-3 w-3 text-destructive" />
                    <span class="text-destructive">
                      {p.last_sent_message || "failed"}
                    </span>
                  {/if}
                </div>
              {/if}
              {#if testResults[p.id]}
                <div
                  class="mt-2 rounded-md px-2 py-1 text-xs {testResults[p.id].ok
                    ? 'bg-success/10 text-success'
                    : 'bg-destructive/10 text-destructive'}"
                >
                  Test: {testResults[p.id].msg}
                </div>
              {/if}
            </div>
            <div class="flex shrink-0 flex-col gap-1">
              <button
                class="inline-flex items-center gap-1 rounded-md border border-border bg-background px-3 py-1.5 text-xs hover:bg-muted"
                onclick={() => testOne(p)}
                disabled={testingId === p.id}
              >
                {#if testingId === p.id}
                  <Loader2 class="h-3.5 w-3.5 animate-spin" />
                {:else}
                  <Send class="h-3.5 w-3.5" />
                {/if}
                Test
              </button>
              <button
                class="inline-flex items-center gap-1 rounded-md border border-border bg-background px-3 py-1.5 text-xs hover:bg-muted"
                onclick={() => openEdit(p)}
              >
                <Pencil class="h-3.5 w-3.5" />
                Edit
              </button>
              <button
                class="inline-flex items-center gap-1 rounded-md border border-border bg-background px-3 py-1.5 text-xs text-destructive hover:bg-destructive/10"
                onclick={() => remove(p)}
              >
                <Trash2 class="h-3.5 w-3.5" />
                Delete
              </button>
            </div>
          </div>
        </div>
      {/each}
    </div>
  {/if}
</div>

{#if showForm}
  <div
    class="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-background/80 p-6 backdrop-blur-sm"
  >
    <div class="mt-10 w-full max-w-xl rounded-2xl border border-border bg-card p-6 shadow-2xl">
      <div class="mb-4 flex items-center justify-between">
        <h3 class="text-lg font-semibold">
          {editingId !== null ? "Edit provider" : "Add notification provider"}
        </h3>
        <button
          class="rounded-md border border-border bg-background px-2 py-1 text-xs hover:bg-muted"
          onclick={() => (showForm = false)}
        >
          Cancel
        </button>
      </div>

      <div class="space-y-3">
        <label class="block">
          <span class="mb-1 block text-sm font-medium">Name</span>
          <input
            type="text"
            bind:value={form.name}
            required
            placeholder="e.g. trove-notifications"
            class="w-full rounded-md border border-input bg-background px-3 py-2 text-sm outline-none ring-ring focus:ring-2"
          />
        </label>

        <label class="block">
          <span class="mb-1 block text-sm font-medium">Type</span>
          <select
            bind:value={form.type}
            disabled={editingId !== null}
            class="w-full rounded-md border border-input bg-background px-3 py-2 text-sm outline-none ring-ring focus:ring-2 disabled:opacity-60"
          >
            <option value="discord_webhook">Discord webhook (simplest, one channel)</option>
            <option value="discord_bot">Discord bot (token, many channels)</option>
            <option value="telegram">Telegram bot</option>
            <option value="ntfy">ntfy</option>
            <option value="webhook">Generic webhook</option>
          </select>
        </label>

        {#if form.type === "discord_webhook"}
          <label class="block">
            <span class="mb-1 block text-sm font-medium">Webhook URL</span>
            <input
              type="url"
              bind:value={form.webhook_url}
              placeholder={editingId !== null
                ? "•••••• (leave blank to keep)"
                : "https://discord.com/api/webhooks/…"}
              class="w-full rounded-md border border-input bg-background px-3 py-2 font-mono text-xs outline-none ring-ring focus:ring-2"
            />
            <span class="mt-1 block text-xs text-muted-foreground">
              In Discord: right-click the channel → Edit Channel → Integrations → Webhooks →
              New Webhook → Copy URL.
            </span>
          </label>
        {:else if form.type === "discord_bot"}
          <label class="block">
            <span class="mb-1 block text-sm font-medium">Bot token</span>
            <input
              type="password"
              bind:value={form.bot_token}
              placeholder={editingId !== null ? "•••••• (leave blank to keep)" : ""}
              class="w-full rounded-md border border-input bg-background px-3 py-2 text-sm outline-none ring-ring focus:ring-2"
            />
          </label>
          <label class="block">
            <span class="mb-1 block text-sm font-medium">Channel ID</span>
            <input
              type="text"
              bind:value={form.channel_id}
              placeholder="e.g. 1234567890123456789"
              class="w-full rounded-md border border-input bg-background px-3 py-2 font-mono text-xs outline-none ring-ring focus:ring-2"
            />
            <span class="mt-1 block text-xs text-muted-foreground">
              Enable Developer Mode in Discord (Settings → Advanced), then right-click a channel
              → Copy Channel ID.
            </span>
          </label>
        {:else if form.type === "telegram"}
          <label class="block">
            <span class="mb-1 block text-sm font-medium">Bot token</span>
            <input
              type="password"
              bind:value={form.bot_token}
              placeholder={editingId !== null ? "•••••• (leave blank to keep)" : "123456:ABC-…"}
              class="w-full rounded-md border border-input bg-background px-3 py-2 text-sm outline-none ring-ring focus:ring-2"
            />
            <span class="mt-1 block text-xs text-muted-foreground">
              Create a bot via @BotFather, copy the token. Then start a chat with the bot (or
              add to a group) and note the chat ID.
            </span>
          </label>
          <label class="block">
            <span class="mb-1 block text-sm font-medium">Chat ID</span>
            <input
              type="text"
              bind:value={form.chat_id}
              placeholder="e.g. 123456789 or -100..."
              class="w-full rounded-md border border-input bg-background px-3 py-2 font-mono text-xs outline-none ring-ring focus:ring-2"
            />
          </label>
        {:else if form.type === "ntfy"}
          <label class="block">
            <span class="mb-1 block text-sm font-medium">Server URL</span>
            <input
              type="url"
              bind:value={form.server_url}
              placeholder="https://ntfy.sh"
              class="w-full rounded-md border border-input bg-background px-3 py-2 font-mono text-xs outline-none ring-ring focus:ring-2"
            />
          </label>
          <label class="block">
            <span class="mb-1 block text-sm font-medium">Topic</span>
            <input
              type="text"
              bind:value={form.topic}
              placeholder="e.g. trove-masterdraco"
              class="w-full rounded-md border border-input bg-background px-3 py-2 font-mono text-xs outline-none ring-ring focus:ring-2"
            />
            <span class="mt-1 block text-xs text-muted-foreground">
              Subscribe to the same topic in the ntfy mobile app to receive push notifications.
            </span>
          </label>
          <label class="block">
            <span class="mb-1 block text-sm font-medium">Auth token (optional)</span>
            <input
              type="password"
              bind:value={form.auth_token}
              placeholder={editingId !== null ? "•••••• (leave blank to keep)" : ""}
              class="w-full rounded-md border border-input bg-background px-3 py-2 text-sm outline-none ring-ring focus:ring-2"
            />
          </label>
        {:else if form.type === "webhook"}
          <label class="block">
            <span class="mb-1 block text-sm font-medium">URL</span>
            <input
              type="url"
              bind:value={form.url}
              placeholder="https://example.com/hook"
              class="w-full rounded-md border border-input bg-background px-3 py-2 font-mono text-xs outline-none ring-ring focus:ring-2"
            />
          </label>
          <label class="block">
            <span class="mb-1 block text-sm font-medium">Method</span>
            <select
              bind:value={form.method}
              class="w-full rounded-md border border-input bg-background px-3 py-2 text-sm outline-none ring-ring focus:ring-2"
            >
              <option value="POST">POST</option>
              <option value="PUT">PUT</option>
            </select>
          </label>
        {/if}

        <div>
          <span class="mb-2 block text-sm font-medium">Events to receive</span>
          <div class="space-y-1">
            {#each ALL_EVENTS as ev (ev)}
              <label class="flex cursor-pointer items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={form.events.includes(ev)}
                  onchange={() => toggleEvent(ev)}
                />
                <span>{EVENT_LABELS[ev]}</span>
                <span class="font-mono text-[10px] text-muted-foreground">{ev}</span>
              </label>
            {/each}
          </div>
        </div>

        <label class="flex items-center gap-2 text-sm">
          <input type="checkbox" bind:checked={form.enabled} />
          <span>Enabled</span>
        </label>

        {#if formError}
          <div class="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
            {formError}
          </div>
        {/if}

        <div class="flex justify-end gap-2 pt-2">
          <button
            class="rounded-md border border-border bg-background px-4 py-2 text-sm hover:bg-muted"
            onclick={() => (showForm = false)}
          >
            Cancel
          </button>
          <button class="btn-primary disabled:opacity-60" onclick={save} disabled={saving}>
            {#if saving}
              <Loader2 class="h-3.5 w-3.5 animate-spin" />
            {/if}
            Save
          </button>
        </div>
      </div>
    </div>
  </div>
{/if}
