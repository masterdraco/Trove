<script lang="ts">
  import { onMount } from "svelte";
  import {
    api,
    type IndexerOut,
    type IndexerType,
    type Protocol,
    type IndexerHealthOut
  } from "$lib/api";
  import {
    Plus,
    Trash2,
    PlugZap,
    Loader2,
    CheckCircle2,
    XCircle,
    Database,
    Pencil,
    Activity
  } from "lucide-svelte";

  let items = $state<IndexerOut[]>([]);
  let healthById = $state<Record<number, IndexerHealthOut>>({});
  let loading = $state(true);
  let showForm = $state(false);
  let saving = $state(false);
  let formError = $state<string | null>(null);
  let testingId = $state<number | null>(null);
  let editingId = $state<number | null>(null);

  function formatRelative(iso: string | null): string {
    if (!iso) return "never";
    const then = new Date(iso).getTime();
    const diff = Date.now() - then;
    if (diff < 0) return "just now";
    const mins = Math.floor(diff / 60_000);
    if (mins < 1) return "just now";
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    const days = Math.floor(hrs / 24);
    return `${days}d ago`;
  }

  function sparklineSvg(sparkline: number[][]): string {
    // Each entry is [count, failures, avg_ms]. Render two stacked bars per hour:
    // total event count (blue), failures (red overlay). 24 bars, width 96px.
    if (!sparkline || sparkline.length === 0) return "";
    const w = 96;
    const h = 22;
    const barW = w / sparkline.length;
    const maxCount = Math.max(1, ...sparkline.map((b) => b[0] || 0));
    let out = `<svg viewBox="0 0 ${w} ${h}" xmlns="http://www.w3.org/2000/svg" class="h-5 w-24">`;
    sparkline.forEach((b, i) => {
      const count = b[0] || 0;
      const fails = b[1] || 0;
      const cH = count > 0 ? Math.max(1, (count / maxCount) * h) : 0;
      const fH = fails > 0 ? Math.max(1, (fails / maxCount) * h) : 0;
      const x = i * barW;
      if (cH > 0) {
        out += `<rect x="${x.toFixed(1)}" y="${(h - cH).toFixed(1)}" width="${(barW - 0.5).toFixed(1)}" height="${cH.toFixed(1)}" fill="hsl(200 80% 55% / 0.75)" />`;
      }
      if (fH > 0) {
        out += `<rect x="${x.toFixed(1)}" y="${(h - fH).toFixed(1)}" width="${(barW - 0.5).toFixed(1)}" height="${fH.toFixed(1)}" fill="hsl(0 85% 60%)" />`;
      }
    });
    out += "</svg>";
    return out;
  }

  type Form = {
    name: string;
    type: IndexerType;
    protocol: Protocol;
    base_url: string;
    api_key: string;
    definition_yaml: string;
    session_cookie: string;
    passkey: string;
  };

  const empty = (): Form => ({
    name: "",
    type: "newznab",
    protocol: "usenet",
    base_url: "",
    api_key: "",
    definition_yaml: "",
    session_cookie: "",
    passkey: ""
  });

  function normalizeUrl(raw: string): string {
    let u = raw.trim();
    u = u.replace(/^(https?:\/\/)+(https?:\/\/)/i, "$2");
    return u;
  }

  let form = $state<Form>(empty());

  async function load() {
    loading = true;
    items = await api.indexers.list();
    loading = false;
    // Fetch health in the background — not blocking the initial render.
    loadHealth();
  }

  async function loadHealth() {
    try {
      const rows = await api.indexers.health();
      const next: Record<number, IndexerHealthOut> = {};
      for (const r of rows) next[r.id] = r;
      healthById = next;
    } catch {
      // Non-fatal — health is observability, not core functionality.
    }
  }

  onMount(load);

  function openForm() {
    form = empty();
    formError = null;
    editingId = null;
    showForm = true;
  }

  function openEdit(item: IndexerOut) {
    form = {
      name: item.name,
      type: item.type,
      protocol: item.protocol,
      base_url: item.base_url,
      api_key: "",
      definition_yaml: "",
      session_cookie: "",
      passkey: ""
    };
    editingId = item.id;
    formError = null;
    showForm = true;
  }

  async function submit(event: Event) {
    event.preventDefault();
    saving = true;
    formError = null;
    const cleanUrl = normalizeUrl(form.base_url);
    try {
      const buildCreds = (): Record<string, unknown> => {
        if (form.type === "cardigann") return {};
        if (form.type === "rartracker") {
          const c: Record<string, unknown> = {};
          if (form.session_cookie) c.session_cookie = form.session_cookie;
          if (form.passkey) c.passkey = form.passkey;
          return c;
        }
        return form.api_key ? { api_key: form.api_key } : {};
      };

      if (editingId !== null) {
        const payload: Record<string, unknown> = {
          name: form.name,
          base_url: cleanUrl
        };
        const creds = buildCreds();
        if (Object.keys(creds).length > 0) payload.credentials = creds;
        if (form.type === "cardigann" && form.definition_yaml) {
          payload.definition_yaml = form.definition_yaml;
        }
        await api.indexers.update(editingId, payload);
      } else {
        await api.indexers.create({
          name: form.name,
          type: form.type,
          protocol: form.protocol,
          base_url: cleanUrl,
          credentials: buildCreds(),
          definition_yaml: form.type === "cardigann" ? form.definition_yaml : null
        });
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

  async function testOne(item: IndexerOut) {
    testingId = item.id;
    try {
      await api.indexers.test(item.id);
      await load();
    } finally {
      testingId = null;
    }
  }

  async function remove(item: IndexerOut) {
    if (!confirm(`Delete indexer "${item.name}"?`)) return;
    await api.indexers.remove(item.id);
    await load();
  }

  function formatTime(iso: string | null): string {
    if (!iso) return "never";
    return new Date(iso).toLocaleString();
  }
</script>

<div class="space-y-6">
  <div class="flex items-center justify-between">
    <div>
      <h2 class="text-xl font-semibold">Indexers</h2>
      <p class="mt-1 text-sm text-muted-foreground">
        Newznab/Torznab APIs and Cardigann-style YAML trackers.
      </p>
    </div>
    <button
      class="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
      onclick={openForm}
    >
      <Plus class="h-4 w-4" /> Add indexer
    </button>
  </div>

  {#if loading}
    <div class="rounded-xl border border-border bg-card p-8 text-center text-sm text-muted-foreground">
      Loading…
    </div>
  {:else if items.length === 0}
    <div class="rounded-xl border border-dashed border-border bg-card p-10 text-center">
      <div class="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-muted">
        <Database class="h-5 w-5 text-muted-foreground" />
      </div>
      <div class="text-base font-medium">No indexers configured</div>
      <p class="mt-1 text-sm text-muted-foreground">
        Add a Newznab URL + API key to start searching.
      </p>
    </div>
  {:else}
    <div class="overflow-hidden rounded-xl border border-border bg-card">
      <table class="w-full text-sm">
        <thead class="bg-muted/50 text-left text-xs uppercase tracking-wide text-muted-foreground">
          <tr>
            <th class="px-4 py-3 font-medium">Name</th>
            <th class="px-4 py-3 font-medium">Type</th>
            <th class="px-4 py-3 font-medium">URL</th>
            <th class="px-4 py-3 font-medium">Last test</th>
            <th class="px-4 py-3 font-medium">Activity (24h)</th>
            <th class="px-4 py-3 font-medium"></th>
          </tr>
        </thead>
        <tbody>
          {#each items as item (item.id)}
            {@const h = healthById[item.id]}
            <tr class="border-t border-border">
              <td class="px-4 py-3 font-medium">{item.name}</td>
              <td class="px-4 py-3">
                <span class="inline-flex items-center rounded-full bg-muted px-2 py-0.5 text-xs">
                  {item.type}
                </span>
                <span class="ml-2 text-xs text-muted-foreground">{item.protocol}</span>
              </td>
              <td class="px-4 py-3 font-mono text-xs text-muted-foreground">{item.base_url}</td>
              <td class="px-4 py-3">
                {#if item.last_test_at}
                  <div class="flex items-center gap-1.5 text-xs">
                    {#if item.last_test_ok}
                      <CheckCircle2 class="h-3.5 w-3.5 text-green-600" />
                      <span>ok</span>
                    {:else}
                      <XCircle class="h-3.5 w-3.5 text-destructive" />
                      <span class="text-destructive">{item.last_test_message ?? "failed"}</span>
                    {/if}
                  </div>
                  <div class="text-xs text-muted-foreground">{formatTime(item.last_test_at)}</div>
                {:else}
                  <span class="text-xs text-muted-foreground">never</span>
                {/if}
              </td>
              <td class="px-4 py-3">
                {#if h && h.events_24h > 0}
                  <div class="flex items-center gap-2">
                    {@html sparklineSvg(h.sparkline)}
                    <div class="text-xs leading-tight">
                      <div>
                        <span class="font-semibold">{h.successes_24h}</span>
                        <span class="text-muted-foreground">/ {h.events_24h} ok</span>
                      </div>
                      <div class="text-muted-foreground">
                        {h.avg_elapsed_ms_24h ?? 0} ms avg · {h.total_hits_24h} hits
                      </div>
                    </div>
                  </div>
                  {#if h.failures_24h > 0 && h.last_error_message}
                    <div
                      class="mt-1 truncate text-xs text-destructive"
                      title={h.last_error_message}
                    >
                      ⚠ {h.last_error_message}
                    </div>
                  {/if}
                {:else if h}
                  <div class="flex items-center gap-1.5 text-xs text-muted-foreground">
                    <Activity class="h-3.5 w-3.5" />
                    <span>no searches in the last 24h</span>
                  </div>
                {:else}
                  <span class="text-xs text-muted-foreground">…</span>
                {/if}
              </td>
              <td class="px-4 py-3 text-right">
                <div class="flex justify-end gap-2">
                  <button
                    class="inline-flex items-center gap-1 rounded-md border border-border bg-background px-3 py-1.5 text-xs hover:bg-muted"
                    onclick={() => testOne(item)}
                    disabled={testingId === item.id}
                  >
                    {#if testingId === item.id}
                      <Loader2 class="h-3.5 w-3.5 animate-spin" />
                    {:else}
                      <PlugZap class="h-3.5 w-3.5" />
                    {/if}
                    Test
                  </button>
                  <button
                    class="inline-flex items-center gap-1 rounded-md border border-border bg-background px-3 py-1.5 text-xs hover:bg-muted"
                    onclick={() => openEdit(item)}
                  >
                    <Pencil class="h-3.5 w-3.5" />
                    Edit
                  </button>
                  <button
                    class="inline-flex items-center gap-1 rounded-md border border-border bg-background px-3 py-1.5 text-xs text-destructive hover:bg-destructive/10"
                    onclick={() => remove(item)}
                  >
                    <Trash2 class="h-3.5 w-3.5" />
                    Delete
                  </button>
                </div>
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}
</div>

{#if showForm}
  <div
    class="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-background/80 p-6 backdrop-blur-sm"
  >
    <form
      onsubmit={submit}
      class="mt-10 w-full max-w-xl rounded-2xl border border-border bg-card p-6 shadow-2xl"
    >
      <div class="mb-4 flex items-center justify-between">
        <h3 class="text-lg font-semibold">
          {editingId !== null ? "Edit indexer" : "Add indexer"}
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

      <div class="space-y-4">
        <label class="block">
          <span class="mb-1 block text-sm font-medium">Name</span>
          <input
            type="text"
            bind:value={form.name}
            required
            class="w-full rounded-md border border-input bg-background px-3 py-2 text-sm outline-none ring-ring focus:ring-2"
          />
        </label>

        <div class="grid grid-cols-2 gap-3">
          <label class="block">
            <span class="mb-1 block text-sm font-medium">Type</span>
            <select
              bind:value={form.type}
              disabled={editingId !== null}
              class="w-full rounded-md border border-input bg-background px-3 py-2 text-sm outline-none ring-ring focus:ring-2 disabled:opacity-60"
            >
              <option value="newznab">Newznab (Usenet)</option>
              <option value="torznab">Torznab (Torrents)</option>
              <option value="cardigann">Cardigann (YAML)</option>
              <option value="unit3d">UNIT3D (Aither, Blutopia, Nordicbytes, …)</option>
              <option value="rartracker">RarTracker (Superbits, ScenePalace, …)</option>
            </select>
          </label>
          <label class="block">
            <span class="mb-1 block text-sm font-medium">Protocol</span>
            <select
              bind:value={form.protocol}
              disabled={editingId !== null}
              class="w-full rounded-md border border-input bg-background px-3 py-2 text-sm outline-none ring-ring focus:ring-2 disabled:opacity-60"
            >
              <option value="usenet">Usenet (NZB)</option>
              <option value="torrent">Torrent</option>
            </select>
          </label>
        </div>

        <label class="block">
          <span class="mb-1 block text-sm font-medium">Base URL</span>
          <input
            type="url"
            bind:value={form.base_url}
            required
            placeholder="https://api.example.com"
            class="w-full rounded-md border border-input bg-background px-3 py-2 font-mono text-sm outline-none ring-ring focus:ring-2"
          />
        </label>

        {#if form.type === "rartracker"}
          <label class="block">
            <span class="mb-1 block text-sm font-medium">Session cookie</span>
            <textarea
              bind:value={form.session_cookie}
              rows="3"
              required={editingId === null}
              placeholder={editingId !== null
                ? "•••••• (leave blank to keep existing)"
                : "PHPSESSID=abc123; rartracker=def456"}
              class="w-full rounded-md border border-input bg-background px-3 py-2 font-mono text-xs outline-none ring-ring focus:ring-2"
            ></textarea>
            <span class="mt-1 block text-xs text-muted-foreground">
              Log in to the tracker in your browser, open DevTools → Application → Cookies,
              and copy the full cookie header for the tracker domain. Session cookies expire —
              you'll need to re-paste when searches start failing with "session expired".
            </span>
          </label>
          <label class="block">
            <span class="mb-1 block text-sm font-medium">Passkey</span>
            <input
              type="password"
              bind:value={form.passkey}
              placeholder={editingId !== null ? "•••••• (leave blank to keep)" : ""}
              class="w-full rounded-md border border-input bg-background px-3 py-2 text-sm outline-none ring-ring focus:ring-2"
            />
            <span class="mt-1 block text-xs text-muted-foreground">
              From your tracker profile page — used to build download URLs. Optional for
              testing the search; required for actually grabbing torrents.
            </span>
          </label>
        {:else if form.type !== "cardigann"}
          <label class="block">
            <span class="mb-1 block text-sm font-medium">API key</span>
            <input
              type="password"
              bind:value={form.api_key}
              required={editingId === null}
              placeholder={editingId !== null ? "•••••• (leave blank to keep)" : ""}
              class="w-full rounded-md border border-input bg-background px-3 py-2 text-sm outline-none ring-ring focus:ring-2"
            />
          </label>
        {:else}
          <label class="block">
            <span class="mb-1 block text-sm font-medium">Cardigann YAML definition</span>
            <textarea
              bind:value={form.definition_yaml}
              rows="10"
              required={editingId === null}
              placeholder={editingId !== null
                ? "# leave blank to keep existing definition"
                : "# paste a Cardigann YAML definition here"}
              class="w-full rounded-md border border-input bg-background px-3 py-2 font-mono text-xs outline-none ring-ring focus:ring-2"
            ></textarea>
            <span class="mt-1 block text-xs text-muted-foreground">
              Only search-only definitions without login are supported in v1.
            </span>
          </label>
        {/if}
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
          {saving ? "Saving…" : editingId !== null ? "Update indexer" : "Save indexer"}
        </button>
      </div>
    </form>
  </div>
{/if}
