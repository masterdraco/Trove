<script lang="ts">
  import { onMount } from "svelte";
  import { page } from "$app/stores";
  import {
    api,
    type SearchHit,
    type DownloadClientOut,
    type Protocol,
    type Category
  } from "$lib/api";
  import { Search, Sparkles, Loader2, Send, Filter } from "lucide-svelte";

  let query = $state("");
  let categories = $state<Category[]>([]);
  let protocol = $state<Protocol | "">("");
  let minSeeders = $state<number | null>(null);
  let maxSizeMb = $state<number | null>(null);
  let useAI = $state(false);

  let loading = $state(false);
  let hits = $state<SearchHit[]>([]);
  let elapsed = $state(0);
  let errors = $state<{ name: string; message: string }[]>([]);
  let clients = $state<DownloadClientOut[]>([]);
  let sendingId = $state<string | null>(null);

  onMount(async () => {
    try {
      clients = await api.clients.list();
    } catch {
      clients = [];
    }
    const q = $page.url.searchParams.get("q");
    if (q) {
      query = q;
      await runSearch();
    }
  });

  async function runSearch(event?: Event) {
    event?.preventDefault();
    if (!query.trim()) return;
    loading = true;
    errors = [];
    try {
      const res = await api.search({
        query,
        categories,
        protocol: protocol || null,
        min_seeders: minSeeders,
        max_size_mb: maxSizeMb,
        use_ai_ranking: useAI
      });
      hits = res.hits;
      elapsed = res.elapsed_ms;
      errors = res.errors;
    } catch (e) {
      hits = [];
      errors = [{ name: "search", message: (e as { detail?: string }).detail ?? "failed" }];
    } finally {
      loading = false;
    }
  }

  function toggleCategory(cat: Category) {
    if (categories.includes(cat)) {
      categories = categories.filter((c) => c !== cat);
    } else {
      categories = [...categories, cat];
    }
  }

  function compatibleClients(hit: SearchHit): DownloadClientOut[] {
    return clients.filter((c) => c.protocol === hit.protocol && c.enabled);
  }

  async function sendHit(hit: SearchHit, clientId: number) {
    if (!hit.download_url) return;
    const key = `${clientId}:${hit.title}`;
    sendingId = key;
    try {
      const result = await api.clients.send(clientId, {
        title: hit.title,
        download_url: hit.download_url
      });
      if (!result.ok) alert(`Failed: ${result.message ?? "unknown error"}`);
    } catch (e) {
      alert((e as { detail?: string }).detail ?? "Send failed");
    } finally {
      sendingId = null;
    }
  }

  function formatSize(bytes: number | null): string {
    if (!bytes) return "?";
    const units = ["B", "KB", "MB", "GB", "TB"];
    let v = bytes;
    let i = 0;
    while (v >= 1024 && i < units.length - 1) {
      v /= 1024;
      i++;
    }
    return `${v.toFixed(1)} ${units[i]}`;
  }

  const allCategories: Category[] = ["movies", "tv", "music", "books", "anime", "other"];
</script>

<div class="space-y-6">
  <form
    onsubmit={runSearch}
    class="rounded-xl border border-border bg-card p-4 shadow-sm"
  >
    <div class="flex items-center gap-2">
      <div class="relative flex-1">
        <Search class="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <input
          type="text"
          bind:value={query}
          placeholder="Search all indexers… (e.g. the bear s03 1080p)"
          class="w-full rounded-md border border-input bg-background py-2.5 pl-9 pr-3 text-sm outline-none ring-ring focus:ring-2"
        />
      </div>
      <button
        type="submit"
        disabled={loading}
        class="inline-flex items-center gap-2 rounded-md bg-primary px-5 py-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-60"
      >
        {#if loading}
          <Loader2 class="h-4 w-4 animate-spin" />
        {:else}
          <Search class="h-4 w-4" />
        {/if}
        Search
      </button>
    </div>

    <div class="mt-4 flex flex-wrap items-center gap-3 text-sm">
      <div class="flex items-center gap-1 text-xs text-muted-foreground">
        <Filter class="h-3.5 w-3.5" /> Categories:
      </div>
      {#each allCategories as cat}
        <button
          type="button"
          onclick={() => toggleCategory(cat)}
          class="rounded-full border px-3 py-1 text-xs capitalize transition-colors {categories.includes(
            cat
          )
            ? 'border-primary bg-primary/10 text-primary'
            : 'border-border bg-background text-muted-foreground hover:bg-muted'}"
        >
          {cat}
        </button>
      {/each}

      <div class="ml-2 h-5 w-px bg-border"></div>

      <label class="flex items-center gap-1 text-xs">
        Protocol:
        <select
          bind:value={protocol}
          class="rounded-md border border-input bg-background px-2 py-1 text-xs outline-none"
        >
          <option value="">any</option>
          <option value="torrent">torrent</option>
          <option value="usenet">usenet</option>
        </select>
      </label>

      <label class="flex items-center gap-1 text-xs">
        Min seeders:
        <input
          type="number"
          bind:value={minSeeders}
          min="0"
          class="w-16 rounded-md border border-input bg-background px-2 py-1 text-xs outline-none"
        />
      </label>

      <label class="flex items-center gap-1 text-xs">
        Max size MB:
        <input
          type="number"
          bind:value={maxSizeMb}
          min="0"
          class="w-20 rounded-md border border-input bg-background px-2 py-1 text-xs outline-none"
        />
      </label>

      <label class="flex items-center gap-1 text-xs">
        <input type="checkbox" bind:checked={useAI} class="h-3.5 w-3.5" />
        <Sparkles class="h-3.5 w-3.5 text-primary" />
        AI ranking
      </label>
    </div>
  </form>

  {#if errors.length > 0}
    <div class="rounded-md border border-yellow-500/30 bg-yellow-500/10 p-3 text-sm">
      <div class="font-medium">Some indexers failed:</div>
      <ul class="mt-1 space-y-0.5 text-xs text-muted-foreground">
        {#each errors as err}
          <li>{err.name}: {err.message}</li>
        {/each}
      </ul>
    </div>
  {/if}

  {#if hits.length > 0}
    <div class="text-xs text-muted-foreground">
      {hits.length} results in {elapsed}ms
    </div>
    <div class="overflow-hidden rounded-xl border border-border bg-card">
      <table class="w-full text-sm">
        <thead class="bg-muted/50 text-left text-xs uppercase tracking-wide text-muted-foreground">
          <tr>
            <th class="px-4 py-3 font-medium">Title</th>
            <th class="px-4 py-3 font-medium">Size</th>
            <th class="px-4 py-3 font-medium">S/L</th>
            <th class="px-4 py-3 font-medium">Source</th>
            <th class="px-4 py-3 font-medium">Score</th>
            <th class="px-4 py-3 font-medium"></th>
          </tr>
        </thead>
        <tbody>
          {#each hits as hit}
            <tr class="border-t border-border">
              <td class="max-w-xl px-4 py-3">
                <div class="truncate font-medium">{hit.title}</div>
                <div class="mt-0.5 text-xs text-muted-foreground">
                  {hit.protocol} · {hit.category ?? "—"}
                </div>
              </td>
              <td class="px-4 py-3 text-xs">{formatSize(hit.size)}</td>
              <td class="px-4 py-3 text-xs">
                {hit.seeders ?? "—"}/{hit.leechers ?? "—"}
              </td>
              <td class="px-4 py-3 text-xs text-muted-foreground">{hit.source ?? "—"}</td>
              <td class="px-4 py-3 text-xs">{hit.score.toFixed(1)}</td>
              <td class="px-4 py-3 text-right">
                {#each compatibleClients(hit) as client}
                  {@const busyKey = `${client.id}:${hit.title}`}
                  <button
                    class="ml-1 inline-flex items-center gap-1 rounded-md border border-border bg-background px-2 py-1 text-xs hover:bg-muted"
                    onclick={() => sendHit(hit, client.id)}
                    disabled={sendingId === busyKey}
                    title="Send to {client.name}"
                  >
                    {#if sendingId === busyKey}
                      <Loader2 class="h-3 w-3 animate-spin" />
                    {:else}
                      <Send class="h-3 w-3" />
                    {/if}
                    {client.name}
                  </button>
                {/each}
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {:else if !loading && query}
    <div class="rounded-xl border border-dashed border-border bg-card p-10 text-center text-sm text-muted-foreground">
      No results.
    </div>
  {/if}
</div>
