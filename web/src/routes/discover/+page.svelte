<script lang="ts">
  import { onMount } from "svelte";
  import { api, type DiscoverItem } from "$lib/api";
  import {
    Search,
    Loader2,
    Star,
    Check,
    Plus,
    X,
    TrendingUp,
    Film,
    Tv,
    CalendarClock,
    Sparkles
  } from "lucide-svelte";

  type Tab = "trending" | "movies" | "tv" | "upcoming" | "onair";

  let configured = $state(true);
  let activeTab = $state<Tab>("trending");
  let items = $state<DiscoverItem[]>([]);
  let loading = $state(false);
  let error = $state<string | null>(null);

  let searchQuery = $state("");
  let searching = $state(false);

  let detailItem = $state<DiscoverItem | null>(null);
  let detailLoading = $state(false);

  let addedIds = $state<Set<number>>(new Set());
  let addingId = $state<number | null>(null);

  const tabs: { key: Tab; label: string; icon: typeof TrendingUp }[] = [
    { key: "trending", label: "Trending", icon: TrendingUp },
    { key: "movies", label: "Popular movies", icon: Film },
    { key: "tv", label: "Popular TV", icon: Tv },
    { key: "upcoming", label: "Upcoming movies", icon: CalendarClock },
    { key: "onair", label: "On the air", icon: Sparkles }
  ];

  async function loadTab(tab: Tab) {
    activeTab = tab;
    loading = true;
    error = null;
    try {
      if (tab === "trending") items = await api.discover.trending("all", "week");
      else if (tab === "movies") items = await api.discover.popular("movie");
      else if (tab === "tv") items = await api.discover.popular("tv");
      else if (tab === "upcoming") items = await api.discover.upcomingMovies();
      else if (tab === "onair") items = await api.discover.onAirTv();
    } catch (e) {
      const err = e as { status?: number; detail?: string };
      if (err.detail === "tmdb_not_configured") configured = false;
      error = err.detail ?? "Failed to load";
      items = [];
    } finally {
      loading = false;
    }
  }

  async function runSearch(event?: Event) {
    event?.preventDefault();
    const q = searchQuery.trim();
    if (!q) {
      await loadTab(activeTab);
      return;
    }
    searching = true;
    error = null;
    try {
      items = await api.discover.search(q, "multi");
    } catch (e) {
      error = (e as { detail?: string }).detail ?? "Search failed";
      items = [];
    } finally {
      searching = false;
    }
  }

  async function checkConfig() {
    try {
      const s = await api.discover.status();
      configured = s.configured;
    } catch {
      configured = false;
    }
  }

  async function loadWatchlistIds() {
    try {
      const watchlist = await api.watchlist.list();
      addedIds = new Set(
        watchlist.filter((w) => w.tmdb_id !== null).map((w) => w.tmdb_id as number)
      );
    } catch {}
  }

  onMount(async () => {
    await checkConfig();
    if (configured) {
      await loadTab("trending");
      await loadWatchlistIds();
    }
  });

  async function openDetail(item: DiscoverItem) {
    detailItem = item;
    // Refresh with full details (includes genres, longer overview, etc)
    detailLoading = true;
    try {
      const full = item.kind === "movie"
        ? await api.discover.movie(item.tmdb_id)
        : await api.discover.tv(item.tmdb_id);
      detailItem = full;
    } catch {}
    detailLoading = false;
  }

  async function addToWatchlist(item: DiscoverItem) {
    addingId = item.tmdb_id;
    try {
      await api.watchlist.create({
        kind: item.kind === "movie" ? "movie" : "series",
        title: item.title,
        year: item.year,
        tmdb_id: item.tmdb_id,
        tmdb_type: item.kind,
        poster_path: item.poster_url,
        backdrop_path: item.backdrop_url,
        overview: item.overview,
        release_date: item.release_date,
        rating: item.rating
      });
      addedIds = new Set([...addedIds, item.tmdb_id]);
    } catch (e) {
      alert((e as { detail?: string }).detail ?? "Failed to add");
    } finally {
      addingId = null;
    }
  }

  function closeDetail() {
    detailItem = null;
  }
</script>

<div class="space-y-6">
  <div class="flex items-end justify-between">
    <div>
      <h1 class="flex items-center gap-2 text-2xl font-bold">
        <TrendingUp class="h-6 w-6 text-primary" /> Discover
      </h1>
      <p class="mt-1 text-sm text-muted-foreground">
        Browse trending, popular, and upcoming releases from TMDB — add to your watchlist.
      </p>
    </div>
  </div>

  {#if !configured}
    <div class="surface p-8 text-center">
      <div class="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-amber-500/20">
        <Sparkles class="h-5 w-5 text-amber-400" />
      </div>
      <h3 class="text-base font-semibold">TMDB not configured</h3>
      <p class="mx-auto mt-2 max-w-md text-sm text-muted-foreground">
        Discover needs a TMDB API read token. Get one for free at
        <a href="https://www.themoviedb.org/settings/api" target="_blank" class="text-primary hover:underline">
          themoviedb.org/settings/api
        </a>
        and paste it in <a href="/settings" class="text-primary hover:underline">Settings</a>.
      </p>
    </div>
  {:else}
    <!-- Search bar -->
    <form onsubmit={runSearch} class="surface p-3">
      <div class="flex gap-2">
        <div class="relative flex-1">
          <Search class="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <input
            type="text"
            bind:value={searchQuery}
            placeholder="Search TMDB for any movie or TV show…"
            class="input-base pl-9"
          />
        </div>
        <button type="submit" class="btn-primary" disabled={searching}>
          {#if searching}
            <Loader2 class="h-4 w-4 animate-spin" />
          {:else}
            <Search class="h-4 w-4" />
          {/if}
          Search
        </button>
      </div>
    </form>

    <!-- Tabs -->
    <div class="flex flex-wrap gap-2">
      {#each tabs as tab}
        {@const Icon = tab.icon}
        {@const active = activeTab === tab.key}
        <button
          onclick={() => loadTab(tab.key)}
          class="inline-flex items-center gap-1.5 rounded-full border px-4 py-1.5 text-xs font-medium transition-colors {active
            ? 'border-primary bg-primary/15 text-primary'
            : 'border-border bg-card/50 text-muted-foreground hover:bg-muted'}"
        >
          <Icon class="h-3.5 w-3.5" />
          {tab.label}
        </button>
      {/each}
    </div>

    {#if error && !loading}
      <div class="rounded-xl border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
        {error}
      </div>
    {/if}

    {#if loading}
      <div class="flex items-center gap-2 py-8 text-sm text-muted-foreground">
        <Loader2 class="h-4 w-4 animate-spin" /> Loading from TMDB…
      </div>
    {:else if items.length === 0}
      <div class="py-8 text-center text-sm text-muted-foreground">No results.</div>
    {:else}
      <!-- Poster grid -->
      <div class="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6">
        {#each items as item (item.tmdb_id)}
          {@const added = addedIds.has(item.tmdb_id)}
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
                {#if item.rating && item.rating > 0}
                  <div class="absolute right-2 top-2 flex items-center gap-0.5 rounded-full bg-black/70 px-2 py-0.5 text-[10px] font-semibold text-amber-300 backdrop-blur-sm">
                    <Star class="h-2.5 w-2.5 fill-amber-300" />
                    {item.rating.toFixed(1)}
                  </div>
                {/if}
                <div class="absolute left-2 top-2 rounded-full bg-black/70 px-2 py-0.5 text-[10px] font-medium uppercase text-white backdrop-blur-sm">
                  {item.kind}
                </div>
              </div>
              <div class="p-3">
                <div class="truncate text-sm font-semibold">{item.title}</div>
                <div class="mt-0.5 text-xs text-muted-foreground">
                  {item.year ?? "—"}
                </div>
              </div>
            </button>
            <div class="border-t border-border/50 p-2">
              {#if added}
                <button class="btn-ghost w-full cursor-default text-success" disabled>
                  <Check class="h-3 w-3" /> On watchlist
                </button>
              {:else}
                <button
                  class="btn-ghost w-full"
                  onclick={() => addToWatchlist(item)}
                  disabled={addingId === item.tmdb_id}
                >
                  {#if addingId === item.tmdb_id}
                    <Loader2 class="h-3 w-3 animate-spin" />
                  {:else}
                    <Plus class="h-3 w-3" />
                  {/if}
                  Add to watchlist
                </button>
              {/if}
            </div>
          </div>
        {/each}
      </div>
    {/if}
  {/if}
</div>

<!-- Detail modal -->
{#if detailItem}
  {@const item = detailItem}
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
          <div class="text-xs uppercase tracking-wider text-primary">{item.kind}</div>
          <h2 class="mt-1 text-2xl font-bold">{item.title}</h2>
          {#if item.original_title && item.original_title !== item.title}
            <div class="mt-0.5 text-sm italic text-muted-foreground">{item.original_title}</div>
          {/if}
          <div class="mt-3 flex flex-wrap items-center gap-3 text-xs">
            {#if item.year}
              <span class="chip">{item.year}</span>
            {/if}
            {#if item.rating && item.rating > 0}
              <span class="inline-flex items-center gap-1 text-amber-400">
                <Star class="h-3 w-3 fill-amber-400" />
                {item.rating.toFixed(1)} / 10
              </span>
            {/if}
            {#if item.release_date}
              <span class="text-muted-foreground">{item.release_date}</span>
            {/if}
          </div>
          {#if item.genres.length > 0}
            <div class="mt-3 flex flex-wrap gap-1.5">
              {#each item.genres as g}
                <span class="chip">{g}</span>
              {/each}
            </div>
          {/if}
          {#if item.overview}
            <p class="mt-4 text-sm leading-relaxed text-foreground/90">{item.overview}</p>
          {/if}
          <div class="mt-6 flex gap-2">
            {#if addedIds.has(item.tmdb_id)}
              <button class="btn-secondary cursor-default" disabled>
                <Check class="h-3.5 w-3.5 text-success" /> On your watchlist
              </button>
            {:else}
              <button
                class="btn-primary"
                onclick={() => addToWatchlist(item)}
                disabled={addingId === item.tmdb_id}
              >
                {#if addingId === item.tmdb_id}
                  <Loader2 class="h-3.5 w-3.5 animate-spin" />
                {:else}
                  <Plus class="h-3.5 w-3.5" />
                {/if}
                Add to watchlist
              </button>
            {/if}
          </div>
        </div>
      </div>
    </div>
  </div>
{/if}
