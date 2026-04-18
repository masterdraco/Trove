<script lang="ts">
  import { onMount } from "svelte";
  import {
    api,
    type SearchHit,
    type DownloadClientOut,
    type BrowseCategory
  } from "$lib/api";
  import {
    Loader2,
    Send,
    Package,
    Gamepad2,
    RefreshCw,
    ExternalLink
  } from "lucide-svelte";

  type TabDef = {
    key: BrowseCategory;
    label: string;
    icon: typeof Package;
  };

  type SteamMatch = {
    appid: number;
    name: string;
    url: string;
    image: string | null;
    confidence: number;
  };

  // Below this, the match is too weak to show as "this is probably it" —
  // we fall back to a Steam search link instead of misleading the user.
  const MIN_CONFIDENCE = 0.4;
  const STRONG_CONFIDENCE = 0.75;

  const tabs: TabDef[] = [
    { key: "software", label: "Apps", icon: Package },
    { key: "games", label: "Games", icon: Gamepad2 }
  ];

  let active = $state<BrowseCategory>("software");
  let loading = $state(false);
  let hits = $state<SearchHit[]>([]);
  let elapsed = $state(0);
  let indexersUsed = $state(0);
  let errors = $state<{ name: string; message: string }[]>([]);
  let clients = $state<DownloadClientOut[]>([]);
  let sendingId = $state<string | null>(null);

  // Keyed by the cleaned title. Value is undefined while in-flight,
  // null when Steam found nothing, or the match otherwise.
  let steamMatches = $state<Record<string, SteamMatch | null | undefined>>({});

  onMount(async () => {
    try {
      clients = await api.clients.list();
    } catch {
      clients = [];
    }
    await load(active);
  });

  // Strip release-group tags, versions, build numbers, quality markers,
  // bracketed noise, and turn dots/underscores into spaces. Good enough
  // to turn "Baldurs.Gate.3.v4.1.1.Hotfix5-FitGirl" into "Baldurs Gate 3".
  const RELEASE_GROUPS =
    /-(FitGirl|DODI|Razor1911|CODEX|FLT|PLAZA|GOG|SKIDROW|RELOADED|ALI213|TiNYiSO|DARKSiDERS|ElAmigos|Empress|RUNE|P2P|REPACK|PROPER|NSW|Switch|TENOKE|RazorDOX|DRMFREE|FCKDRM)(\b|[._-])/gi;
  const NOISE_TAGS =
    /\b(1080p|2160p|720p|x264|x265|HEVC|REPACK|PROPER|MULTi\d*|MULTI\d*|NSW|PKG|NSP|XCI|ISO|EXE|ZIP|RAR|7z|MacOSX|MacOS|Linux|WIN64|WIN32|x86|x64|amd64)\b/gi;

  function cleanTitle(title: string): string {
    let s = title;
    s = s.replace(RELEASE_GROUPS, " ");
    s = s.replace(/\bv\d+(\.\d+)*[a-z0-9]*\b/gi, " ");
    s = s.replace(/\bBuild[\s._-]*\d+\b/gi, " ");
    s = s.replace(/\bUpdate[\s._-]*\d+\b/gi, " ");
    s = s.replace(/\bHotfix\d*\b/gi, " ");
    s = s.replace(/\[[^\]]*\]/g, " ");
    s = s.replace(/\([^)]*\)/g, " ");
    s = s.replace(/\{[^}]*\}/g, " ");
    s = s.replace(NOISE_TAGS, " ");
    s = s.replace(/[._]+/g, " ");
    s = s.replace(/\s+/g, " ").trim();
    s = s.replace(/[-\s]+$/, "").replace(/^[-\s]+/, "");
    return s || title;
  }

  async function load(cat: BrowseCategory) {
    active = cat;
    loading = true;
    errors = [];
    try {
      const res = await api.browse.latest(cat, { limit: 50 });
      hits = res.hits;
      elapsed = res.elapsed_ms;
      indexersUsed = res.indexers_used;
      errors = res.errors;
      if (cat === "games") {
        enrichWithSteam(hits);
      }
    } catch (e) {
      hits = [];
      errors = [
        { name: "browse", message: (e as { detail?: string }).detail ?? "failed" }
      ];
    } finally {
      loading = false;
    }
  }

  async function enrichWithSteam(list: SearchHit[]) {
    const todo = new Set<string>();
    for (const h of list) {
      const cleaned = cleanTitle(h.title);
      if (cleaned && !(cleaned in steamMatches)) {
        todo.add(cleaned);
      }
    }
    // Kick off lookups in parallel. Each result is merged into the store
    // as it resolves so rows update progressively instead of all-at-once.
    await Promise.all(
      Array.from(todo).map(async (name) => {
        steamMatches = { ...steamMatches, [name]: undefined };
        try {
          const res = await api.browse.steam(name);
          steamMatches = { ...steamMatches, [name]: res.match };
        } catch {
          steamMatches = { ...steamMatches, [name]: null };
        }
      })
    );
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

  function formatDate(iso: string | null): string {
    if (!iso) return "—";
    const d = new Date(iso);
    if (isNaN(d.getTime())) return iso;
    return d.toLocaleString();
  }

  function googleSearchUrl(q: string): string {
    return `https://www.google.com/search?q=${encodeURIComponent(q)}`;
  }

  function steamSearchUrl(q: string): string {
    return `https://store.steampowered.com/search/?term=${encodeURIComponent(q)}`;
  }
</script>

<div class="space-y-6">
  <div class="flex items-center justify-between">
    <div>
      <h1 class="text-2xl font-bold tracking-tight">Latest releases</h1>
      <p class="mt-1 text-sm text-muted-foreground">
        Newest items pushed to your indexers — no search needed.
      </p>
    </div>
    <button
      type="button"
      onclick={() => load(active)}
      disabled={loading}
      class="inline-flex items-center gap-2 rounded-md border border-border bg-background px-3 py-2 text-sm hover:bg-muted disabled:opacity-60"
      title="Refresh"
    >
      {#if loading}
        <Loader2 class="h-4 w-4 animate-spin" />
      {:else}
        <RefreshCw class="h-4 w-4" />
      {/if}
      Refresh
    </button>
  </div>

  <div class="flex items-center gap-2 border-b border-border">
    {#each tabs as tab}
      {@const isActive = tab.key === active}
      {@const Icon = tab.icon}
      <button
        type="button"
        onclick={() => load(tab.key)}
        class="-mb-px flex items-center gap-2 border-b-2 px-4 py-2 text-sm font-medium transition-colors {isActive
          ? 'border-primary text-primary'
          : 'border-transparent text-muted-foreground hover:text-foreground'}"
      >
        <Icon class="h-4 w-4" />
        {tab.label}
      </button>
    {/each}
  </div>

  {#if errors.length > 0}
    <div class="rounded-md border border-yellow-500/30 bg-yellow-500/10 p-3 text-sm">
      <div class="font-medium">Some indexers couldn't browse this category:</div>
      <ul class="mt-1 space-y-0.5 text-xs text-muted-foreground">
        {#each errors as err}
          <li>{err.name}: {err.message}</li>
        {/each}
      </ul>
    </div>
  {/if}

  {#if loading && hits.length === 0}
    <div class="rounded-xl border border-dashed border-border bg-card p-10 text-center text-sm text-muted-foreground">
      <Loader2 class="mx-auto mb-3 h-6 w-6 animate-spin" />
      Loading latest {active}…
    </div>
  {:else if hits.length > 0}
    <div class="text-xs text-muted-foreground">
      {hits.length} items from {indexersUsed} indexer{indexersUsed === 1 ? "" : "s"} in {elapsed}ms
    </div>
    <div class="overflow-hidden rounded-xl border border-border bg-card">
      <table class="w-full text-sm">
        <thead class="bg-muted/50 text-left text-xs uppercase tracking-wide text-muted-foreground">
          <tr>
            <th class="px-4 py-3 font-medium">Title</th>
            <th class="px-4 py-3 font-medium">Published</th>
            <th class="px-4 py-3 font-medium">Size</th>
            <th class="px-4 py-3 font-medium">S/L</th>
            <th class="px-4 py-3 font-medium">Source</th>
            <th class="px-4 py-3 font-medium"></th>
          </tr>
        </thead>
        <tbody>
          {#each hits as hit}
            {@const cleaned = cleanTitle(hit.title)}
            {@const match = active === "games" ? steamMatches[cleaned] : undefined}
            <tr class="border-t border-border">
              <td class="max-w-xl px-4 py-3">
                <div class="truncate font-medium">{hit.title}</div>
                <div class="mt-0.5 flex items-center gap-2 text-xs text-muted-foreground">
                  <span>{hit.protocol} · {hit.category ?? "—"}</span>
                  {#if active === "games"}
                    {#if match === undefined}
                      <span class="inline-flex items-center gap-1 text-muted-foreground/70">
                        <Loader2 class="h-3 w-3 animate-spin" /> looking up…
                      </span>
                    {:else if match && match.confidence >= MIN_CONFIDENCE}
                      {@const isStrong = match.confidence >= STRONG_CONFIDENCE}
                      <a
                        href={match.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        class="inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[11px] {isStrong
                          ? 'border-primary/30 bg-primary/10 text-primary hover:bg-primary/20'
                          : 'border-yellow-500/30 bg-yellow-500/10 text-yellow-600 hover:bg-yellow-500/20 dark:text-yellow-400'}"
                        title={isStrong
                          ? `Open on Steam (match ${Math.round(match.confidence * 100)}%)`
                          : `Possible match (${Math.round(match.confidence * 100)}%) — verify`}
                      >
                        {#if match.image}
                          <img src={match.image} alt="" class="h-3 w-auto rounded-sm" />
                        {/if}
                        {isStrong ? "Steam" : "Maybe"}: {match.name}
                        <ExternalLink class="h-3 w-3" />
                      </a>
                    {:else}
                      <a
                        href={steamSearchUrl(cleaned)}
                        target="_blank"
                        rel="noopener noreferrer"
                        class="inline-flex items-center gap-1 text-muted-foreground hover:text-foreground"
                        title="Search on Steam"
                      >
                        Search Steam
                        <ExternalLink class="h-3 w-3" />
                      </a>
                    {/if}
                  {:else if active === "software"}
                    <a
                      href={googleSearchUrl(cleaned)}
                      target="_blank"
                      rel="noopener noreferrer"
                      class="inline-flex items-center gap-1 text-muted-foreground hover:text-foreground"
                      title="Search Google for this app"
                    >
                      Search: {cleaned}
                      <ExternalLink class="h-3 w-3" />
                    </a>
                  {/if}
                </div>
              </td>
              <td class="whitespace-nowrap px-4 py-3 text-xs text-muted-foreground">
                {formatDate(hit.published_at)}
              </td>
              <td class="px-4 py-3 text-xs">{formatSize(hit.size)}</td>
              <td class="px-4 py-3 text-xs">
                {hit.seeders ?? "—"}/{hit.leechers ?? "—"}
              </td>
              <td class="px-4 py-3 text-xs text-muted-foreground">{hit.source ?? "—"}</td>
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
  {:else}
    <div class="rounded-xl border border-dashed border-border bg-card p-10 text-center text-sm text-muted-foreground">
      No {active} releases found. Your indexers either don't support browsing this category
      or returned no items.
    </div>
  {/if}
</div>
