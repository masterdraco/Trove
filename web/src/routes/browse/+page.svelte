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
    ExternalLink,
    Film,
    Tv,
    Sparkles
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

  type TmdbMatch = {
    tmdb_id: number;
    kind: string;
    title: string;
    year: number | null;
    rating: number | null;
    poster_url: string | null;
    backdrop_url: string | null;
    url: string;
    confidence: number;
  };

  // Below this, the match is too weak to show as "this is probably it".
  const MIN_CONFIDENCE = 0.4;
  const STRONG_CONFIDENCE = 0.75;

  const tabs: TabDef[] = [
    { key: "movies", label: "Movies", icon: Film },
    { key: "tv", label: "TV", icon: Tv },
    { key: "anime", label: "Anime", icon: Sparkles },
    { key: "games", label: "Games", icon: Gamepad2 },
    { key: "software", label: "Apps", icon: Package }
  ];

  let active = $state<BrowseCategory>("movies");
  let loading = $state(false);
  let hits = $state<SearchHit[]>([]);
  let elapsed = $state(0);
  let indexersUsed = $state(0);
  let errors = $state<{ name: string; message: string }[]>([]);
  let clients = $state<DownloadClientOut[]>([]);
  let sendingId = $state<string | null>(null);

  // Per-namespace enrichment stores. Keyed by the cleaned/parsed query.
  // undefined = in-flight, null = provider had no match.
  let steamMatches = $state<Record<string, SteamMatch | null | undefined>>({});
  let tmdbMatches = $state<Record<string, TmdbMatch | null | undefined>>({});

  onMount(async () => {
    try {
      clients = await api.clients.list();
    } catch {
      clients = [];
    }
    await load(active);
  });

  const RELEASE_GROUPS =
    /-(FitGirl|DODI|Razor1911|CODEX|FLT|PLAZA|GOG|SKIDROW|RELOADED|ALI213|TiNYiSO|DARKSiDERS|ElAmigos|Empress|RUNE|P2P|REPACK|PROPER|NSW|Switch|TENOKE|RazorDOX|DRMFREE|FCKDRM|RARBG|YTS|YIFY|EZTV|NTb|SYNCOPY|FLUX|CAKES|NOSiViD|ETHEL|ION10|SubsPlease|Erai-raws)(\b|[._-])/gi;
  const NOISE_TAGS =
    /\b(1080p|2160p|720p|480p|4K|UHD|x264|x265|HEVC|H264|H265|REPACK|PROPER|REMUX|BluRay|Blu-Ray|WEB-DL|WEBRip|WEB|HDTV|DVDRip|BDRip|HDRip|MULTi\d*|MULTI\d*|NSW|PKG|NSP|XCI|ISO|EXE|ZIP|RAR|7z|MacOSX|MacOS|Linux|WIN64|WIN32|x86|x64|amd64|AMZN|NF|HMAX|DSNP|HULU|ATVP|PMTP|DDP5?\.?1|DD5?\.?1|AAC2?\.?0|AAC5?\.?1|FLAC|Atmos|TrueHD|10bit|HDR|HDR10|DV|Dolby|EAC3|AC3)\b/gi;

  function stripNoise(s: string): string {
    let out = s;
    out = out.replace(RELEASE_GROUPS, " ");
    out = out.replace(/\bv\d+(\.\d+)*[a-z0-9]*\b/gi, " ");
    out = out.replace(/\bBuild[\s._-]*\d+\b/gi, " ");
    out = out.replace(/\bUpdate[\s._-]*\d+\b/gi, " ");
    out = out.replace(/\bHotfix\d*\b/gi, " ");
    out = out.replace(/\[[^\]]*\]/g, " ");
    out = out.replace(/\([^)]*\)/g, " ");
    out = out.replace(/\{[^}]*\}/g, " ");
    out = out.replace(NOISE_TAGS, " ");
    out = out.replace(/[._]+/g, " ");
    out = out.replace(/\s+/g, " ").trim();
    out = out.replace(/[-\s]+$/, "").replace(/^[-\s]+/, "");
    return out;
  }

  type Parsed = {
    name: string;
    year: number | null;
    season: number | null;
    episode: number | null;
  };

  // Extract the earliest "cut point" — the name portion ends before the
  // first occurrence of a year, SxxExx, or a quality tag. Everything
  // after that is release metadata we don't want in the search query.
  function parseRelease(title: string): Parsed {
    const yearMatch = title.match(/[\s._\-\(\[](19[7-9]\d|20[0-4]\d)[\s._\-\)\]]/);
    const year = yearMatch ? parseInt(yearMatch[1], 10) : null;
    const yearIdx = yearMatch
      ? title.indexOf(yearMatch[0]) + 1 // skip the leading delimiter
      : -1;

    const sxxexx = title.match(/[\s._\-][Ss](\d{1,2})[Ee](\d{1,3})\b/);
    const season = sxxexx ? parseInt(sxxexx[1], 10) : null;
    const episode = sxxexx ? parseInt(sxxexx[2], 10) : null;
    const sxxexxIdx = sxxexx ? title.indexOf(sxxexx[0]) : -1;

    const quality = title.match(
      /[\s._\-](1080p|2160p|720p|480p|4K|UHD|BluRay|Blu-Ray|WEB-DL|WEBRip|WEB|HDTV|DVDRip|BDRip|HDRip|REMUX)\b/i
    );
    const qualityIdx = quality ? title.indexOf(quality[0]) : -1;

    const candidates = [yearIdx, sxxexxIdx, qualityIdx].filter((i) => i > 0);
    const cut = candidates.length > 0 ? Math.min(...candidates) : title.length;

    const namePart = title.substring(0, cut);
    return {
      name: stripNoise(namePart),
      year,
      season,
      episode
    };
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
      } else if (cat === "movies" || cat === "tv" || cat === "anime") {
        enrichWithTmdb(hits, cat);
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
      const { name } = parseRelease(h.title);
      if (name && !(name in steamMatches)) todo.add(name);
    }
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

  async function enrichWithTmdb(list: SearchHit[], cat: BrowseCategory) {
    const kind: "movie" | "tv" = cat === "movies" ? "movie" : "tv";
    const todo = new Map<string, { name: string; year: number | null }>();
    for (const h of list) {
      const parsed = parseRelease(h.title);
      if (!parsed.name) continue;
      const key = tmdbKey(parsed.name, kind, parsed.year);
      if (!(key in tmdbMatches)) {
        todo.set(key, { name: parsed.name, year: parsed.year });
      }
    }
    await Promise.all(
      Array.from(todo.entries()).map(async ([key, { name, year }]) => {
        tmdbMatches = { ...tmdbMatches, [key]: undefined };
        try {
          const res = await api.browse.tmdb(name, kind, year);
          tmdbMatches = { ...tmdbMatches, [key]: res.match };
        } catch {
          tmdbMatches = { ...tmdbMatches, [key]: null };
        }
      })
    );
  }

  function tmdbKey(name: string, kind: "movie" | "tv", year: number | null): string {
    return `${kind}::${name.toLowerCase()}::${year ?? ""}`;
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

  function tmdbSearchUrl(q: string, kind: "movie" | "tv"): string {
    return `https://www.themoviedb.org/search/${kind}?query=${encodeURIComponent(q)}`;
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

  <div class="flex flex-wrap items-center gap-2 border-b border-border">
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
            {@const parsed = parseRelease(hit.title)}
            {@const steamMatch = active === "games" ? steamMatches[parsed.name] : undefined}
            {@const tmdbKind = active === "movies" ? "movie" : active === "tv" || active === "anime" ? "tv" : null}
            {@const tmdbMatch = tmdbKind
              ? tmdbMatches[tmdbKey(parsed.name, tmdbKind, parsed.year)]
              : undefined}
            <tr class="border-t border-border">
              <td class="max-w-xl px-4 py-3">
                <div class="flex items-start gap-3">
                  {#if tmdbKind && tmdbMatch && tmdbMatch.confidence >= MIN_CONFIDENCE && tmdbMatch.poster_url}
                    <a
                      href={tmdbMatch.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      class="shrink-0"
                      title="Open on TMDB"
                    >
                      <img
                        src={tmdbMatch.poster_url}
                        alt=""
                        class="h-16 w-auto rounded border border-border"
                        loading="lazy"
                      />
                    </a>
                  {/if}
                  <div class="min-w-0 flex-1">
                    <div class="truncate font-medium">{hit.title}</div>
                    <div class="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                      <span>{hit.protocol} · {hit.category ?? "—"}</span>

                      {#if active === "games"}
                        {#if steamMatch === undefined}
                          <span class="inline-flex items-center gap-1 text-muted-foreground/70">
                            <Loader2 class="h-3 w-3 animate-spin" /> looking up…
                          </span>
                        {:else if steamMatch && steamMatch.confidence >= MIN_CONFIDENCE}
                          {@const isStrong = steamMatch.confidence >= STRONG_CONFIDENCE}
                          <a
                            href={steamMatch.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            class="inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[11px] {isStrong
                              ? 'border-primary/30 bg-primary/10 text-primary hover:bg-primary/20'
                              : 'border-yellow-500/30 bg-yellow-500/10 text-yellow-600 hover:bg-yellow-500/20 dark:text-yellow-400'}"
                            title={isStrong
                              ? `Open on Steam (match ${Math.round(steamMatch.confidence * 100)}%)`
                              : `Possible match (${Math.round(steamMatch.confidence * 100)}%) — verify`}
                          >
                            {#if steamMatch.image}
                              <img src={steamMatch.image} alt="" class="h-3 w-auto rounded-sm" />
                            {/if}
                            {isStrong ? "Steam" : "Maybe"}: {steamMatch.name}
                            <ExternalLink class="h-3 w-3" />
                          </a>
                        {:else}
                          <a
                            href={steamSearchUrl(parsed.name)}
                            target="_blank"
                            rel="noopener noreferrer"
                            class="inline-flex items-center gap-1 text-muted-foreground hover:text-foreground"
                            title="Search on Steam"
                          >
                            Search Steam
                            <ExternalLink class="h-3 w-3" />
                          </a>
                        {/if}
                      {:else if tmdbKind}
                        {#if tmdbMatch === undefined}
                          <span class="inline-flex items-center gap-1 text-muted-foreground/70">
                            <Loader2 class="h-3 w-3 animate-spin" /> looking up…
                          </span>
                        {:else if tmdbMatch && tmdbMatch.confidence >= MIN_CONFIDENCE}
                          {@const isStrong = tmdbMatch.confidence >= STRONG_CONFIDENCE}
                          <a
                            href={tmdbMatch.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            class="inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[11px] {isStrong
                              ? 'border-primary/30 bg-primary/10 text-primary hover:bg-primary/20'
                              : 'border-yellow-500/30 bg-yellow-500/10 text-yellow-600 hover:bg-yellow-500/20 dark:text-yellow-400'}"
                            title={isStrong
                              ? `Open on TMDB (match ${Math.round(tmdbMatch.confidence * 100)}%)`
                              : `Possible match (${Math.round(tmdbMatch.confidence * 100)}%) — verify`}
                          >
                            {isStrong ? "TMDB" : "Maybe"}: {tmdbMatch.title}{#if tmdbMatch.year} ({tmdbMatch.year}){/if}
                            {#if tmdbMatch.rating !== null}
                              <span class="opacity-80">★ {tmdbMatch.rating.toFixed(1)}</span>
                            {/if}
                            <ExternalLink class="h-3 w-3" />
                          </a>
                        {:else}
                          <a
                            href={tmdbSearchUrl(parsed.name, tmdbKind)}
                            target="_blank"
                            rel="noopener noreferrer"
                            class="inline-flex items-center gap-1 text-muted-foreground hover:text-foreground"
                            title="Search on TMDB"
                          >
                            Search TMDB
                            <ExternalLink class="h-3 w-3" />
                          </a>
                        {/if}

                        {#if parsed.season !== null && parsed.episode !== null}
                          <span class="rounded bg-muted px-1.5 py-0.5 text-[11px]">
                            S{String(parsed.season).padStart(2, "0")}E{String(parsed.episode).padStart(2, "0")}
                          </span>
                        {/if}
                      {:else if active === "software"}
                        <a
                          href={googleSearchUrl(parsed.name)}
                          target="_blank"
                          rel="noopener noreferrer"
                          class="inline-flex items-center gap-1 text-muted-foreground hover:text-foreground"
                          title="Search Google for this app"
                        >
                          Search: {parsed.name}
                          <ExternalLink class="h-3 w-3" />
                        </a>
                      {/if}
                    </div>
                  </div>
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
