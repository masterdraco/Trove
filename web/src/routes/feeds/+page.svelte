<script lang="ts">
  import { onMount } from "svelte";
  import { api } from "$lib/api";
  import {
    Plus,
    Trash2,
    Pencil,
    Rss,
    Loader2,
    CheckCircle2,
    XCircle,
    RefreshCw,
    Eye,
    Search
  } from "lucide-svelte";

  type Feed = Awaited<ReturnType<typeof api.feeds.list>>[number];
  type PreviewItem = Awaited<ReturnType<typeof api.feeds.preview>>[number];
  type StoredItem = Awaited<ReturnType<typeof api.feeds.items>>[number];

  let feeds = $state<Feed[]>([]);
  let loading = $state(true);
  let showForm = $state(false);
  let saving = $state(false);
  let formError = $state<string | null>(null);
  let editingId = $state<number | null>(null);
  let pollingId = $state<number | null>(null);
  let previewing = $state(false);
  let previewItems = $state<PreviewItem[] | null>(null);

  let expandedFeedId = $state<number | null>(null);
  let itemSearch = $state("");
  let storedItems = $state<StoredItem[]>([]);
  let loadingItems = $state(false);

  type Form = {
    name: string;
    url: string;
    enabled: boolean;
    poll_interval_seconds: number;
    retention_days: number;
    protocol_hint: "torrent" | "usenet";
  };
  const empty = (): Form => ({
    name: "",
    url: "",
    enabled: true,
    poll_interval_seconds: 600,
    retention_days: 90,
    protocol_hint: "torrent"
  });
  let form = $state<Form>(empty());

  function normalizeUrl(raw: string): string {
    return raw.trim().replace(/^(https?:\/\/)+(https?:\/\/)/i, "$2");
  }

  async function load() {
    loading = true;
    feeds = await api.feeds.list();
    loading = false;
  }

  onMount(load);

  function openNew() {
    form = empty();
    editingId = null;
    formError = null;
    previewItems = null;
    showForm = true;
  }

  function openEdit(feed: Feed) {
    form = {
      name: feed.name,
      url: feed.url,
      enabled: feed.enabled,
      poll_interval_seconds: feed.poll_interval_seconds,
      retention_days: feed.retention_days,
      protocol_hint: feed.protocol_hint as "torrent" | "usenet"
    };
    editingId = feed.id;
    formError = null;
    previewItems = null;
    showForm = true;
  }

  async function submit(event: Event) {
    event.preventDefault();
    saving = true;
    formError = null;
    const payload = {
      name: form.name,
      url: normalizeUrl(form.url),
      enabled: form.enabled,
      poll_interval_seconds: form.poll_interval_seconds,
      retention_days: form.retention_days,
      protocol_hint: form.protocol_hint
    };
    try {
      if (editingId !== null) {
        await api.feeds.update(editingId, payload);
      } else {
        await api.feeds.create(payload);
      }
      showForm = false;
      editingId = null;
      await load();
    } catch (e) {
      const err = e as { status?: number; detail?: string };
      formError = err.status === 409 ? "Name already used." : err.detail ?? "Save failed.";
    } finally {
      saving = false;
    }
  }

  async function runPreview() {
    previewing = true;
    previewItems = null;
    try {
      previewItems = await api.feeds.preview(normalizeUrl(form.url));
    } catch (e) {
      formError = (e as { detail?: string }).detail ?? "Preview failed";
    } finally {
      previewing = false;
    }
  }

  async function pollNow(feed: Feed) {
    pollingId = feed.id;
    try {
      const r = await api.feeds.poll(feed.id);
      if (!r.ok) alert(`Poll failed: ${r.error}`);
      await load();
      if (expandedFeedId === feed.id) await loadItems(feed.id);
    } finally {
      pollingId = null;
    }
  }

  async function remove(feed: Feed) {
    if (!confirm(`Delete feed "${feed.name}" and all its cached items?`)) return;
    await api.feeds.remove(feed.id);
    if (expandedFeedId === feed.id) {
      expandedFeedId = null;
      storedItems = [];
    }
    await load();
  }

  async function toggleExpand(feed: Feed) {
    if (expandedFeedId === feed.id) {
      expandedFeedId = null;
      return;
    }
    expandedFeedId = feed.id;
    itemSearch = "";
    await loadItems(feed.id);
  }

  async function loadItems(feedId: number) {
    loadingItems = true;
    try {
      storedItems = await api.feeds.items(feedId, itemSearch || undefined);
    } finally {
      loadingItems = false;
    }
  }

  async function searchItems() {
    if (expandedFeedId) await loadItems(expandedFeedId);
  }

  function formatBytes(size: number | null): string {
    if (!size) return "?";
    const units = ["B", "KB", "MB", "GB", "TB"];
    let v = size;
    let i = 0;
    while (v >= 1024 && i < units.length - 1) {
      v /= 1024;
      i++;
    }
    return `${v.toFixed(1)} ${units[i]}`;
  }

  function formatTime(iso: string | null): string {
    if (!iso) return "never";
    return new Date(iso).toLocaleString();
  }

  function formatInterval(seconds: number): string {
    if (seconds < 60) return `${seconds}s`;
    const m = Math.floor(seconds / 60);
    if (m < 60) return `${m}m`;
    const h = Math.floor(m / 60);
    return `${h}h ${m % 60}m`;
  }
</script>

<div class="space-y-6">
  <div class="flex items-center justify-between">
    <div>
      <h2 class="flex items-center gap-2 text-xl font-semibold">
        <Rss class="h-5 w-5 text-primary" /> RSS Feeds
      </h2>
      <p class="mt-1 text-sm text-muted-foreground">
        Poll RSS feeds on a schedule and build a searchable local history.
      </p>
    </div>
    <button
      class="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
      onclick={openNew}
    >
      <Plus class="h-4 w-4" /> Add feed
    </button>
  </div>

  {#if loading}
    <div class="text-sm text-muted-foreground">Loading…</div>
  {:else if feeds.length === 0}
    <div class="rounded-xl border border-dashed border-border bg-card p-10 text-center">
      <Rss class="mx-auto mb-3 h-6 w-6 text-muted-foreground" />
      <div class="text-base font-medium">No feeds yet</div>
      <p class="mt-1 text-sm text-muted-foreground">
        Add a tracker RSS feed and Trove will poll it on a schedule.
      </p>
    </div>
  {:else}
    <div class="space-y-3">
      {#each feeds as feed (feed.id)}
        <div class="rounded-xl border border-border bg-card">
          <div class="flex items-start justify-between gap-3 p-4">
            <button class="min-w-0 flex-1 text-left" onclick={() => toggleExpand(feed)}>
              <div class="flex items-center gap-2">
                <Rss class="h-4 w-4 shrink-0 text-primary" />
                <span class="truncate font-medium">{feed.name}</span>
                <span class="rounded-full bg-muted px-2 py-0.5 text-[10px] uppercase">
                  {feed.protocol_hint}
                </span>
                {#if !feed.enabled}
                  <span class="text-[10px] uppercase text-muted-foreground">disabled</span>
                {/if}
              </div>
              <div class="mt-1 truncate font-mono text-xs text-muted-foreground">{feed.url}</div>
              <div class="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
                <span>{feed.total_items} items stored</span>
                <span>poll every {formatInterval(feed.poll_interval_seconds)}</span>
                <span>retention {feed.retention_days}d</span>
                {#if feed.last_polled_at}
                  <span class="flex items-center gap-1">
                    {#if feed.last_poll_status === "ok"}
                      <CheckCircle2 class="h-3 w-3 text-green-600" />
                    {:else}
                      <XCircle class="h-3 w-3 text-destructive" />
                    {/if}
                    last poll {formatTime(feed.last_polled_at)}
                    {#if feed.last_new_items > 0}
                      (+{feed.last_new_items})
                    {/if}
                  </span>
                {/if}
                {#if feed.last_poll_message}
                  <span class="text-destructive">{feed.last_poll_message}</span>
                {/if}
              </div>
            </button>
            <div class="flex shrink-0 flex-col gap-1">
              <button
                class="inline-flex items-center gap-1 rounded-md border border-border bg-background px-3 py-1.5 text-xs hover:bg-muted"
                onclick={() => pollNow(feed)}
                disabled={pollingId === feed.id}
              >
                {#if pollingId === feed.id}
                  <Loader2 class="h-3.5 w-3.5 animate-spin" />
                {:else}
                  <RefreshCw class="h-3.5 w-3.5" />
                {/if}
                Poll
              </button>
              <button
                class="inline-flex items-center gap-1 rounded-md border border-border bg-background px-3 py-1.5 text-xs hover:bg-muted"
                onclick={() => openEdit(feed)}
              >
                <Pencil class="h-3.5 w-3.5" />
                Edit
              </button>
              <button
                class="inline-flex items-center gap-1 rounded-md border border-border bg-background px-3 py-1.5 text-xs text-destructive hover:bg-destructive/10"
                onclick={() => remove(feed)}
              >
                <Trash2 class="h-3.5 w-3.5" />
                Delete
              </button>
            </div>
          </div>

          {#if expandedFeedId === feed.id}
            <div class="border-t border-border p-4">
              <div class="mb-3 flex items-center gap-2">
                <div class="relative flex-1">
                  <Search class="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
                  <input
                    type="text"
                    bind:value={itemSearch}
                    onkeydown={(e) => e.key === "Enter" && searchItems()}
                    placeholder="Search cached items…"
                    class="w-full rounded-md border border-input bg-background py-1.5 pl-8 pr-3 text-sm outline-none ring-ring focus:ring-2"
                  />
                </div>
                <button
                  class="rounded-md border border-border bg-background px-3 py-1.5 text-xs hover:bg-muted"
                  onclick={searchItems}
                >
                  Search
                </button>
              </div>

              {#if loadingItems}
                <div class="py-4 text-center text-xs text-muted-foreground">Loading…</div>
              {:else if storedItems.length === 0}
                <div class="py-4 text-center text-xs text-muted-foreground">No items yet.</div>
              {:else}
                <div class="max-h-96 overflow-y-auto">
                  <table class="w-full text-xs">
                    <thead class="sticky top-0 bg-card text-left text-[10px] uppercase tracking-wide text-muted-foreground">
                      <tr>
                        <th class="pb-2 pr-2">Title</th>
                        <th class="pb-2 pr-2">Size</th>
                        <th class="pb-2 pr-2">S/L</th>
                        <th class="pb-2">Published</th>
                      </tr>
                    </thead>
                    <tbody>
                      {#each storedItems as item (item.id)}
                        <tr class="border-t border-border/50">
                          <td class="max-w-md truncate py-1.5 pr-2">{item.title}</td>
                          <td class="py-1.5 pr-2">{formatBytes(item.size)}</td>
                          <td class="py-1.5 pr-2">
                            {item.seeders ?? "—"}/{item.leechers ?? "—"}
                          </td>
                          <td class="py-1.5 text-muted-foreground">
                            {item.published_at ? formatTime(item.published_at) : "—"}
                          </td>
                        </tr>
                      {/each}
                    </tbody>
                  </table>
                </div>
              {/if}
            </div>
          {/if}
        </div>
      {/each}
    </div>
  {/if}
</div>

{#if showForm}
  <div class="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-background/80 p-6 backdrop-blur-sm">
    <form
      onsubmit={submit}
      class="mt-10 w-full max-w-xl rounded-2xl border border-border bg-card p-6 shadow-2xl"
    >
      <div class="mb-4 flex items-center justify-between">
        <h3 class="text-lg font-semibold">
          {editingId !== null ? "Edit feed" : "Add RSS feed"}
        </h3>
        <button
          type="button"
          class="rounded-md p-1 text-muted-foreground hover:bg-muted"
          onclick={() => {
            showForm = false;
            editingId = null;
          }}
          aria-label="Close"
        >
          ✕
        </button>
      </div>

      <div class="space-y-3">
        <label class="block">
          <span class="mb-1 block text-sm font-medium">Name</span>
          <input
            type="text"
            bind:value={form.name}
            required
            class="w-full rounded-md border border-input bg-background px-3 py-2 text-sm outline-none ring-ring focus:ring-2"
          />
        </label>

        <label class="block">
          <span class="mb-1 block text-sm font-medium">RSS URL</span>
          <input
            type="url"
            bind:value={form.url}
            required
            placeholder="https://tracker.example/rss.php?uid=123&key=abc"
            class="w-full rounded-md border border-input bg-background px-3 py-2 font-mono text-xs outline-none ring-ring focus:ring-2"
          />
          <span class="mt-1 block text-xs text-muted-foreground">
            Include authentication tokens directly in the URL, or use credential fields (coming soon).
          </span>
        </label>

        <div class="grid grid-cols-3 gap-3">
          <label class="block">
            <span class="mb-1 block text-sm font-medium">Protocol</span>
            <select
              bind:value={form.protocol_hint}
              class="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
            >
              <option value="torrent">Torrent</option>
              <option value="usenet">Usenet</option>
            </select>
          </label>
          <label class="block">
            <span class="mb-1 block text-sm font-medium">Poll interval (s)</span>
            <input
              type="number"
              min="60"
              bind:value={form.poll_interval_seconds}
              class="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
            />
          </label>
          <label class="block">
            <span class="mb-1 block text-sm font-medium">Retention (days)</span>
            <input
              type="number"
              min="1"
              bind:value={form.retention_days}
              class="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
            />
          </label>
        </div>

        <label class="flex items-center gap-2 text-sm">
          <input type="checkbox" bind:checked={form.enabled} />
          Enabled (scheduler will poll on the interval)
        </label>

        <div class="rounded-lg border border-border bg-muted/30 p-3">
          <div class="flex items-center justify-between">
            <span class="text-sm font-medium">Preview</span>
            <button
              type="button"
              class="inline-flex items-center gap-1 rounded-md border border-border bg-background px-3 py-1 text-xs hover:bg-muted"
              onclick={runPreview}
              disabled={previewing || !form.url}
            >
              {#if previewing}
                <Loader2 class="h-3 w-3 animate-spin" />
              {:else}
                <Eye class="h-3 w-3" />
              {/if}
              Preview feed
            </button>
          </div>
          {#if previewItems && previewItems.length > 0}
            <div class="mt-2 max-h-56 overflow-y-auto">
              <table class="w-full text-[10px]">
                <tbody>
                  {#each previewItems as p}
                    <tr class="border-t border-border/50">
                      <td class="max-w-[300px] truncate py-1 pr-2">{p.title}</td>
                      <td class="py-1 pr-2 text-muted-foreground">{formatBytes(p.size)}</td>
                      <td class="py-1 text-muted-foreground">
                        {p.seeders ?? "—"}/{p.leechers ?? "—"}
                      </td>
                    </tr>
                  {/each}
                </tbody>
              </table>
            </div>
          {:else if previewItems && previewItems.length === 0}
            <div class="mt-2 text-xs text-muted-foreground">Feed returned 0 entries.</div>
          {/if}
        </div>
      </div>

      {#if formError}
        <div class="mt-4 rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {formError}
        </div>
      {/if}

      <div class="mt-6 flex justify-end gap-2">
        <button
          type="button"
          class="rounded-md border border-border bg-background px-4 py-2 text-sm hover:bg-muted"
          onclick={() => {
            showForm = false;
            editingId = null;
          }}
        >
          Cancel
        </button>
        <button
          type="submit"
          class="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-60"
          disabled={saving}
        >
          {saving ? "Saving…" : editingId !== null ? "Update feed" : "Save feed"}
        </button>
      </div>
    </form>
  </div>
{/if}
