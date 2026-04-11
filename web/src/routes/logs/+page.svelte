<script lang="ts">
  import { onMount, onDestroy, tick } from "svelte";
  import {
    ScrollText,
    Pause,
    Play,
    Trash2,
    Download,
    Filter,
    Wifi,
    WifiOff
  } from "lucide-svelte";

  type LogEntry = {
    timestamp?: string;
    level?: string;
    event?: string;
    logger?: string;
    source?: string;
    [key: string]: unknown;
  };

  const MAX_LINES = 2000;

  let entries = $state<LogEntry[]>([]);
  let connected = $state(false);
  let paused = $state(false);
  let autoScroll = $state(true);
  let filterText = $state("");
  let levelFilter = $state<"all" | "debug" | "info" | "warning" | "error">("all");
  let ws: WebSocket | null = null;
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  let containerEl: HTMLDivElement | null = null;

  const filtered = $derived.by(() => {
    const needle = filterText.trim().toLowerCase();
    return entries.filter((e) => {
      if (levelFilter !== "all") {
        const lvl = (e.level ?? "info").toLowerCase();
        if (levelFilter === "warning" && lvl !== "warning" && lvl !== "warn") return false;
        if (levelFilter === "error" && lvl !== "error" && lvl !== "critical") return false;
        if (levelFilter === "info" && !["info", "warning", "warn", "error", "critical"].includes(lvl)) return false;
        if (levelFilter === "debug" && lvl === "debug") {
          // show
        } else if (levelFilter === "debug" && lvl !== "debug") {
          return false;
        }
      }
      if (!needle) return true;
      const hay =
        (e.event ?? "") +
        " " +
        (e.logger ?? "") +
        " " +
        Object.entries(e)
          .filter(([k]) => !["timestamp", "level", "event", "logger", "source"].includes(k))
          .map(([k, v]) => `${k}=${v}`)
          .join(" ");
      return hay.toLowerCase().includes(needle);
    });
  });

  function appendEntry(entry: LogEntry) {
    if (paused) return;
    entries.push(entry);
    if (entries.length > MAX_LINES) {
      entries = entries.slice(-MAX_LINES);
    } else {
      entries = entries;
    }
    if (autoScroll) {
      tick().then(() => {
        if (containerEl) containerEl.scrollTop = containerEl.scrollHeight;
      });
    }
  }

  function connect() {
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    const url = `${proto}//${location.host}/api/logs/ws`;
    ws = new WebSocket(url);
    ws.addEventListener("open", () => {
      connected = true;
    });
    ws.addEventListener("message", (ev) => {
      try {
        const data = JSON.parse(ev.data) as LogEntry;
        appendEntry(data);
      } catch {
        /* noop */
      }
    });
    ws.addEventListener("close", () => {
      connected = false;
      ws = null;
      if (!reconnectTimer) {
        reconnectTimer = setTimeout(() => {
          reconnectTimer = null;
          connect();
        }, 2000);
      }
    });
    ws.addEventListener("error", () => {
      ws?.close();
    });
  }

  function disconnect() {
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
    if (ws) {
      ws.close();
      ws = null;
    }
    connected = false;
  }

  function clearLogs() {
    entries = [];
  }

  function downloadLogs() {
    const blob = new Blob(
      entries.map((e) => JSON.stringify(e) + "\n"),
      { type: "application/x-ndjson" }
    );
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `trove-logs-${new Date().toISOString()}.ndjson`;
    a.click();
    URL.revokeObjectURL(url);
  }

  function formatTimestamp(ts?: string): string {
    if (!ts) return "";
    try {
      const d = new Date(ts);
      return d.toLocaleTimeString("da-DK", { hour12: false }) + "." + String(d.getMilliseconds()).padStart(3, "0");
    } catch {
      return ts;
    }
  }

  function levelColor(level?: string): string {
    switch ((level ?? "info").toLowerCase()) {
      case "debug":
        return "text-muted-foreground";
      case "info":
        return "text-blue-400";
      case "warning":
      case "warn":
        return "text-amber-400";
      case "error":
      case "critical":
        return "text-destructive";
      default:
        return "text-foreground";
    }
  }

  function extraFields(entry: LogEntry): [string, unknown][] {
    const skip = new Set(["timestamp", "level", "event", "logger", "source", "exc"]);
    return Object.entries(entry).filter(([k]) => !skip.has(k));
  }

  function onScroll() {
    if (!containerEl) return;
    const atBottom =
      containerEl.scrollHeight - containerEl.scrollTop - containerEl.clientHeight < 10;
    autoScroll = atBottom;
  }

  onMount(() => {
    connect();
  });

  onDestroy(() => {
    disconnect();
  });
</script>

<div class="flex h-[calc(100vh-10rem)] flex-col space-y-4">
  <div class="flex items-start justify-between gap-4">
    <div>
      <h2 class="flex items-center gap-2 text-xl font-semibold">
        <ScrollText class="h-5 w-5" /> Live logs
      </h2>
      <p class="mt-1 text-sm text-muted-foreground">
        In-memory ring buffer of the last {MAX_LINES} events. Reconnects automatically if the server restarts.
      </p>
    </div>
    <div class="flex items-center gap-2 text-xs">
      {#if connected}
        <span class="inline-flex items-center gap-1.5 rounded-full bg-success/15 px-2.5 py-1 font-medium text-success">
          <Wifi class="h-3 w-3" /> Connected
        </span>
      {:else}
        <span class="inline-flex items-center gap-1.5 rounded-full bg-destructive/15 px-2.5 py-1 font-medium text-destructive">
          <WifiOff class="h-3 w-3" /> Reconnecting…
        </span>
      {/if}
    </div>
  </div>

  <div class="flex flex-wrap items-center gap-2">
    <div class="relative flex-1 min-w-[200px]">
      <Filter class="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
      <input
        type="text"
        placeholder="Filter…"
        bind:value={filterText}
        class="w-full rounded-md border border-border bg-muted/40 pl-9 pr-3 py-2 text-xs"
      />
    </div>
    <select
      bind:value={levelFilter}
      class="rounded-md border border-border bg-muted/40 px-3 py-2 text-xs"
    >
      <option value="all">All levels</option>
      <option value="debug">Debug+</option>
      <option value="info">Info+</option>
      <option value="warning">Warnings+</option>
      <option value="error">Errors only</option>
    </select>
    <button
      class="btn-secondary"
      onclick={() => (paused = !paused)}
      title={paused ? "Resume" : "Pause"}
    >
      {#if paused}
        <Play class="h-3.5 w-3.5" />
        Resume
      {:else}
        <Pause class="h-3.5 w-3.5" />
        Pause
      {/if}
    </button>
    <button class="btn-secondary" onclick={clearLogs} title="Clear">
      <Trash2 class="h-3.5 w-3.5" />
      Clear
    </button>
    <button class="btn-secondary" onclick={downloadLogs} title="Download">
      <Download class="h-3.5 w-3.5" />
      Export
    </button>
  </div>

  <div
    bind:this={containerEl}
    onscroll={onScroll}
    class="flex-1 overflow-y-auto rounded-xl border border-border bg-background/60 p-3 font-mono text-[11px] leading-relaxed"
  >
    {#if filtered.length === 0}
      <div class="flex h-full items-center justify-center text-muted-foreground">
        {entries.length === 0 ? "Waiting for log events…" : "No entries match the current filter."}
      </div>
    {:else}
      {#each filtered as entry (entry.timestamp + (entry.event ?? ""))}
        <div class="group flex gap-2 py-0.5 hover:bg-muted/30">
          <span class="shrink-0 text-muted-foreground">{formatTimestamp(entry.timestamp)}</span>
          <span class="shrink-0 w-14 font-semibold uppercase {levelColor(entry.level)}">{entry.level ?? "info"}</span>
          {#if entry.logger}
            <span class="shrink-0 text-muted-foreground">[{entry.logger}]</span>
          {/if}
          <span class="break-all text-foreground">{entry.event ?? ""}</span>
          {#each extraFields(entry) as [k, v]}
            <span class="break-all text-muted-foreground">
              <span class="text-primary">{k}</span>=<span>{typeof v === "string" ? v : JSON.stringify(v)}</span>
            </span>
          {/each}
        </div>
      {/each}
    {/if}
  </div>

  <div class="flex items-center justify-between text-xs text-muted-foreground">
    <span>{filtered.length} of {entries.length} lines</span>
    <span>
      {#if autoScroll}Auto-scrolling{:else}Scroll paused — scroll to bottom to resume{/if}
      {#if paused} · Paused{/if}
    </span>
  </div>
</div>
