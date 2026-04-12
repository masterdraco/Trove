<script lang="ts">
  import { onMount } from "svelte";
  import { api } from "$lib/api";
  import {
    Info,
    Github,
    Heart,
    Coffee,
    Shield,
    Sparkles,
    Database,
    Rss,
    Search,
    Bot
  } from "lucide-svelte";

  let version = $state<string | null>(null);
  let alembicRevision = $state<string | null>(null);
  let loading = $state(true);

  onMount(async () => {
    try {
      const info = await api.system.version();
      version = info.current;
    } catch {
      version = null;
    } finally {
      loading = false;
    }
  });
</script>

<svelte:head>
  <title>About — Trove</title>
</svelte:head>

<div class="mx-auto max-w-3xl space-y-6">
  <!-- Hero -->
  <div class="surface relative overflow-hidden p-8">
    <div
      class="absolute inset-0 bg-gradient-to-br from-primary/15 via-transparent to-amber-500/10"
    ></div>
    <div class="relative flex flex-col items-center gap-4 text-center sm:flex-row sm:text-left">
      <img
        src="/logo-256.png"
        alt="Trove"
        class="h-24 w-24 rounded-2xl glow-primary"
        width="96"
        height="96"
      />
      <div class="flex-1">
        <h1 class="text-3xl font-bold">Trove</h1>
        <p class="mt-1 text-sm text-muted-foreground">
          A modern, self-hosted media automation hub.
        </p>
        <div class="mt-3 flex flex-wrap items-center justify-center gap-2 sm:justify-start">
          <span
            class="rounded-full border border-primary/30 bg-primary/5 px-3 py-1 font-mono text-xs"
          >
            v{version ?? "—"}
          </span>
          <span
            class="rounded-full border border-border/60 bg-background/40 px-3 py-1 text-xs text-muted-foreground"
          >
            GPL-3.0-or-later
          </span>
          <a
            href="https://github.com/masterdraco/Trove"
            target="_blank"
            rel="noopener noreferrer"
            class="inline-flex items-center gap-1 rounded-full border border-border/60 bg-background/40 px-3 py-1 text-xs text-muted-foreground transition hover:text-primary"
          >
            <Github class="h-3 w-3" />
            github.com/masterdraco/Trove
          </a>
        </div>
      </div>
    </div>
  </div>

  <!-- What it does -->
  <div class="surface p-6">
    <div class="mb-4 flex items-center gap-2">
      <Info class="h-5 w-5 text-primary" />
      <h2 class="text-lg font-semibold">What Trove does</h2>
    </div>
    <p class="text-sm text-muted-foreground">
      Trove is an all-in-one automation hub for managing your private media collection. Add
      your indexers and trackers once, then let Trove handle discovery, scheduling,
      filtering, and routing to the right download client.
    </p>
    <div class="mt-5 grid gap-3 sm:grid-cols-2">
      <div class="flex items-start gap-3 rounded-md border border-border/40 bg-background/40 p-3">
        <Search class="mt-0.5 h-4 w-4 shrink-0 text-cyan-400" />
        <div>
          <div class="text-sm font-semibold">Multi-indexer search</div>
          <div class="mt-1 text-xs text-muted-foreground">
            Query Newznab, Torznab, UNIT3D, RarTracker, and Cardigann trackers in parallel
            with a single search.
          </div>
        </div>
      </div>
      <div class="flex items-start gap-3 rounded-md border border-border/40 bg-background/40 p-3">
        <Rss class="mt-0.5 h-4 w-4 shrink-0 text-orange-400" />
        <div>
          <div class="text-sm font-semibold">RSS feed cache</div>
          <div class="mt-1 text-xs text-muted-foreground">
            Poll tracker RSS feeds, build a searchable local archive, and run standing
            filter rules against it.
          </div>
        </div>
      </div>
      <div class="flex items-start gap-3 rounded-md border border-border/40 bg-background/40 p-3">
        <Bot class="mt-0.5 h-4 w-4 shrink-0 text-fuchsia-400" />
        <div>
          <div class="text-sm font-semibold">Local AI agent</div>
          <div class="mt-1 text-xs text-muted-foreground">
            Talk to Trove in plain English via Ollama or any litellm-compatible backend. It
            proposes, you confirm.
          </div>
        </div>
      </div>
      <div class="flex items-start gap-3 rounded-md border border-border/40 bg-background/40 p-3">
        <Database class="mt-0.5 h-4 w-4 shrink-0 text-violet-400" />
        <div>
          <div class="text-sm font-semibold">Task engine & watchlist</div>
          <div class="mt-1 text-xs text-muted-foreground">
            Hourly backfill, episode-level dedup, per-season iteration, strict title
            matching. Tasks survive restarts, cascade cleanly on delete.
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- Maker -->
  <div class="surface p-6">
    <div class="mb-4 flex items-center gap-2">
      <Sparkles class="h-5 w-5 text-amber-400" />
      <h2 class="text-lg font-semibold">Who made this</h2>
    </div>
    <p class="text-sm text-muted-foreground">
      Trove is developed by
      <strong class="text-foreground">PowerData</strong> — a one-person project built in
      evenings and weekends, scratching a very specific itch of having a single pane of
      glass over a bunch of private trackers, indexers, and download clients. Released under
      GPL-3.0 because media tooling should be open.
    </p>
  </div>

  <!-- Coffee -->
  <div
    class="surface relative overflow-hidden p-6"
    style="background-image: linear-gradient(135deg, hsl(42 85% 50% / 0.08) 0%, transparent 60%);"
  >
    <div class="mb-4 flex items-center gap-2">
      <Heart class="h-5 w-5 text-rose-400" />
      <h2 class="text-lg font-semibold">Support the project</h2>
    </div>
    <p class="text-sm text-muted-foreground">
      Trove is free and open source and always will be. If it saves you time, consider
      buying a coffee — it keeps the late-night commits flowing, pays for the test VPS, and
      funds the occasional "why is this tracker's API like this" bug-hunting session.
    </p>
    <a
      href="https://www.buymeacoffee.com/MasterDraco"
      target="_blank"
      rel="noopener noreferrer"
      class="btn-primary mt-4 inline-flex items-center gap-2"
    >
      <Coffee class="h-4 w-4" />
      Buy me a coffee
    </a>
    <p class="mt-3 text-xs text-muted-foreground">
      Not the buying type? A GitHub star on
      <a
        href="https://github.com/masterdraco/Trove"
        target="_blank"
        rel="noopener noreferrer"
        class="text-primary underline-offset-2 hover:underline">the repo</a
      > is equally appreciated and free.
    </p>
  </div>

  <!-- Privacy / license strip -->
  <div class="surface p-6">
    <div class="mb-3 flex items-center gap-2">
      <Shield class="h-5 w-5 text-teal-400" />
      <h2 class="text-lg font-semibold">Privacy &amp; data</h2>
    </div>
    <ul class="space-y-2 text-sm text-muted-foreground">
      <li>
        <strong class="text-foreground">Everything runs locally.</strong> Your credentials
        (indexer API keys, tracker session cookies, download-client passwords) are encrypted
        at rest in SQLite using a key derived from
        <code class="font-mono text-xs">session.secret</code>.
      </li>
      <li>
        <strong class="text-foreground">No telemetry.</strong> Trove doesn't call home. The
        only outbound requests are the ones you configure — your indexers, your trackers,
        your AI endpoint, and a weekly GitHub check for new releases.
      </li>
      <li>
        <strong class="text-foreground">Your data is yours.</strong> Full
        <a href="/settings#backup" class="text-primary underline-offset-2 hover:underline">backup</a>
        with one click — the zip contains your DB, your session secret, and a manifest. Move
        the zip to a new host and restore in one click. No vendor lock-in.
      </li>
    </ul>
  </div>
</div>
