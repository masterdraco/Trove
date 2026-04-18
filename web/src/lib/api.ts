export type ApiError = {
  status: number;
  detail: string;
};

export type UserOut = {
  id: number;
  username: string;
};

export type SetupStatus = {
  needs_setup: boolean;
};

export type ClientType = "deluge" | "transmission" | "sabnzbd" | "nzbget";
export type Protocol = "torrent" | "usenet";

export type DownloadClientOut = {
  id: number;
  name: string;
  type: ClientType;
  url: string;
  protocol: Protocol;
  default_category: string | null;
  default_save_path: string | null;
  enabled: boolean;
  last_test_at: string | null;
  last_test_ok: boolean | null;
  last_test_message: string | null;
};

export type ClientCreate = {
  name: string;
  type: ClientType;
  url: string;
  credentials: Record<string, string>;
  default_category?: string | null;
  default_save_path?: string | null;
  enabled?: boolean;
};

export type ClientTestResult = {
  ok: boolean;
  version: string | null;
  message: string | null;
  details: Record<string, unknown>;
  categories: string[];
};

export type IndexerType =
  | "newznab"
  | "torznab"
  | "cardigann"
  | "unit3d"
  | "rartracker"
  | "custom";
export type Category =
  | "movies"
  | "tv"
  | "music"
  | "books"
  | "audiobooks"
  | "comics"
  | "anime"
  | "games"
  | "software"
  | "other";

// Alias kept for readability in browse-specific call sites.
export type BrowseCategory = Category;

export type BrowseResponse = {
  category: BrowseCategory;
  hits: SearchHit[];
  indexers_used: number;
  elapsed_ms: number;
  errors: { name: string; message: string }[];
};

export type IndexerOut = {
  id: number;
  name: string;
  type: IndexerType;
  protocol: Protocol;
  base_url: string;
  enabled: boolean;
  priority: number;
  last_test_at: string | null;
  last_test_ok: boolean | null;
  last_test_message: string | null;
};

export type IndexerCreate = {
  name: string;
  type: IndexerType;
  protocol: Protocol;
  base_url: string;
  credentials: Record<string, unknown>;
  definition_yaml?: string | null;
  enabled?: boolean;
  priority?: number;
};

export type IndexerTestResult = {
  ok: boolean;
  version: string | null;
  message: string | null;
  supported_categories: Category[];
};

export type IndexerHealthOut = {
  id: number;
  name: string;
  type: IndexerType;
  protocol: Protocol;
  enabled: boolean;
  last_test_at: string | null;
  last_test_ok: boolean | null;
  last_test_message: string | null;
  events_24h: number;
  successes_24h: number;
  failures_24h: number;
  success_rate_24h: number;
  avg_elapsed_ms_24h: number | null;
  total_hits_24h: number;
  last_event_at: string | null;
  last_success_at: string | null;
  last_failure_at: string | null;
  last_error_message: string | null;
  sparkline: number[][];
};

export type NotificationProviderType =
  | "discord_webhook"
  | "discord_bot"
  | "telegram"
  | "ntfy"
  | "webhook";

export type NotificationEventKind =
  | "task.grabbed"
  | "task.upgraded"
  | "task.send_failed"
  | "task.error"
  | "download.started"
  | "download.completed"
  | "download.failed"
  | "download.removed";

export type NotificationOut = {
  id: number;
  name: string;
  type: NotificationProviderType;
  events: NotificationEventKind[];
  enabled: boolean;
  created_at: string;
  last_sent_at: string | null;
  last_sent_ok: boolean | null;
  last_sent_message: string | null;
};

export type NotificationCreate = {
  name: string;
  type: NotificationProviderType;
  config: Record<string, unknown>;
  events: NotificationEventKind[];
  enabled?: boolean;
};

export type NotificationMeta = {
  event_kinds: NotificationEventKind[];
  provider_types: NotificationProviderType[];
};

export type QualityProfile = {
  name: string;
  quality_tiers: Record<string, number>;
  source_tiers: Record<string, number>;
  codec_bonus: Record<string, number>;
  audio_bonus: Record<string, number>;
  reject_tokens: string[];
  prefer_quality: string | null;
  min_acceptable_tier: number;
};

export type QualityProfilesOut = {
  default: string;
  profiles: Record<string, QualityProfile>;
};

export type CalendarEvent = {
  date: string;
  title: string;
  kind: "movie" | "tv";
  tmdb_id: number | null;
  season: number | null;
  episode: number | null;
  episode_title: string | null;
  poster_url: string | null;
  grab_state: "pending" | "grabbed" | "missed" | "discover";
  source: "watchlist" | "tmdb";
  overview: string | null;
  rating: number | null;
};

export type CalendarResponse = {
  month: string;
  events: CalendarEvent[];
};

export type SearchHit = {
  title: string;
  protocol: Protocol;
  size: number | null;
  seeders: number | null;
  leechers: number | null;
  download_url: string | null;
  infohash: string | null;
  category: string | null;
  source: string | null;
  score: number;
  published_at: string | null;
};

export type SearchResponse = {
  query: string;
  hits: SearchHit[];
  indexers_used: number;
  elapsed_ms: number;
  errors: { name: string; message: string }[];
};

export type DiscoverItem = {
  tmdb_id: number;
  kind: "movie" | "tv";
  title: string;
  original_title: string | null;
  year: number | null;
  overview: string | null;
  poster_url: string | null;
  backdrop_url: string | null;
  rating: number | null;
  genres: string[];
  release_date: string | null;
  popularity: number | null;
};

export type WatchlistItem = {
  id: number;
  kind: string;
  title: string;
  year: number | null;
  target_quality: string | null;
  status: string;
  notes: string | null;
  added_at: string;
  tmdb_id: number | null;
  tmdb_type: string | null;
  poster_url: string | null;
  backdrop_url: string | null;
  overview: string | null;
  release_date: string | null;
  rating: number | null;
  discovery_status: string;
  discovery_task_id: number | null;
  download_count: number;
  last_download_title: string | null;
  last_download_at: string | null;
};

export type WatchlistCandidate = {
  title: string;
  protocol: "torrent" | "usenet";
  size: number | null;
  seeders: number | null;
  source: string;
  category: string | null;
  download_url: string;
  infohash: string | null;
  published_at: string | null;
  score: number;
};

export type TaskOut = {
  id: number;
  name: string;
  enabled: boolean;
  schedule_cron: string | null;
  config_yaml: string;
  last_run_at: string | null;
  last_run_status: string | null;
  last_run_accepted: number | null;
  last_run_considered: number | null;
};

export type TaskRunOut = {
  id: number;
  task_id: number;
  started_at: string;
  finished_at: string | null;
  status: string;
  considered: number;
  accepted: number;
  dry_run: boolean;
  log: string;
};

export type DownloadOut = {
  id: number;
  task_id: number;
  task_name: string;
  title: string;
  outcome: string;
  seen_at: string;
  client_id: number | null;
  client_name: string | null;
  download_status: string | null;
  download_progress: number | null;
  download_size_bytes: number | null;
  download_downloaded_bytes: number | null;
  download_eta_seconds: number | null;
  download_error_message: string | null;
  download_state_at: string | null;
  quality_score: number | null;
  quality_tier: number | null;
};

export type SeenReleaseOut = {
  id: number;
  task_id: number;
  key: string;
  title: string;
  seen_at: string;
  outcome: string;
  reason: string | null;
  client_id: number | null;
  download_status: string | null;
  quality_score: number | null;
  quality_tier: number | null;
  upgraded_from_id: number | null;
};

async function request<T>(
  path: string,
  opts: RequestInit = {}
): Promise<T> {
  const res = await fetch(path, {
    credentials: "include",
    headers: {
      "content-type": "application/json",
      ...(opts.headers ?? {})
    },
    ...opts
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      /* noop */
    }
    const err: ApiError = { status: res.status, detail };
    throw err;
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  health: () => request<{ status: string; version: string }>("/api/health"),

  authStatus: () => request<SetupStatus>("/api/auth/status"),

  setup: (username: string, password: string) =>
    request<UserOut>("/api/auth/setup", {
      method: "POST",
      body: JSON.stringify({ username, password })
    }),

  login: (username: string, password: string) =>
    request<UserOut>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password })
    }),

  logout: () => request<void>("/api/auth/logout", { method: "POST" }),

  me: () => request<UserOut>("/api/auth/me"),

  clients: {
    list: () => request<DownloadClientOut[]>("/api/clients"),

    create: (payload: ClientCreate) =>
      request<DownloadClientOut>("/api/clients", {
        method: "POST",
        body: JSON.stringify(payload)
      }),

    update: (id: number, payload: Partial<ClientCreate>) =>
      request<DownloadClientOut>(`/api/clients/${id}`, {
        method: "PATCH",
        body: JSON.stringify(payload)
      }),

    remove: (id: number) =>
      request<void>(`/api/clients/${id}`, { method: "DELETE" }),

    test: (id: number) =>
      request<ClientTestResult>(`/api/clients/${id}/test`, { method: "POST" }),

    testTransient: (payload: { type: ClientType; url: string; credentials: Record<string, string> }) =>
      request<ClientTestResult>("/api/clients/test", {
        method: "POST",
        body: JSON.stringify(payload)
      }),

    send: (
      id: number,
      payload: {
        title: string;
        download_url: string;
        category?: string | null;
        save_path?: string | null;
        paused?: boolean;
      }
    ) =>
      request<{ ok: boolean; identifier: string | null; message: string | null }>(
        `/api/clients/${id}/send`,
        { method: "POST", body: JSON.stringify(payload) }
      )
  },

  calendar: (month?: string, includeTmdb = false) => {
    const params = new URLSearchParams();
    if (month) params.set("month", month);
    if (includeTmdb) params.set("include_tmdb", "true");
    const qs = params.toString();
    return request<CalendarResponse>(`/api/calendar${qs ? `?${qs}` : ""}`);
  },

  qualityProfiles: {
    list: () => request<QualityProfilesOut>("/api/quality-profiles"),
    upsert: (name: string, payload: QualityProfile) =>
      request<QualityProfilesOut>(`/api/quality-profiles/${encodeURIComponent(name)}`, {
        method: "PUT",
        body: JSON.stringify(payload)
      }),
    remove: (name: string) =>
      request<void>(`/api/quality-profiles/${encodeURIComponent(name)}`, { method: "DELETE" }),
    setDefault: (name: string) =>
      request<QualityProfilesOut>("/api/quality-profiles/default", {
        method: "POST",
        body: JSON.stringify({ name })
      })
  },

  notifications: {
    meta: () => request<NotificationMeta>("/api/notifications/meta"),
    list: () => request<NotificationOut[]>("/api/notifications"),
    create: (payload: NotificationCreate) =>
      request<NotificationOut>("/api/notifications", {
        method: "POST",
        body: JSON.stringify(payload)
      }),
    update: (id: number, payload: Partial<NotificationCreate>) =>
      request<NotificationOut>(`/api/notifications/${id}`, {
        method: "PATCH",
        body: JSON.stringify(payload)
      }),
    remove: (id: number) =>
      request<void>(`/api/notifications/${id}`, { method: "DELETE" }),
    test: (id: number) =>
      request<{ ok: boolean; message: string | null }>(`/api/notifications/${id}/test`, {
        method: "POST"
      })
  },

  indexers: {
    list: () => request<IndexerOut[]>("/api/indexers"),
    health: () => request<IndexerHealthOut[]>("/api/indexers/health"),
    create: (payload: IndexerCreate) =>
      request<IndexerOut>("/api/indexers", {
        method: "POST",
        body: JSON.stringify(payload)
      }),
    update: (id: number, payload: Partial<IndexerCreate>) =>
      request<IndexerOut>(`/api/indexers/${id}`, {
        method: "PATCH",
        body: JSON.stringify(payload)
      }),
    remove: (id: number) => request<void>(`/api/indexers/${id}`, { method: "DELETE" }),
    test: (id: number) =>
      request<IndexerTestResult>(`/api/indexers/${id}/test`, { method: "POST" })
  },

  search: (payload: {
    query: string;
    categories?: Category[];
    protocol?: Protocol | null;
    min_seeders?: number | null;
    max_size_mb?: number | null;
    use_ai_ranking?: boolean;
  }) =>
    request<SearchResponse>("/api/search", {
      method: "POST",
      body: JSON.stringify(payload)
    }),

  browse: {
    latest: (cat: BrowseCategory, opts?: { protocol?: Protocol; limit?: number }) => {
      const params = new URLSearchParams({ cat });
      if (opts?.protocol) params.set("protocol", opts.protocol);
      if (opts?.limit) params.set("limit", String(opts.limit));
      return request<BrowseResponse>(`/api/browse/latest?${params}`);
    },
    steam: (q: string) =>
      request<{
        match: {
          appid: number;
          name: string;
          url: string;
          image: string | null;
          confidence: number;
        } | null;
      }>(`/api/browse/steam?q=${encodeURIComponent(q)}`),
    tmdb: (q: string, kind: "movie" | "tv", year?: number | null) => {
      const params = new URLSearchParams({ q, kind });
      if (year) params.set("year", String(year));
      return request<{
        match: {
          tmdb_id: number;
          kind: string;
          title: string;
          year: number | null;
          rating: number | null;
          poster_url: string | null;
          backdrop_url: string | null;
          url: string;
          confidence: number;
        } | null;
      }>(`/api/browse/tmdb?${params}`);
    }
  },

  system: {
    version: (force = false) =>
      request<{
        current: string;
        latest: string | null;
        update_available: boolean;
        source: string | null;
        release_notes: string | null;
        release_url: string | null;
        checked_at: number;
        error: string | null;
      }>(`/api/system/version${force ? "?force=true" : ""}`),
    update: () =>
      request<{ ok: boolean; message: string; log_path: string; pid: number | null }>(
        "/api/system/update",
        { method: "POST" }
      ),
    torznabInfo: () =>
      request<{ apikey: string; path: string }>("/api/system/torznab-info")
  },

  backup: {
    downloadUrl: "/api/backup",
    restore: async (file: File) => {
      const form = new FormData();
      form.append("file", file);
      const res = await fetch("/api/backup/restore", {
        method: "POST",
        credentials: "include",
        body: form
      });
      if (!res.ok) {
        let detail = res.statusText;
        try {
          const body = await res.json();
          if (typeof body?.detail === "string") detail = body.detail;
        } catch {}
        throw { status: res.status, detail };
      }
      return (await res.json()) as {
        ok: boolean;
        restored_version: string | null;
        restored_alembic: string | null;
        backup_created_at: string | null;
      };
    }
  },

  discover: {
    status: () =>
      request<{ configured: boolean }>("/api/discover/status"),
    trending: (media: "all" | "movie" | "tv" = "all", window: "day" | "week" = "week", limit = 20) =>
      request<DiscoverItem[]>(`/api/discover/trending?media=${media}&window=${window}&limit=${limit}`),
    popular: (media: "movie" | "tv" = "movie", limit = 20) =>
      request<DiscoverItem[]>(`/api/discover/popular?media=${media}&limit=${limit}`),
    upcomingMovies: (limit = 20) => request<DiscoverItem[]>(`/api/discover/upcoming/movies?limit=${limit}`),
    onAirTv: (limit = 20) => request<DiscoverItem[]>(`/api/discover/on-air/tv?limit=${limit}`),
    search: (q: string, kind: "multi" | "movie" | "tv" = "multi") =>
      request<DiscoverItem[]>(
        `/api/discover/search?q=${encodeURIComponent(q)}&kind=${kind}`
      ),
    movie: (tmdbId: number) => request<DiscoverItem>(`/api/discover/movie/${tmdbId}`),
    tv: (tmdbId: number) => request<DiscoverItem>(`/api/discover/tv/${tmdbId}`),
    test: () =>
      request<{ ok: boolean; message?: string; image_base?: string }>(
        "/api/discover/test",
        { method: "POST" }
      )
  },

  docs: {
    list: () =>
      request<{ slug: string; title: string; order: number; description: string }[]>(
        "/api/docs"
      ),
    get: (slug: string) =>
      request<{
        slug: string;
        title: string;
        order: number;
        description: string;
        markdown: string;
      }>(`/api/docs/${slug}`)
  },

  appSettings: {
    list: () =>
      request<
        {
          key: string;
          type: string;
          label: string;
          description: string;
          group: string;
          default: unknown;
          value: unknown;
          min_value: number | null;
          max_value: number | null;
        }[]
      >("/api/settings"),
    update: (values: Record<string, unknown>) =>
      request<
        {
          key: string;
          type: string;
          label: string;
          description: string;
          group: string;
          default: unknown;
          value: unknown;
          min_value: number | null;
          max_value: number | null;
        }[]
      >("/api/settings", {
        method: "PATCH",
        body: JSON.stringify({ values })
      })
  },

  feeds: {
    list: () =>
      request<
        {
          id: number;
          name: string;
          url: string;
          enabled: boolean;
          poll_interval_seconds: number;
          retention_days: number;
          protocol_hint: string;
          category_hint: string | null;
          last_polled_at: string | null;
          last_poll_status: string | null;
          last_poll_message: string | null;
          total_items: number;
          last_new_items: number;
        }[]
      >("/api/feeds"),
    create: (payload: {
      name: string;
      url: string;
      enabled?: boolean;
      poll_interval_seconds?: number;
      retention_days?: number;
      protocol_hint?: "torrent" | "usenet";
      category_hint?: string | null;
      credentials?: Record<string, unknown> | null;
    }) =>
      request<{ id: number }>("/api/feeds", {
        method: "POST",
        body: JSON.stringify(payload)
      }),
    update: (
      id: number,
      payload: {
        name?: string;
        url?: string;
        enabled?: boolean;
        poll_interval_seconds?: number;
        retention_days?: number;
        protocol_hint?: "torrent" | "usenet";
        category_hint?: string | null;
        credentials?: Record<string, unknown> | null;
      }
    ) =>
      request<{ id: number }>(`/api/feeds/${id}`, {
        method: "PATCH",
        body: JSON.stringify(payload)
      }),
    remove: (id: number) => request<void>(`/api/feeds/${id}`, { method: "DELETE" }),
    preview: (url: string, credentials?: Record<string, unknown> | null) =>
      request<
        {
          title: string;
          download_url: string;
          size: number | null;
          seeders: number | null;
          leechers: number | null;
          infohash: string | null;
          category: string | null;
          published_at: string | null;
        }[]
      >("/api/feeds/preview", {
        method: "POST",
        body: JSON.stringify({ url, credentials })
      }),
    poll: (id: number) =>
      request<{ ok: boolean; new_items: number; total: number | null; error: string | null }>(
        `/api/feeds/${id}/poll`,
        { method: "POST" }
      ),
    items: (id: number, q?: string) => {
      const params = new URLSearchParams();
      if (q) params.set("q", q);
      return request<
        {
          id: number;
          feed_id: number;
          title: string;
          download_url: string;
          size: number | null;
          seeders: number | null;
          leechers: number | null;
          category: string | null;
          published_at: string | null;
          fetched_at: string;
        }[]
      >(`/api/feeds/${id}/items?${params}`);
    }
  },

  watchlist: {
    list: () => request<WatchlistItem[]>("/api/watchlist"),
    create: (payload: {
      kind: "series" | "movie";
      title: string;
      year?: number | null;
      target_quality?: string | null;
      notes?: string | null;
      tmdb_id?: number | null;
      tmdb_type?: "movie" | "tv" | null;
      poster_path?: string | null;
      backdrop_path?: string | null;
      overview?: string | null;
      release_date?: string | null;
      rating?: number | null;
    }) =>
      request<WatchlistItem>("/api/watchlist", {
        method: "POST",
        body: JSON.stringify(payload)
      }),
    remove: (id: number) => request<void>(`/api/watchlist/${id}`, { method: "DELETE" }),
    update: (
      id: number,
      payload: { status?: string; title?: string; notes?: string | null }
    ) =>
      request<void>(`/api/watchlist/${id}`, {
        method: "PATCH",
        body: JSON.stringify(payload)
      }),
    promote: (id: number) =>
      request<{
        ok: boolean;
        watchlist_id: number;
        task_id: number | null;
        message: string;
      }>(`/api/watchlist/${id}/promote`, { method: "POST" }),
    unpromote: (id: number) =>
      request<WatchlistItem>(`/api/watchlist/${id}/unpromote`, { method: "POST" }),
    candidates: (id: number) =>
      request<WatchlistCandidate[]>(`/api/watchlist/${id}/candidates`),
    grab: (id: number, payload: {
      title: string;
      protocol: "torrent" | "usenet";
      download_url: string;
      size?: number | null;
      infohash?: string | null;
    }) =>
      request<{ ok: boolean; client: string | null; message: string }>(
        `/api/watchlist/${id}/grab`,
        { method: "POST", body: JSON.stringify(payload) }
      )
  },

  ai: {
    status: () =>
      request<{ enabled: boolean; endpoint: string; model: string }>("/api/ai/status"),
    models: () =>
      request<
        {
          name: string;
          size: number | null;
          parameter_size: string | null;
          family: string | null;
        }[]
      >("/api/ai/models"),
    chat: (prompt: string, system?: string) =>
      request<{ response: string }>("/api/ai/chat", {
        method: "POST",
        body: JSON.stringify({ prompt, system })
      }),
    test: () => request<{ response: string }>("/api/ai/test", { method: "POST" }),
    agentPropose: (prompt: string) =>
      request<{
        intent: string;
        description: string;
        preview: Record<string, unknown>;
        params: Record<string, unknown>;
        requires_confirmation: boolean;
        message: string | null;
        warnings: string[];
      }>("/api/ai/agent/propose", {
        method: "POST",
        body: JSON.stringify({ prompt })
      }),
    agentExecute: (intent: string, params: Record<string, unknown>) =>
      request<{
        ok: boolean;
        kind: string;
        resource_id: number | null;
        message: string;
      }>("/api/ai/agent/execute", {
        method: "POST",
        body: JSON.stringify({ intent, params })
      })
  },

  downloads: {
    list: (status?: string, limit = 50) => {
      const params = new URLSearchParams();
      if (status) params.set("status", status);
      if (limit !== 50) params.set("limit", String(limit));
      const qs = params.toString();
      return request<DownloadOut[]>(`/api/downloads${qs ? `?${qs}` : ""}`);
    }
  },

  tasks: {
    list: () => request<TaskOut[]>("/api/tasks"),
    create: (payload: {
      name: string;
      enabled?: boolean;
      schedule_cron?: string | null;
      config_yaml: string;
    }) =>
      request<TaskOut>("/api/tasks", {
        method: "POST",
        body: JSON.stringify(payload)
      }),
    update: (
      id: number,
      payload: {
        name?: string;
        enabled?: boolean;
        schedule_cron?: string | null;
        config_yaml?: string;
      }
    ) =>
      request<TaskOut>(`/api/tasks/${id}`, {
        method: "PATCH",
        body: JSON.stringify(payload)
      }),
    remove: (id: number) => request<void>(`/api/tasks/${id}`, { method: "DELETE" }),
    run: (id: number, dryRun = false) =>
      request<TaskRunOut>(`/api/tasks/${id}/run?dry_run=${dryRun}`, { method: "POST" }),
    runs: (id: number) => request<TaskRunOut[]>(`/api/tasks/${id}/runs`),
    seenReleases: (id: number, outcome?: string) => {
      const params = new URLSearchParams();
      if (outcome) params.set("outcome", outcome);
      const qs = params.toString();
      return request<SeenReleaseOut[]>(`/api/tasks/${id}/seen-releases${qs ? `?${qs}` : ""}`);
    }
  }
};
