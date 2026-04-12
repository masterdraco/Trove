<script lang="ts">
  import { onMount } from "svelte";
  import { api, type CalendarEvent } from "$lib/api";
  import {
    ChevronLeft,
    ChevronRight,
    Film,
    Tv,
    Calendar,
    Star,
    Plus,
    Check,
    Loader2,
    X,
    Eye
  } from "lucide-svelte";

  let year = $state(new Date().getFullYear());
  let month = $state(new Date().getMonth() + 1);
  let events = $state<CalendarEvent[]>([]);
  let loading = $state(true);
  let showTmdb = $state(true);

  let detailEvent = $state<CalendarEvent | null>(null);
  let addingId = $state<number | null>(null);
  let addedIds = $state<Set<number>>(new Set());

  const MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"
  ];

  const DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

  function monthStr(): string {
    return `${year}-${String(month).padStart(2, "0")}`;
  }

  async function load() {
    loading = true;
    try {
      const resp = await api.calendar(monthStr(), showTmdb);
      events = resp.events;
    } catch {
      events = [];
    } finally {
      loading = false;
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

  function prev() {
    if (month === 1) { month = 12; year--; } else { month--; }
    load();
  }

  function next() {
    if (month === 12) { month = 1; year++; } else { month++; }
    load();
  }

  function today() {
    year = new Date().getFullYear();
    month = new Date().getMonth() + 1;
    load();
  }

  function toggleTmdb() {
    showTmdb = !showTmdb;
    load();
  }

  function daysInMonth(y: number, m: number): number {
    return new Date(y, m, 0).getDate();
  }

  function firstWeekday(y: number, m: number): number {
    const d = new Date(y, m - 1, 1).getDay();
    return d === 0 ? 6 : d - 1;
  }

  function eventsForDay(day: number): CalendarEvent[] {
    const target = `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
    return events.filter((e) => e.date === target);
  }

  function grabColor(ev: CalendarEvent): string {
    if (ev.source === "tmdb") return "bg-indigo-500/40 border border-indigo-500/30";
    switch (ev.grab_state) {
      case "grabbed": return "bg-green-500/70";
      case "missed": return "bg-red-500/50";
      default: return "bg-muted-foreground/30";
    }
  }

  function openDetail(ev: CalendarEvent) {
    detailEvent = ev;
  }

  function closeDetail() {
    detailEvent = null;
  }

  async function addToWatchlist(ev: CalendarEvent) {
    if (!ev.tmdb_id) return;
    addingId = ev.tmdb_id;
    try {
      const item = await api.watchlist.create({
        kind: ev.kind === "movie" ? "movie" : "series",
        title: ev.title,
        tmdb_id: ev.tmdb_id,
        tmdb_type: ev.kind === "movie" ? "movie" : "tv",
        poster_path: ev.poster_url,
        overview: ev.overview,
        rating: ev.rating
      });
      addedIds = new Set([...addedIds, ev.tmdb_id]);
      // Auto-promote to create a download task
      if (item.id) {
        try { await api.watchlist.promote(item.id); } catch {}
      }
      await load();
    } catch (e) {
      alert((e as { detail?: string }).detail ?? "Failed to add");
    } finally {
      addingId = null;
    }
  }

  onMount(async () => {
    await load();
    await loadWatchlistIds();
  });
</script>

<svelte:head>
  <title>Calendar — Trove</title>
</svelte:head>

<div class="space-y-6">
  <div class="flex items-center justify-between">
    <div class="flex items-center gap-2">
      <Calendar class="h-5 w-5 text-primary" />
      <h1 class="text-xl font-bold">Calendar</h1>
    </div>
    <div class="flex items-center gap-3">
      <button
        class="inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-colors {showTmdb
          ? 'bg-indigo-500/20 border border-indigo-500/40 text-indigo-300'
          : 'border border-border bg-card text-muted-foreground hover:bg-muted'}"
        onclick={toggleTmdb}
      >
        <Eye class="h-3.5 w-3.5" />
        TMDB Releases
      </button>
      <div class="flex items-center gap-1">
        <button class="btn-secondary" onclick={prev}>
          <ChevronLeft class="h-4 w-4" />
        </button>
        <button class="btn-secondary px-3 text-sm font-semibold" onclick={today}>
          {MONTH_NAMES[month - 1]}
          {year}
        </button>
        <button class="btn-secondary" onclick={next}>
          <ChevronRight class="h-4 w-4" />
        </button>
      </div>
    </div>
  </div>

  {#if loading}
    <div class="rounded-xl border border-border bg-card p-12 text-center text-muted-foreground">
      Loading...
    </div>
  {:else}
    <!-- Day headers -->
    <div class="grid grid-cols-7 gap-px rounded-t-xl border border-b-0 border-border bg-card">
      {#each DAY_NAMES as day}
        <div class="px-2 py-2 text-center text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          {day}
        </div>
      {/each}
    </div>
    <!-- Grid -->
    <div class="-mt-6 grid grid-cols-7 gap-px overflow-hidden rounded-b-xl border border-t-0 border-border bg-border">
      {#each { length: firstWeekday(year, month) } as _}
        <div class="min-h-[80px] bg-card/50"></div>
      {/each}
      {#each { length: daysInMonth(year, month) } as _, i}
        {@const day = i + 1}
        {@const dayEvents = eventsForDay(day)}
        {@const isToday =
          day === new Date().getDate() &&
          month === new Date().getMonth() + 1 &&
          year === new Date().getFullYear()}
        <div
          class="relative min-h-[80px] bg-card p-1.5"
          class:ring-2={isToday}
          class:ring-primary={isToday}
          class:ring-inset={isToday}
        >
          <div
            class="mb-1 text-xs font-semibold"
            class:text-primary={isToday}
            class:text-muted-foreground={!isToday}
          >
            {day}
          </div>
          <div class="space-y-0.5">
            {#each dayEvents.slice(0, 4) as ev}
              <button
                class="group flex w-full items-center gap-1 truncate rounded px-1 py-0.5 text-left text-[10px] leading-tight transition-opacity hover:opacity-80 {grabColor(ev)}"
                onclick={() => openDetail(ev)}
                title="{ev.title}{ev.season != null
                  ? ` S${String(ev.season).padStart(2, '0')}E${String(ev.episode).padStart(2, '0')}`
                  : ''}{ev.episode_title ? ` — ${ev.episode_title}` : ''} [{ev.source === 'tmdb' ? 'TMDB' : ev.grab_state}]"
              >
                {#if ev.kind === "tv"}
                  <Tv class="h-2.5 w-2.5 shrink-0" />
                {:else}
                  <Film class="h-2.5 w-2.5 shrink-0" />
                {/if}
                <span class="truncate">
                  {ev.title}
                  {#if ev.season != null}
                    <span class="font-mono">S{String(ev.season).padStart(2, "0")}E{String(ev.episode).padStart(2, "0")}</span>
                  {/if}
                </span>
              </button>
            {/each}
            {#if dayEvents.length > 4}
              <div class="px-1 text-[10px] text-muted-foreground">
                +{dayEvents.length - 4} more
              </div>
            {/if}
          </div>
        </div>
      {/each}
      {#each { length: (7 - ((firstWeekday(year, month) + daysInMonth(year, month)) % 7)) % 7 } as _}
        <div class="min-h-[80px] bg-card/50"></div>
      {/each}
    </div>

    <!-- Legend -->
    <div class="flex flex-wrap items-center gap-4 text-xs text-muted-foreground">
      <div class="flex items-center gap-1.5">
        <span class="inline-block h-2.5 w-2.5 rounded bg-green-500/70"></span>
        Grabbed
      </div>
      <div class="flex items-center gap-1.5">
        <span class="inline-block h-2.5 w-2.5 rounded bg-muted-foreground/30"></span>
        Pending
      </div>
      <div class="flex items-center gap-1.5">
        <span class="inline-block h-2.5 w-2.5 rounded bg-red-500/50"></span>
        Missed
      </div>
      {#if showTmdb}
        <div class="flex items-center gap-1.5">
          <span class="inline-block h-2.5 w-2.5 rounded bg-indigo-500/40 ring-1 ring-indigo-500/30"></span>
          TMDB Discover
        </div>
      {/if}
      <div class="flex items-center gap-1.5">
        <Tv class="h-3 w-3" /> TV
      </div>
      <div class="flex items-center gap-1.5">
        <Film class="h-3 w-3" /> Movie
      </div>
    </div>
  {/if}
</div>

<!-- Detail modal -->
{#if detailEvent}
  {@const ev = detailEvent}
  {@const isTmdb = ev.source === "tmdb"}
  {@const alreadyAdded = ev.tmdb_id != null && addedIds.has(ev.tmdb_id)}
  <!-- svelte-ignore a11y_click_events_have_key_events -->
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div
    class="fixed inset-0 z-50 flex items-center justify-center bg-background/90 p-6 backdrop-blur-md"
    onclick={closeDetail}
  >
    <button
      class="fixed right-6 top-6 flex h-10 w-10 items-center justify-center rounded-full bg-card/80 text-muted-foreground backdrop-blur hover:bg-card hover:text-foreground"
      onclick={closeDetail}
    >
      <X class="h-5 w-5" />
    </button>
    <!-- svelte-ignore a11y_click_events_have_key_events -->
    <!-- svelte-ignore a11y_no_static_element_interactions -->
    <div class="surface max-w-lg overflow-hidden p-0" onclick={(e) => e.stopPropagation()}>
      <div class="flex gap-4 p-5">
        {#if ev.poster_url}
          <img
            src={ev.poster_url}
            alt={ev.title}
            class="h-44 w-28 shrink-0 rounded-lg object-cover shadow-lg"
          />
        {/if}
        <div class="min-w-0 flex-1">
          <div class="flex items-center gap-2">
            <span class="rounded-full px-2 py-0.5 text-[10px] font-medium uppercase {isTmdb
              ? 'bg-indigo-500/20 text-indigo-300'
              : ev.grab_state === 'grabbed'
                ? 'bg-green-500/20 text-green-400'
                : ev.grab_state === 'missed'
                  ? 'bg-red-500/20 text-red-400'
                  : 'bg-muted text-muted-foreground'}">
              {isTmdb ? "TMDB" : ev.grab_state}
            </span>
            <span class="rounded-full bg-muted px-2 py-0.5 text-[10px] uppercase">{ev.kind}</span>
          </div>
          <h3 class="mt-2 text-lg font-bold">{ev.title}</h3>
          <div class="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            <span>{ev.date}</span>
            {#if ev.season != null}
              <span class="font-mono">S{String(ev.season).padStart(2, "0")}E{String(ev.episode).padStart(2, "0")}</span>
            {/if}
            {#if ev.episode_title}
              <span>"{ev.episode_title}"</span>
            {/if}
            {#if ev.rating && ev.rating > 0}
              <span class="flex items-center gap-0.5 text-amber-400">
                <Star class="h-3 w-3 fill-amber-400" />
                {ev.rating.toFixed(1)}
              </span>
            {/if}
          </div>
          {#if ev.overview}
            <p class="mt-3 text-sm leading-relaxed text-foreground/80">{ev.overview}</p>
          {/if}
          {#if isTmdb && ev.tmdb_id}
            <div class="mt-4">
              {#if alreadyAdded}
                <button class="btn-secondary cursor-default" disabled>
                  <Check class="h-3.5 w-3.5 text-success" /> On watchlist
                </button>
              {:else}
                <button
                  class="btn-primary"
                  onclick={() => addToWatchlist(ev)}
                  disabled={addingId === ev.tmdb_id}
                >
                  {#if addingId === ev.tmdb_id}
                    <Loader2 class="h-3.5 w-3.5 animate-spin" />
                  {:else}
                    <Plus class="h-3.5 w-3.5" />
                  {/if}
                  Add to watchlist & download
                </button>
              {/if}
            </div>
          {/if}
        </div>
      </div>
    </div>
  </div>
{/if}
