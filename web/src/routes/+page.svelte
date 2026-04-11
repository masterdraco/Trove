<script lang="ts">
  import { onMount } from "svelte";
  import { api } from "$lib/api";
  import {
    Database,
    Download,
    ListChecks,
    Eye,
    Sparkles,
    Rss,
    TrendingUp,
    Zap,
    ArrowRight
  } from "lucide-svelte";

  let version = $state<string | null>(null);
  let stats = $state({
    clients: 0,
    indexers: 0,
    feeds: 0,
    tasks: 0,
    watchlist: 0,
    rssItems: 0
  });
  let recentRuns = $state<
    {
      task: string;
      status: string;
      accepted: number;
      considered: number;
      started_at: string;
    }[]
  >([]);
  let aiOk = $state<boolean | null>(null);
  let feedActivity = $state<{ name: string; new_items: number; last_polled: string | null }[]>(
    []
  );

  async function load() {
    try {
      version = (await api.health()).version;
    } catch {}
    try {
      const [clients, indexers, feeds, tasks, watchlist] = await Promise.all([
        api.clients.list(),
        api.indexers.list(),
        api.feeds.list(),
        api.tasks.list(),
        api.watchlist.list()
      ]);
      const rssItems = feeds.reduce((sum, f) => sum + (f.total_items || 0), 0);
      stats = {
        clients: clients.length,
        indexers: indexers.length,
        feeds: feeds.length,
        tasks: tasks.length,
        watchlist: watchlist.length,
        rssItems
      };

      feedActivity = feeds
        .filter((f) => f.last_polled_at)
        .sort((a, b) => (a.last_polled_at! > b.last_polled_at! ? -1 : 1))
        .slice(0, 5)
        .map((f) => ({
          name: f.name,
          new_items: f.last_new_items,
          last_polled: f.last_polled_at
        }));

      const runs: typeof recentRuns = [];
      for (const task of tasks.slice(0, 10)) {
        try {
          const taskRuns = await api.tasks.runs(task.id);
          for (const r of taskRuns.slice(0, 2)) {
            runs.push({
              task: task.name,
              status: r.status,
              accepted: r.accepted,
              considered: r.considered,
              started_at: r.started_at
            });
          }
        } catch {}
      }
      runs.sort((a, b) => (a.started_at > b.started_at ? -1 : 1));
      recentRuns = runs.slice(0, 6);
    } catch {}
    try {
      const ai = await api.ai.status();
      aiOk = ai.enabled;
    } catch {
      aiOk = false;
    }
  }

  onMount(load);

  function formatTime(iso: string | null): string {
    if (!iso) return "never";
    const d = new Date(iso);
    const diff = Date.now() - d.getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return "just now";
    if (mins < 60) return `${mins}m ago`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `${hours}h ago`;
    return `${Math.floor(hours / 24)}d ago`;
  }

  const statCards = $derived([
    {
      href: "/clients",
      label: "Clients",
      value: stats.clients,
      sub: null as string | null,
      icon: Download,
      gradient: "from-emerald-500/20 to-emerald-500/5",
      iconColor: "text-emerald-400"
    },
    {
      href: "/indexers",
      label: "Indexers",
      value: stats.indexers,
      sub: null as string | null,
      icon: Database,
      gradient: "from-blue-500/20 to-blue-500/5",
      iconColor: "text-blue-400"
    },
    {
      href: "/feeds",
      label: "RSS Feeds",
      value: stats.feeds,
      sub: `${stats.rssItems.toLocaleString()} cached`,
      icon: Rss,
      gradient: "from-orange-500/20 to-orange-500/5",
      iconColor: "text-orange-400"
    },
    {
      href: "/tasks",
      label: "Tasks",
      value: stats.tasks,
      sub: null as string | null,
      icon: ListChecks,
      gradient: "from-violet-500/20 to-violet-500/5",
      iconColor: "text-violet-400"
    },
    {
      href: "/watchlist",
      label: "Watchlist",
      value: stats.watchlist,
      sub: null as string | null,
      icon: Eye,
      gradient: "from-pink-500/20 to-pink-500/5",
      iconColor: "text-pink-400"
    }
  ]);
</script>

<div class="space-y-8">
  <!-- Hero header -->
  <div class="flex items-end justify-between">
    <div>
      <div class="text-xs uppercase tracking-widest text-muted-foreground">Welcome back</div>
      <h1 class="mt-1 text-4xl font-bold tracking-tight">
        Your <span class="text-gradient">command center</span>
      </h1>
      <p class="mt-2 text-sm text-muted-foreground">
        Search, automate, and fetch from every source at once.
      </p>
    </div>
    {#if version}
      <div class="chip">
        <span class="h-1.5 w-1.5 animate-pulse rounded-full bg-success"></span>
        online · v{version}
      </div>
    {/if}
  </div>

  <!-- Stat cards -->
  <div class="grid gap-4 md:grid-cols-3 xl:grid-cols-5">
    {#each statCards as card}
      {@const Icon = card.icon}
      <a
        href={card.href}
        class="surface group relative overflow-hidden p-5 transition-all hover:-translate-y-0.5 hover:border-border"
      >
        <div
          class="absolute inset-0 bg-gradient-to-br {card.gradient} opacity-60 transition-opacity group-hover:opacity-100"
        ></div>
        <div class="relative">
          <div class="flex items-center justify-between">
            <div class="rounded-xl bg-card/60 p-2 backdrop-blur-sm">
              <Icon class="h-5 w-5 {card.iconColor}" />
            </div>
            <ArrowRight class="h-4 w-4 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />
          </div>
          <div class="mt-4 text-3xl font-bold tracking-tight">{card.value}</div>
          <div class="mt-1 text-xs text-muted-foreground">
            {card.label}{#if card.sub} · {card.sub}{/if}
          </div>
        </div>
      </a>
    {/each}
  </div>

  <!-- Quick actions -->
  <div class="surface p-6">
    <div class="flex items-center gap-2 text-sm font-semibold">
      <Zap class="h-4 w-4 text-primary" />
      Quick actions
    </div>
    <div class="mt-4 flex flex-wrap gap-2">
      <a href="/search" class="btn-primary">Run a search</a>
      <a href="/tasks" class="btn-secondary">Create a task</a>
      <a href="/ai" class="btn-secondary">
        <Sparkles class="h-3.5 w-3.5" /> Ask AI
      </a>
      <a href="/feeds" class="btn-secondary">Add RSS feed</a>
    </div>
  </div>

  <div class="grid gap-4 lg:grid-cols-2">
    <!-- Recent task runs -->
    <div class="surface p-6">
      <div class="flex items-center justify-between">
        <h3 class="flex items-center gap-2 text-sm font-semibold">
          <TrendingUp class="h-4 w-4 text-violet-400" /> Recent task runs
        </h3>
        <a href="/history" class="text-xs text-muted-foreground hover:text-foreground">
          see all →
        </a>
      </div>
      {#if recentRuns.length === 0}
        <p class="mt-4 text-sm text-muted-foreground">No runs yet. Create a task to get started.</p>
      {:else}
        <ul class="mt-4 space-y-2">
          {#each recentRuns as run}
            <li class="flex items-center justify-between rounded-xl border border-border/50 bg-card/40 px-3 py-2 text-sm">
              <div class="min-w-0">
                <div class="truncate font-medium">{run.task}</div>
                <div class="text-[10px] text-muted-foreground">{formatTime(run.started_at)}</div>
              </div>
              <div class="flex items-center gap-2">
                <span class="font-mono text-xs text-muted-foreground">
                  {run.accepted}/{run.considered}
                </span>
                {#if run.status === "success"}
                  <span class="chip-success">{run.status}</span>
                {:else}
                  <span class="chip-danger">{run.status}</span>
                {/if}
              </div>
            </li>
          {/each}
        </ul>
      {/if}
    </div>

    <!-- Feed activity -->
    <div class="surface p-6">
      <div class="flex items-center justify-between">
        <h3 class="flex items-center gap-2 text-sm font-semibold">
          <Rss class="h-4 w-4 text-orange-400" /> Feed activity
        </h3>
        <a href="/feeds" class="text-xs text-muted-foreground hover:text-foreground">
          manage →
        </a>
      </div>
      {#if feedActivity.length === 0}
        <p class="mt-4 text-sm text-muted-foreground">
          No RSS feeds yet. Add one to cache releases for fast search.
        </p>
      {:else}
        <ul class="mt-4 space-y-2">
          {#each feedActivity as f}
            <li class="flex items-center justify-between rounded-xl border border-border/50 bg-card/40 px-3 py-2 text-sm">
              <div class="min-w-0">
                <div class="truncate font-medium">{f.name}</div>
                <div class="text-[10px] text-muted-foreground">{formatTime(f.last_polled)}</div>
              </div>
              <span class="chip-primary">+{f.new_items}</span>
            </li>
          {/each}
        </ul>
      {/if}
    </div>
  </div>

  <!-- AI hero -->
  <div class="surface relative overflow-hidden p-6">
    <div class="absolute inset-0 bg-gradient-to-br from-fuchsia-500/10 via-transparent to-primary/15"></div>
    <div class="relative flex items-start gap-4">
      <div
        class="flex h-12 w-12 items-center justify-center rounded-2xl glow-primary"
        style="background-image: linear-gradient(135deg, hsl(300 85% 60%) 0%, hsl(var(--primary)) 100%);"
      >
        <Sparkles class="h-6 w-6 text-white" />
      </div>
      <div class="flex-1">
        <h3 class="text-base font-semibold">AI Assistant</h3>
        <p class="mt-1 text-sm text-muted-foreground">
          {#if aiOk}
            Say <em>"add The Big Bang Theory to my downloads"</em> and confirm. No YAML, no fiddling.
          {:else if aiOk === false}
            AI is disabled or unreachable. Check the connection from Settings.
          {:else}
            Checking AI status…
          {/if}
        </p>
        <div class="mt-3 flex gap-2">
          <a href="/ai" class="btn-primary">Open chat</a>
          <a href="/settings" class="btn-secondary">Settings</a>
        </div>
      </div>
    </div>
  </div>
</div>
