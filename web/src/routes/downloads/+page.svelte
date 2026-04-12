<script lang="ts">
  import { onMount } from "svelte";
  import { api, type DownloadOut } from "$lib/api";
  import {
    Download,
    CheckCircle2,
    XCircle,
    Clock,
    Loader2,
    AlertTriangle,
    HardDrive,
    RefreshCw
  } from "lucide-svelte";

  let downloads = $state<DownloadOut[]>([]);
  let loading = $state(true);
  let filter = $state<string>("all");
  let refreshing = $state(false);
  let timer: ReturnType<typeof setInterval> | null = null;

  async function load() {
    try {
      const status = filter === "all" ? undefined : filter;
      downloads = await api.downloads.list(status, 100);
    } finally {
      loading = false;
      refreshing = false;
    }
  }

  async function refresh() {
    refreshing = true;
    await load();
  }

  onMount(() => {
    load();
    timer = setInterval(load, 10_000);
    return () => { if (timer) clearInterval(timer); };
  });

  function formatSize(bytes: number | null): string {
    if (!bytes || bytes <= 0) return "?";
    let b = bytes;
    for (const unit of ["B", "KB", "MB", "GB", "TB"]) {
      if (b < 1024) return `${b.toFixed(unit === "B" ? 0 : 1)} ${unit}`;
      b /= 1024;
    }
    return `${b.toFixed(1)} PB`;
  }

  function formatEta(seconds: number | null): string {
    if (!seconds || seconds <= 0) return "";
    if (seconds < 60) return `${seconds}s`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    return `${h}h ${m}m`;
  }

  function formatAge(dateStr: string): string {
    const diff = Date.now() - new Date(dateStr).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return "just now";
    if (mins < 60) return `${mins}m ago`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `${hours}h ago`;
    const days = Math.floor(hours / 24);
    return `${days}d ago`;
  }

  function statusIcon(status: string | null) {
    if (status === "completed") return CheckCircle2;
    if (status === "failed") return XCircle;
    if (status === "downloading") return Download;
    if (status === "queued") return Clock;
    if (status === "verifying") return Loader2;
    return AlertTriangle;
  }

  function statusColor(status: string | null): string {
    if (status === "completed") return "text-success";
    if (status === "failed") return "text-destructive";
    if (status === "downloading") return "text-blue-400";
    if (status === "queued") return "text-muted-foreground";
    if (status === "verifying") return "text-amber-400";
    return "text-muted-foreground";
  }

  function tierLabel(tier: number | null): string {
    if (tier === null || tier === 0) return "";
    if (tier >= 4) return "2160p";
    if (tier === 3) return "1080p";
    if (tier === 2) return "720p";
    return "SD";
  }

  function tierColor(tier: number | null): string {
    if (tier === null || tier === 0) return "text-muted-foreground";
    if (tier >= 4) return "text-purple-400";
    if (tier === 3) return "text-blue-400";
    if (tier === 2) return "text-amber-400";
    return "text-muted-foreground";
  }

  const filters = [
    { value: "all", label: "All" },
    { value: "downloading", label: "Downloading" },
    { value: "queued", label: "Queued" },
    { value: "completed", label: "Completed" },
    { value: "failed", label: "Failed" }
  ];

  $effect(() => {
    filter;
    loading = true;
    load();
  });
</script>

<div class="max-w-4xl space-y-6">
  <div class="flex items-center justify-between">
    <div>
      <h2 class="text-xl font-semibold">Downloads</h2>
      <p class="mt-1 text-sm text-muted-foreground">
        Live download progress across all clients. Auto-refreshes every 10s.
      </p>
    </div>
    <button
      class="inline-flex items-center gap-1 rounded-md border border-border bg-background px-3 py-1.5 text-xs hover:bg-muted"
      onclick={refresh}
      disabled={refreshing}
    >
      <RefreshCw class="h-3.5 w-3.5 {refreshing ? 'animate-spin' : ''}" />
      Refresh
    </button>
  </div>

  <!-- Filters -->
  <div class="flex gap-1">
    {#each filters as f}
      <button
        class="rounded-md px-3 py-1.5 text-xs font-medium transition-colors {filter === f.value
          ? 'bg-primary text-primary-foreground'
          : 'border border-border bg-card hover:bg-muted'}"
        onclick={() => (filter = f.value)}
      >
        {f.label}
      </button>
    {/each}
  </div>

  {#if loading && downloads.length === 0}
    <div class="text-sm text-muted-foreground">Loading...</div>
  {:else if downloads.length === 0}
    <div class="rounded-xl border border-dashed border-border bg-card p-10 text-center text-sm text-muted-foreground">
      <HardDrive class="mx-auto mb-2 h-6 w-6" />
      No downloads found.
    </div>
  {:else}
    <div class="space-y-2">
      {#each downloads as dl (dl.id)}
        {@const Icon = statusIcon(dl.download_status)}
        {@const pct = dl.download_progress != null ? Math.round(dl.download_progress * 100) : null}
        <div class="rounded-xl border border-border bg-card p-4">
          <div class="flex items-start gap-3">
            <div class="mt-0.5 {statusColor(dl.download_status)}">
              <Icon class="h-4 w-4 {dl.download_status === 'downloading' || dl.download_status === 'verifying' ? 'animate-pulse' : ''}" />
            </div>
            <div class="min-w-0 flex-1">
              <!-- Title + quality -->
              <div class="flex items-center gap-2">
                <span class="truncate font-mono text-sm font-medium" title={dl.title}>{dl.title}</span>
                {#if tierLabel(dl.quality_tier)}
                  <span class="shrink-0 rounded-full border border-border px-2 py-0.5 text-[10px] font-semibold {tierColor(dl.quality_tier)}">{tierLabel(dl.quality_tier)}</span>
                {/if}
              </div>

              <!-- Meta line -->
              <div class="mt-1 flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
                <span>{dl.task_name}</span>
                {#if dl.client_name}
                  <span class="flex items-center gap-1">
                    <HardDrive class="h-3 w-3" />
                    {dl.client_name}
                  </span>
                {/if}
                {#if dl.download_size_bytes}
                  <span>{formatSize(dl.download_downloaded_bytes)} / {formatSize(dl.download_size_bytes)}</span>
                {/if}
                {#if dl.download_eta_seconds && dl.download_status === "downloading"}
                  <span class="flex items-center gap-1">
                    <Clock class="h-3 w-3" />
                    {formatEta(dl.download_eta_seconds)}
                  </span>
                {/if}
                <span>{formatAge(dl.seen_at)}</span>
                {#if dl.download_status}
                  <span class="font-semibold {statusColor(dl.download_status)}">{dl.download_status}</span>
                {/if}
              </div>

              <!-- Progress bar -->
              {#if pct !== null && dl.download_status !== "completed"}
                <div class="mt-2 flex items-center gap-2">
                  <div class="h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
                    <div
                      class="h-full rounded-full transition-all duration-500 {dl.download_status === 'failed' ? 'bg-destructive' : 'bg-primary'}"
                      style="width: {pct}%"
                    ></div>
                  </div>
                  <span class="shrink-0 font-mono text-xs text-muted-foreground">{pct}%</span>
                </div>
              {/if}

              <!-- Error message -->
              {#if dl.download_error_message}
                <div class="mt-2 rounded-md border border-destructive/30 bg-destructive/10 px-2 py-1 text-xs text-destructive">
                  {dl.download_error_message}
                </div>
              {/if}
            </div>
          </div>
        </div>
      {/each}
    </div>
  {/if}
</div>
