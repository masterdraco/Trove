<script lang="ts">
  import { onMount } from "svelte";
  import { api, type BrowseCategory, type Protocol } from "$lib/api";
  import { Bell, Plus, Loader2, Play, Trash2, Save, X } from "lucide-svelte";

  type AlertRow = Awaited<ReturnType<typeof api.alerts.list>>[number];

  const CATEGORIES: BrowseCategory[] = [
    "movies",
    "tv",
    "anime",
    "games",
    "software",
    "music",
    "books",
    "audiobooks",
    "comics",
    "other"
  ];

  let alerts = $state<AlertRow[]>([]);
  let loading = $state(false);
  let showForm = $state(false);
  let editingId = $state<number | null>(null);
  let runningId = $state<number | null>(null);
  let error = $state<string | null>(null);

  let formName = $state("");
  let formCategory = $state<BrowseCategory>("movies");
  let formKeywords = $state("");
  let formProtocol = $state<Protocol | "">("");
  let formEnabled = $state(true);
  let formInterval = $state(30);

  onMount(load);

  async function load() {
    loading = true;
    try {
      alerts = await api.alerts.list();
    } catch (e) {
      error = (e as { detail?: string }).detail ?? "failed to load";
    } finally {
      loading = false;
    }
  }

  function resetForm() {
    formName = "";
    formCategory = "movies";
    formKeywords = "";
    formProtocol = "";
    formEnabled = true;
    formInterval = 30;
    editingId = null;
  }

  function startCreate() {
    resetForm();
    showForm = true;
  }

  function startEdit(row: AlertRow) {
    editingId = row.id;
    formName = row.name;
    formCategory = row.category as BrowseCategory;
    formKeywords = row.keywords;
    formProtocol = (row.protocol as Protocol | null) ?? "";
    formEnabled = row.enabled;
    formInterval = row.check_interval_minutes;
    showForm = true;
  }

  async function submit(event: Event) {
    event.preventDefault();
    if (!formName.trim()) return;
    const payload = {
      name: formName,
      category: formCategory,
      keywords: formKeywords,
      protocol: (formProtocol || null) as Protocol | null,
      enabled: formEnabled,
      check_interval_minutes: formInterval
    };
    try {
      if (editingId !== null) {
        await api.alerts.update(editingId, payload);
      } else {
        await api.alerts.create(payload);
      }
      showForm = false;
      resetForm();
      await load();
    } catch (e) {
      alert((e as { detail?: string }).detail ?? "save failed");
    }
  }

  async function runNow(row: AlertRow) {
    runningId = row.id;
    try {
      const res = await api.alerts.run(row.id);
      alert(`${res.new_matches} new match${res.new_matches === 1 ? "" : "es"} dispatched.`);
      await load();
    } catch (e) {
      alert((e as { detail?: string }).detail ?? "run failed");
    } finally {
      runningId = null;
    }
  }

  async function remove(row: AlertRow) {
    if (!confirm(`Delete alert "${row.name}"?`)) return;
    try {
      await api.alerts.remove(row.id);
      await load();
    } catch (e) {
      alert((e as { detail?: string }).detail ?? "delete failed");
    }
  }

  function fmtDate(iso: string | null): string {
    if (!iso) return "never";
    const d = new Date(iso);
    return isNaN(d.getTime()) ? iso : d.toLocaleString();
  }
</script>

<div class="space-y-6">
  <div class="flex items-center justify-between">
    <div>
      <h1 class="text-2xl font-bold tracking-tight">Alerts</h1>
      <p class="mt-1 text-sm text-muted-foreground">
        Get notified when a new release matches your saved query.
      </p>
    </div>
    <button
      type="button"
      onclick={startCreate}
      class="inline-flex items-center gap-2 rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
    >
      <Plus class="h-4 w-4" /> New alert
    </button>
  </div>

  {#if error}
    <div class="rounded-md border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-600 dark:text-red-400">
      {error}
    </div>
  {/if}

  {#if showForm}
    <form
      onsubmit={submit}
      class="space-y-3 rounded-xl border border-border bg-card p-4"
    >
      <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <label class="space-y-1 text-sm">
          <div class="font-medium">Name</div>
          <input
            type="text"
            bind:value={formName}
            required
            placeholder="e.g. Elden Ring updates"
            class="w-full rounded-md border border-input bg-background px-3 py-2 text-sm outline-none ring-ring focus:ring-2"
          />
        </label>
        <label class="space-y-1 text-sm">
          <div class="font-medium">Category</div>
          <select
            bind:value={formCategory}
            class="w-full rounded-md border border-input bg-background px-3 py-2 text-sm outline-none"
          >
            {#each CATEGORIES as cat}
              <option value={cat}>{cat}</option>
            {/each}
          </select>
        </label>
      </div>

      <label class="block space-y-1 text-sm">
        <div class="font-medium">Keywords (comma-separated, empty = all)</div>
        <input
          type="text"
          bind:value={formKeywords}
          placeholder="e.g. elden ring, shadow of the erdtree"
          class="w-full rounded-md border border-input bg-background px-3 py-2 text-sm outline-none"
        />
      </label>

      <div class="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <label class="space-y-1 text-sm">
          <div class="font-medium">Protocol</div>
          <select
            bind:value={formProtocol}
            class="w-full rounded-md border border-input bg-background px-3 py-2 text-sm outline-none"
          >
            <option value="">any</option>
            <option value="torrent">torrent</option>
            <option value="usenet">usenet</option>
          </select>
        </label>
        <label class="space-y-1 text-sm">
          <div class="font-medium">Check every (min)</div>
          <input
            type="number"
            bind:value={formInterval}
            min="5"
            max="1440"
            class="w-full rounded-md border border-input bg-background px-3 py-2 text-sm outline-none"
          />
        </label>
        <label class="flex items-end gap-2 text-sm">
          <input type="checkbox" bind:checked={formEnabled} class="h-4 w-4" />
          <span>Enabled</span>
        </label>
      </div>

      <div class="flex items-center gap-2">
        <button
          type="submit"
          class="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
        >
          <Save class="h-4 w-4" /> {editingId !== null ? "Save changes" : "Create alert"}
        </button>
        <button
          type="button"
          onclick={() => {
            showForm = false;
            resetForm();
          }}
          class="inline-flex items-center gap-2 rounded-md border border-border bg-background px-4 py-2 text-sm hover:bg-muted"
        >
          <X class="h-4 w-4" /> Cancel
        </button>
      </div>
    </form>
  {/if}

  {#if loading && alerts.length === 0}
    <div class="rounded-xl border border-dashed border-border bg-card p-10 text-center text-sm text-muted-foreground">
      <Loader2 class="mx-auto mb-3 h-6 w-6 animate-spin" />
      Loading…
    </div>
  {:else if alerts.length === 0}
    <div class="rounded-xl border border-dashed border-border bg-card p-10 text-center text-sm text-muted-foreground">
      <Bell class="mx-auto mb-3 h-6 w-6" />
      No alerts yet. Create one to get pinged when new releases match.
    </div>
  {:else}
    <div class="overflow-hidden rounded-xl border border-border bg-card">
      <table class="w-full text-sm">
        <thead class="bg-muted/50 text-left text-xs uppercase tracking-wide text-muted-foreground">
          <tr>
            <th class="px-4 py-3 font-medium">Name</th>
            <th class="px-4 py-3 font-medium">Category</th>
            <th class="px-4 py-3 font-medium">Keywords</th>
            <th class="px-4 py-3 font-medium">Every</th>
            <th class="px-4 py-3 font-medium">Last check</th>
            <th class="px-4 py-3 font-medium">Status</th>
            <th class="px-4 py-3 font-medium"></th>
          </tr>
        </thead>
        <tbody>
          {#each alerts as row}
            <tr class="border-t border-border">
              <td class="px-4 py-3">
                <button
                  type="button"
                  class="font-medium hover:underline"
                  onclick={() => startEdit(row)}
                >
                  {row.name}
                </button>
              </td>
              <td class="px-4 py-3 text-xs">{row.category}</td>
              <td class="px-4 py-3 text-xs text-muted-foreground">
                {row.keywords || "—"}
              </td>
              <td class="px-4 py-3 text-xs">{row.check_interval_minutes}m</td>
              <td class="whitespace-nowrap px-4 py-3 text-xs text-muted-foreground">
                {fmtDate(row.last_check_at)}
              </td>
              <td class="px-4 py-3 text-xs">
                <span
                  class="rounded-full px-2 py-0.5 text-[11px] {row.enabled
                    ? 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400'
                    : 'bg-muted text-muted-foreground'}"
                >
                  {row.enabled ? "active" : "paused"}
                </span>
              </td>
              <td class="px-4 py-3 text-right">
                <button
                  type="button"
                  onclick={() => runNow(row)}
                  disabled={runningId === row.id}
                  class="ml-1 inline-flex items-center gap-1 rounded-md border border-border bg-background px-2 py-1 text-xs hover:bg-muted"
                  title="Run now"
                >
                  {#if runningId === row.id}
                    <Loader2 class="h-3 w-3 animate-spin" />
                  {:else}
                    <Play class="h-3 w-3" />
                  {/if}
                  Run
                </button>
                <button
                  type="button"
                  onclick={() => remove(row)}
                  class="ml-1 inline-flex items-center gap-1 rounded-md border border-border bg-background px-2 py-1 text-xs text-red-600 hover:bg-red-500/10 dark:text-red-400"
                  title="Delete"
                >
                  <Trash2 class="h-3 w-3" />
                </button>
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}
</div>
