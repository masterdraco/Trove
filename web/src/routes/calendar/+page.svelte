<script lang="ts">
  import { onMount } from "svelte";
  import { api, type CalendarEvent } from "$lib/api";
  import { ChevronLeft, ChevronRight, Film, Tv, Calendar } from "lucide-svelte";

  let year = $state(new Date().getFullYear());
  let month = $state(new Date().getMonth() + 1);
  let events = $state<CalendarEvent[]>([]);
  let loading = $state(true);

  const MONTH_NAMES = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December"
  ];

  const DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

  function monthStr(): string {
    return `${year}-${String(month).padStart(2, "0")}`;
  }

  async function load() {
    loading = true;
    try {
      const resp = await api.calendar(monthStr());
      events = resp.events;
    } catch {
      events = [];
    } finally {
      loading = false;
    }
  }

  function prev() {
    if (month === 1) {
      month = 12;
      year--;
    } else {
      month--;
    }
    load();
  }

  function next() {
    if (month === 12) {
      month = 1;
      year++;
    } else {
      month++;
    }
    load();
  }

  function today() {
    year = new Date().getFullYear();
    month = new Date().getMonth() + 1;
    load();
  }

  function daysInMonth(y: number, m: number): number {
    return new Date(y, m, 0).getDate();
  }

  function firstWeekday(y: number, m: number): number {
    const d = new Date(y, m - 1, 1).getDay();
    return d === 0 ? 6 : d - 1; // Monday=0 ... Sunday=6
  }

  function eventsForDay(day: number): CalendarEvent[] {
    const target = `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
    return events.filter((e) => e.date === target);
  }

  function grabColor(state: string): string {
    switch (state) {
      case "grabbed":
        return "bg-green-500/70";
      case "missed":
        return "bg-red-500/50";
      default:
        return "bg-muted-foreground/30";
    }
  }

  onMount(load);
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
    <div class="flex items-center gap-2">
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

  {#if loading}
    <div class="rounded-xl border border-border bg-card p-12 text-center text-muted-foreground">
      Loading…
    </div>
  {:else}
    <!-- Day headers -->
    <div class="grid grid-cols-7 gap-px rounded-t-xl border border-b-0 border-border bg-card">
      {#each DAY_NAMES as day}
        <div
          class="px-2 py-2 text-center text-xs font-semibold uppercase tracking-wide text-muted-foreground"
        >
          {day}
        </div>
      {/each}
    </div>
    <!-- Grid -->
    <div
      class="-mt-6 grid grid-cols-7 gap-px overflow-hidden rounded-b-xl border border-t-0 border-border bg-border"
    >
      <!-- Empty cells before the first day -->
      {#each { length: firstWeekday(year, month) } as _}
        <div class="min-h-[80px] bg-card/50"></div>
      {/each}
      <!-- Day cells -->
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
              <div
                class="group flex items-center gap-1 truncate rounded px-1 py-0.5 text-[10px] leading-tight {grabColor(
                  ev.grab_state
                )}"
                title="{ev.title}{ev.season != null
                  ? ` S${String(ev.season).padStart(2, '0')}E${String(ev.episode).padStart(2, '0')}`
                  : ''}{ev.episode_title ? ` — ${ev.episode_title}` : ''} [{ev.grab_state}]"
              >
                {#if ev.kind === "tv"}
                  <Tv class="h-2.5 w-2.5 shrink-0" />
                {:else}
                  <Film class="h-2.5 w-2.5 shrink-0" />
                {/if}
                <span class="truncate">
                  {ev.title}
                  {#if ev.season != null}
                    <span class="font-mono"
                      >S{String(ev.season).padStart(2, "0")}E{String(ev.episode).padStart(
                        2,
                        "0"
                      )}</span
                    >
                  {/if}
                </span>
              </div>
            {/each}
            {#if dayEvents.length > 4}
              <div class="px-1 text-[10px] text-muted-foreground">
                +{dayEvents.length - 4} more
              </div>
            {/if}
          </div>
        </div>
      {/each}
      <!-- Fill the rest of the last row -->
      {#each { length: (7 - ((firstWeekday(year, month) + daysInMonth(year, month)) % 7)) % 7 } as _}
        <div class="min-h-[80px] bg-card/50"></div>
      {/each}
    </div>

    <!-- Legend -->
    <div class="flex items-center gap-4 text-xs text-muted-foreground">
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
      <div class="flex items-center gap-1.5">
        <Tv class="h-3 w-3" /> TV
      </div>
      <div class="flex items-center gap-1.5">
        <Film class="h-3 w-3" /> Movie
      </div>
    </div>
  {/if}
</div>
