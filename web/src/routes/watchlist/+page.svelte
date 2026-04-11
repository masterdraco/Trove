<script lang="ts">
  import { onMount } from "svelte";
  import { api, type WatchlistItem } from "$lib/api";
  import {
    Plus,
    Trash2,
    Eye,
    Star,
    Zap,
    PauseCircle,
    Loader2,
    X,
    TrendingUp
  } from "lucide-svelte";

  let items = $state<WatchlistItem[]>([]);
  let loading = $state(true);
  let showForm = $state(false);

  let busyId = $state<number | null>(null);
  let detailItem = $state<WatchlistItem | null>(null);

  let form = $state({
    kind: "series" as "series" | "movie",
    title: "",
    year: null as number | null,
    target_quality: "",
    notes: ""
  });

  async function load() {
    loading = true;
    items = await api.watchlist.list();
    loading = false;
  }

  onMount(load);

  async function save(e: Event) {
    e.preventDefault();
    await api.watchlist.create({
      kind: form.kind,
      title: form.title,
      year: form.year,
      target_quality: form.target_quality || null,
      notes: form.notes || null
    });
    showForm = false;
    form = { kind: "series", title: "", year: null, target_quality: "", notes: "" };
    await load();
  }

  async function remove(item: WatchlistItem) {
    if (!confirm(`Remove "${item.title}" from watchlist?`)) return;
    busyId = item.id;
    try {
      await api.watchlist.remove(item.id);
      if (detailItem?.id === item.id) detailItem = null;
      await load();
    } finally {
      busyId = null;
    }
  }

  async function promote(item: WatchlistItem) {
    busyId = item.id;
    try {
      const r = await api.watchlist.promote(item.id);
      if (!r.ok) alert("Promote failed");
      await load();
      if (detailItem?.id === item.id) {
        detailItem = items.find((i) => i.id === item.id) ?? null;
      }
    } catch (e) {
      alert((e as { detail?: string }).detail ?? "Failed to promote");
    } finally {
      busyId = null;
    }
  }

  async function unpromote(item: WatchlistItem) {
    if (!confirm("Stop the backing download task? The watchlist entry stays.")) return;
    busyId = item.id;
    try {
      await api.watchlist.unpromote(item.id);
      await load();
      if (detailItem?.id === item.id) {
        detailItem = items.find((i) => i.id === item.id) ?? null;
      }
    } finally {
      busyId = null;
    }
  }

  function statusLabel(s: string): { text: string; cls: string } {
    if (s === "promoted") return { text: "Auto-downloading", cls: "chip-primary" };
    if (s === "downloaded") return { text: "Downloaded", cls: "chip-success" };
    if (s === "available") return { text: "Available", cls: "chip-primary" };
    return { text: "Tracking", cls: "chip" };
  }

  function openDetail(item: WatchlistItem) {
    detailItem = item;
  }

  function closeDetail() {
    detailItem = null;
  }
</script>

<div class="space-y-6">
  <div class="flex items-center justify-between">
    <div>
      <h1 class="flex items-center gap-2 text-2xl font-bold">
        <Eye class="h-6 w-6 text-primary" /> Watchlist
      </h1>
      <p class="mt-1 text-sm text-muted-foreground">
        Titles you're tracking — promote to auto-download when you're ready.
      </p>
    </div>
    <div class="flex gap-2">
      <a href="/discover" class="btn-secondary">
        <TrendingUp class="h-4 w-4" /> Discover
      </a>
      <button class="btn-primary" onclick={() => (showForm = true)}>
        <Plus class="h-4 w-4" /> Add manually
      </button>
    </div>
  </div>

  {#if loading}
    <div class="text-sm text-muted-foreground">Loading…</div>
  {:else if items.length === 0}
    <div class="surface p-12 text-center">
      <Eye class="mx-auto mb-3 h-8 w-8 text-muted-foreground" />
      <h3 class="text-base font-semibold">Your watchlist is empty</h3>
      <p class="mx-auto mt-2 max-w-md text-sm text-muted-foreground">
        Browse trending movies and TV on the <a href="/discover" class="text-primary hover:underline">Discover</a>
        page, or add a title manually.
      </p>
    </div>
  {:else}
    <div class="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6">
      {#each items as item (item.id)}
        {@const status = statusLabel(item.discovery_status)}
        <div class="surface group overflow-hidden p-0 transition-transform hover:-translate-y-1">
          <button class="block w-full text-left" onclick={() => openDetail(item)}>
            <div class="relative aspect-[2/3] overflow-hidden bg-muted/30">
              {#if item.poster_url}
                <img
                  src={item.poster_url}
                  alt={item.title}
                  loading="lazy"
                  class="h-full w-full object-cover transition-transform group-hover:scale-105"
                />
              {:else}
                <div class="flex h-full items-center justify-center text-xs text-muted-foreground">
                  No poster
                </div>
              {/if}
              {#if item.rating}
                <div class="absolute right-2 top-2 flex items-center gap-0.5 rounded-full bg-black/70 px-2 py-0.5 text-[10px] font-semibold text-amber-300 backdrop-blur-sm">
                  <Star class="h-2.5 w-2.5 fill-amber-300" />
                  {item.rating.toFixed(1)}
                </div>
              {/if}
              <div class="absolute left-2 top-2 rounded-full bg-black/70 px-2 py-0.5 text-[10px] font-medium uppercase text-white backdrop-blur-sm">
                {item.kind}
              </div>
              <div class="absolute bottom-2 left-2">
                <span class={status.cls}>{status.text}</span>
              </div>
            </div>
            <div class="p-3">
              <div class="truncate text-sm font-semibold">{item.title}</div>
              <div class="mt-0.5 text-xs text-muted-foreground">
                {item.year ?? "—"}
              </div>
            </div>
          </button>
          <div class="flex border-t border-border/50">
            {#if item.discovery_status === "promoted"}
              <button
                class="btn-ghost flex-1 text-amber-400"
                onclick={() => unpromote(item)}
                disabled={busyId === item.id}
              >
                <PauseCircle class="h-3 w-3" />
                Stop
              </button>
            {:else}
              <button
                class="btn-ghost flex-1 text-primary"
                onclick={() => promote(item)}
                disabled={busyId === item.id}
              >
                {#if busyId === item.id}
                  <Loader2 class="h-3 w-3 animate-spin" />
                {:else}
                  <Zap class="h-3 w-3" />
                {/if}
                Auto-download
              </button>
            {/if}
            <button
              class="btn-ghost border-l border-border/50 px-3 text-muted-foreground hover:text-destructive"
              onclick={() => remove(item)}
              aria-label="Remove"
            >
              <Trash2 class="h-3 w-3" />
            </button>
          </div>
        </div>
      {/each}
    </div>
  {/if}
</div>

{#if showForm}
  <div class="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-background/80 p-6 backdrop-blur-sm">
    <form onsubmit={save} class="surface mt-16 w-full max-w-md p-6">
      <div class="mb-4 flex items-center justify-between">
        <h3 class="text-lg font-semibold">Add to watchlist</h3>
        <button
          type="button"
          class="rounded-md p-1 text-muted-foreground hover:bg-muted"
          onclick={() => (showForm = false)}
        >
          ✕
        </button>
      </div>
      <div class="space-y-3">
        <label class="block">
          <span class="mb-1 block text-sm font-medium">Kind</span>
          <select bind:value={form.kind} class="input-base">
            <option value="series">Series</option>
            <option value="movie">Movie</option>
          </select>
        </label>
        <label class="block">
          <span class="mb-1 block text-sm font-medium">Title</span>
          <input type="text" required bind:value={form.title} class="input-base" />
        </label>
        <div class="grid grid-cols-2 gap-3">
          <label class="block">
            <span class="mb-1 block text-sm font-medium">Year</span>
            <input type="number" bind:value={form.year} class="input-base" />
          </label>
          <label class="block">
            <span class="mb-1 block text-sm font-medium">Quality</span>
            <input type="text" bind:value={form.target_quality} placeholder="1080p" class="input-base" />
          </label>
        </div>
        <label class="block">
          <span class="mb-1 block text-sm font-medium">Notes</span>
          <textarea rows="3" bind:value={form.notes} class="input-base"></textarea>
        </label>
      </div>
      <div class="mt-4 flex justify-end gap-2">
        <button type="button" class="btn-secondary" onclick={() => (showForm = false)}>
          Cancel
        </button>
        <button type="submit" class="btn-primary">Save</button>
      </div>
      <p class="mt-3 text-xs text-muted-foreground">
        Tip: browse <a href="/discover" class="text-primary hover:underline">Discover</a>
        for posters + metadata from TMDB.
      </p>
    </form>
  </div>
{/if}

{#if detailItem}
  {@const item = detailItem}
  {@const status = statusLabel(item.discovery_status)}
  <!-- svelte-ignore a11y_click_events_have_key_events -->
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div
    class="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-background/90 p-6 backdrop-blur-md"
    onclick={closeDetail}
  >
    <button
      class="fixed right-6 top-6 flex h-10 w-10 items-center justify-center rounded-full bg-card/80 text-muted-foreground backdrop-blur hover:bg-card hover:text-foreground"
      onclick={closeDetail}
      aria-label="Close"
    >
      <X class="h-5 w-5" />
    </button>
    <!-- svelte-ignore a11y_click_events_have_key_events -->
    <!-- svelte-ignore a11y_no_static_element_interactions -->
    <div
      class="surface my-10 max-w-4xl overflow-hidden p-0"
      onclick={(e) => e.stopPropagation()}
    >
      {#if item.backdrop_url}
        <div class="relative aspect-[16/9] bg-muted/30">
          <img src={item.backdrop_url} alt="" class="h-full w-full object-cover" />
          <div class="absolute inset-0 bg-gradient-to-t from-card via-card/60 to-transparent"></div>
        </div>
      {/if}
      <div class="flex gap-6 p-6 {item.backdrop_url ? '-mt-24 relative' : ''}">
        {#if item.poster_url}
          <img
            src={item.poster_url}
            alt={item.title}
            class="h-56 w-40 shrink-0 rounded-xl object-cover shadow-2xl"
          />
        {/if}
        <div class="min-w-0 flex-1">
          <div class="flex items-center gap-2 text-xs uppercase tracking-wider text-primary">
            {item.kind}
            <span class={status.cls}>{status.text}</span>
          </div>
          <h2 class="mt-1 text-2xl font-bold">{item.title}</h2>
          <div class="mt-2 flex flex-wrap items-center gap-3 text-xs">
            {#if item.year}<span class="chip">{item.year}</span>{/if}
            {#if item.rating}
              <span class="inline-flex items-center gap-1 text-amber-400">
                <Star class="h-3 w-3 fill-amber-400" />
                {item.rating.toFixed(1)}
              </span>
            {/if}
            {#if item.release_date}
              <span class="text-muted-foreground">{item.release_date}</span>
            {/if}
          </div>
          {#if item.overview}
            <p class="mt-4 text-sm leading-relaxed text-foreground/90">{item.overview}</p>
          {/if}
          <div class="mt-6 flex gap-2">
            {#if item.discovery_status === "promoted"}
              <button class="btn-secondary" onclick={() => unpromote(item)} disabled={busyId === item.id}>
                <PauseCircle class="h-3.5 w-3.5" />
                Stop auto-download
              </button>
            {:else}
              <button class="btn-primary" onclick={() => promote(item)} disabled={busyId === item.id}>
                {#if busyId === item.id}
                  <Loader2 class="h-3.5 w-3.5 animate-spin" />
                {:else}
                  <Zap class="h-3.5 w-3.5" />
                {/if}
                Start auto-download
              </button>
            {/if}
            <button class="btn-secondary text-destructive" onclick={() => remove(item)}>
              <Trash2 class="h-3.5 w-3.5" />
              Remove
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
{/if}
