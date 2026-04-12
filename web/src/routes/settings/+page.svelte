<script lang="ts">
  import { onMount } from "svelte";
  import { api } from "$lib/api";
  import NotificationsPanel from "./NotificationsPanel.svelte";
  import { goto } from "$app/navigation";
  import {
    Sparkles,
    Globe,
    CheckCircle2,
    XCircle,
    Loader2,
    Wand2,
    SlidersHorizontal,
    Save,
    Download,
    Upload,
    Archive,
    AlertTriangle,
    TrendingUp,
    ExternalLink,
    RefreshCw,
    Rocket,
    Copy,
    Eye,
    EyeOff,
    Info
  } from "lucide-svelte";

  type AppSetting = Awaited<ReturnType<typeof api.appSettings.list>>[number];

  type VersionInfo = Awaited<ReturnType<typeof api.system.version>>;

  let aiStatus = $state<{ enabled: boolean; endpoint: string; model: string } | null>(null);
  let version = $state<string | null>(null);
  let versionInfo = $state<VersionInfo | null>(null);
  let versionChecking = $state(false);
  let testing = $state(false);
  let testResult = $state<{ ok: boolean; message: string } | null>(null);
  let availableModels = $state<
    { name: string; size: number | null; parameter_size: string | null; family: string | null }[]
  >([]);
  let loadingModels = $state(false);
  let modelsError = $state<string | null>(null);

  let settings = $state<AppSetting[]>([]);
  let draft = $state<Record<string, unknown>>({});
  let settingsLoading = $state(true);
  let settingsSaving = $state(false);
  let settingsError = $state<string | null>(null);
  let settingsSaved = $state(false);

  async function loadSettings() {
    settingsLoading = true;
    try {
      settings = await api.appSettings.list();
      draft = Object.fromEntries(settings.map((s) => [s.key, s.value]));
    } finally {
      settingsLoading = false;
    }
  }

  async function loadVersion(force = false) {
    versionChecking = true;
    try {
      versionInfo = await api.system.version(force);
      version = versionInfo.current;
    } catch (e) {
      version = null;
      versionInfo = null;
    } finally {
      versionChecking = false;
    }
  }

  let updating = $state(false);
  let updateStage = $state<string>("");
  let updateError = $state<string | null>(null);
  let torznabInfo = $state<{ apikey: string; path: string } | null>(null);
  let showApikey = $state(false);

  async function runUpdate() {
    if (
      !confirm(
        "Pull latest code from GitHub and restart Trove? The server will be unreachable for ~60–90 seconds while it rebuilds."
      )
    )
      return;
    updating = true;
    updateError = null;
    updateStage = "Starting update script…";
    const startingVersion = versionInfo?.current;
    try {
      const r = await api.system.update();
      if (!r.ok) {
        updateError = r.message;
        updating = false;
        return;
      }
      // Poll /api/health every 2s with cache-busting. We succeed the
      // moment the reported version differs from the starting one —
      // regardless of whether we observed the down-window (restart may
      // be faster than our poll interval).
      updateStage = "Server is rebuilding — this takes 1–2 minutes…";
      const deadline = Date.now() + 300_000;
      let serverWentDown = false;
      while (Date.now() < deadline) {
        await new Promise((r) => setTimeout(r, 2000));
        try {
          const res = await fetch(`/api/health?t=${Date.now()}`, {
            cache: "no-store",
            credentials: "include"
          });
          if (!res.ok) throw new Error(String(res.status));
          const h = (await res.json()) as { status: string; version: string };
          if (h.version !== startingVersion) {
            updateStage = `Updated to v${h.version}. Reloading…`;
            updating = false;
            setTimeout(() => window.location.reload(), 1200);
            return;
          }
          updateStage = serverWentDown
            ? `Server came back but still v${h.version}. Waiting…`
            : "Pulling code and building…";
        } catch {
          serverWentDown = true;
          updateStage = "Server is restarting…";
        }
      }
      updateError = "Update timed out after 5 minutes. Check /tmp/trove-update.log on the server.";
      updating = false;
    } catch (e) {
      updateError = (e as { detail?: string }).detail ?? "Update failed";
      updating = false;
    }
  }

  onMount(async () => {
    try {
      aiStatus = await api.ai.status();
    } catch {
      aiStatus = null;
    }
    try {
      torznabInfo = await api.system.torznabInfo();
    } catch {
      torznabInfo = null;
    }
    await loadVersion();
    await loadSettings();
  });

  function isDirty(): boolean {
    return settings.some((s) => draft[s.key] !== s.value);
  }

  async function saveSettings() {
    settingsSaving = true;
    settingsError = null;
    settingsSaved = false;
    try {
      const updated = await api.appSettings.update(draft);
      settings = updated;
      draft = Object.fromEntries(updated.map((s) => [s.key, s.value]));
      settingsSaved = true;
      setTimeout(() => (settingsSaved = false), 2500);
    } catch (e) {
      settingsError = (e as { detail?: unknown }).detail
        ? JSON.stringify((e as { detail: unknown }).detail)
        : "Failed to save";
    } finally {
      settingsSaving = false;
    }
  }

  function resetDraft(key: string) {
    const spec = settings.find((s) => s.key === key);
    if (spec) draft[key] = spec.default;
  }

  function groupedSettings(): Record<string, AppSetting[]> {
    const grouped: Record<string, AppSetting[]> = {};
    for (const s of settings) {
      // AI and TMDB settings get their own dedicated panels below
      if (s.group === "ai" || s.group === "tmdb") continue;
      (grouped[s.group] ??= []).push(s);
    }
    return grouped;
  }

  function groupLabel(group: string): string {
    return (
      {
        rss: "RSS Feeds",
        search: "Search",
        ai: "AI",
        tmdb: "TMDB",
        general: "General"
      }[group] ?? group
    );
  }

  let tmdbTesting = $state(false);
  let tmdbResult = $state<{ ok: boolean; message: string } | null>(null);

  async function runTmdbTest() {
    // Save any pending TMDB changes first so the test uses the new token
    if (draft["tmdb.api_token"] !== (settings.find((s) => s.key === "tmdb.api_token")?.value ?? "")) {
      try {
        await api.appSettings.update({ "tmdb.api_token": draft["tmdb.api_token"] });
        await loadSettings();
      } catch (e) {
        tmdbResult = {
          ok: false,
          message: (e as { detail?: string }).detail ?? "failed to save token"
        };
        return;
      }
    }
    tmdbTesting = true;
    tmdbResult = null;
    try {
      const r = await api.discover.test();
      tmdbResult = {
        ok: r.ok,
        message: r.ok ? `Connected · image base: ${r.image_base ?? "default"}` : (r.message ?? "failed")
      };
    } catch (e) {
      tmdbResult = { ok: false, message: (e as { detail?: string }).detail ?? "failed" };
    } finally {
      tmdbTesting = false;
    }
  }

  let restoreFile = $state<File | null>(null);
  let restoring = $state(false);
  let restoreMsg = $state<{ ok: boolean; text: string } | null>(null);

  function pickRestoreFile(e: Event) {
    const target = e.currentTarget as HTMLInputElement;
    restoreFile = target.files?.[0] ?? null;
    restoreMsg = null;
  }

  async function doRestore() {
    if (!restoreFile) return;
    if (
      !confirm(
        `Restore from ${restoreFile.name}? This will OVERWRITE your current database and session secret. The current files are backed up to config/.pre-restore/ first, but this is still a destructive operation.`
      )
    )
      return;
    restoring = true;
    restoreMsg = null;
    try {
      const result = await api.backup.restore(restoreFile);
      restoreMsg = {
        ok: true,
        text: `Restored backup from ${result.backup_created_at ?? "unknown time"} (Trove ${result.restored_version ?? "?"}). Reload the page to see your restored data.`
      };
      restoreFile = null;
    } catch (e) {
      const err = e as { detail?: string };
      restoreMsg = { ok: false, text: err.detail ?? "restore failed" };
    } finally {
      restoring = false;
    }
  }

  function runOnboarding() {
    try {
      localStorage.removeItem("trove_onboarding_dismissed");
    } catch {}
    goto("/onboarding");
  }

  async function runAiTest() {
    testing = true;
    testResult = null;
    try {
      const r = await api.ai.test();
      testResult = { ok: true, message: r.response.trim() || "(empty)" };
    } catch (e) {
      testResult = { ok: false, message: (e as { detail?: string }).detail ?? "failed" };
    } finally {
      testing = false;
    }
  }

  async function loadOllamaModels() {
    // Save the current endpoint first so /api/ai/models uses the right URL
    if (draft["ai.endpoint"] !== (settings.find((s) => s.key === "ai.endpoint")?.value ?? "")) {
      try {
        await api.appSettings.update({ "ai.endpoint": draft["ai.endpoint"] });
        await loadSettings();
      } catch (e) {
        modelsError = (e as { detail?: string }).detail ?? "failed to save endpoint";
        return;
      }
    }
    loadingModels = true;
    modelsError = null;
    try {
      const models = await api.ai.models();
      availableModels = models;
    } catch (e) {
      modelsError = (e as { detail?: string }).detail ?? "failed";
    } finally {
      loadingModels = false;
    }
  }

  function pickModel(name: string) {
    // LiteLLM needs an 'ollama/' prefix for Ollama models
    const full = name.startsWith("ollama/") ? name : `ollama/${name}`;
    draft["ai.model"] = full;
  }

  function formatBytes(bytes: number | null): string {
    if (!bytes) return "";
    const gb = bytes / 1024 / 1024 / 1024;
    return `${gb.toFixed(1)} GB`;
  }
</script>

<div class="max-w-3xl space-y-6">
  <div>
    <h2 class="text-xl font-semibold">Settings</h2>
    <p class="mt-1 text-sm text-muted-foreground">Server configuration and integrations.</p>
  </div>

  <div class="rounded-xl border border-border bg-card p-5">
    <div class="flex items-center justify-between">
      <h3 class="flex items-center gap-2 text-base font-semibold">
        <SlidersHorizontal class="h-4 w-4 text-primary" /> Defaults
      </h3>
      <div class="flex items-center gap-2">
        {#if settingsSaved}
          <span class="text-xs text-green-600">Saved</span>
        {/if}
        <button
          class="inline-flex items-center gap-1 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-60"
          onclick={saveSettings}
          disabled={settingsSaving || !isDirty()}
        >
          {#if settingsSaving}
            <Loader2 class="h-3.5 w-3.5 animate-spin" />
          {:else}
            <Save class="h-3.5 w-3.5" />
          {/if}
          Save
        </button>
      </div>
    </div>
    <p class="mt-1 text-sm text-muted-foreground">
      Global defaults applied when creating new feeds, searches, or AI calls. Individual
      resources can still override these.
    </p>

    {#if settingsLoading}
      <div class="mt-4 text-sm text-muted-foreground">Loading…</div>
    {:else}
      <div class="mt-5 space-y-5">
        {#each Object.entries(groupedSettings()) as [group, specs]}
          <div>
            <div class="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              {groupLabel(group)}
            </div>
            <div class="space-y-3">
              {#each specs as spec (spec.key)}
                <div class="rounded-lg border border-border bg-background p-3">
                  <div class="flex items-start justify-between gap-3">
                    <div class="flex-1">
                      <label class="block text-sm font-medium" for={`setting-${spec.key}`}>
                        {spec.label}
                      </label>
                      <p class="mt-0.5 text-xs text-muted-foreground">{spec.description}</p>
                      <div class="mt-0.5 font-mono text-[10px] text-muted-foreground">
                        {spec.key}
                      </div>
                    </div>
                    <div class="flex flex-col items-end gap-1">
                      {#if spec.type === "int"}
                        <input
                          id={`setting-${spec.key}`}
                          type="number"
                          min={spec.min_value ?? undefined}
                          max={spec.max_value ?? undefined}
                          value={draft[spec.key] as number}
                          oninput={(e) => {
                            const val = (e.currentTarget as HTMLInputElement).valueAsNumber;
                            if (!Number.isNaN(val)) draft[spec.key] = val;
                          }}
                          class="w-28 rounded-md border border-input bg-background px-3 py-1.5 text-right font-mono text-sm outline-none ring-ring focus:ring-2"
                        />
                      {:else if spec.type === "bool"}
                        <input
                          id={`setting-${spec.key}`}
                          type="checkbox"
                          checked={draft[spec.key] as boolean}
                          onchange={(e) => {
                            draft[spec.key] = (e.currentTarget as HTMLInputElement).checked;
                          }}
                          class="h-4 w-4"
                        />
                      {:else}
                        <input
                          id={`setting-${spec.key}`}
                          type="text"
                          value={draft[spec.key] as string}
                          oninput={(e) => {
                            draft[spec.key] = (e.currentTarget as HTMLInputElement).value;
                          }}
                          class="w-48 rounded-md border border-input bg-background px-3 py-1.5 text-sm outline-none ring-ring focus:ring-2"
                        />
                      {/if}
                      <button
                        type="button"
                        class="text-[10px] text-muted-foreground hover:text-foreground"
                        onclick={() => resetDraft(spec.key)}
                      >
                        reset to {String(spec.default)}
                      </button>
                    </div>
                  </div>
                </div>
              {/each}
            </div>
          </div>
        {/each}
      </div>
      {#if settingsError}
        <div class="mt-3 rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {settingsError}
        </div>
      {/if}
    {/if}
  </div>

  <div class="rounded-xl border border-border bg-card p-5">
    <div class="flex items-center justify-between">
      <h3 class="flex items-center gap-2 text-base font-semibold">
        <Wand2 class="h-4 w-4 text-primary" /> Onboarding
      </h3>
      <button
        class="inline-flex items-center gap-1 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90"
        onclick={runOnboarding}
      >
        <Wand2 class="h-3.5 w-3.5" />
        Run wizard
      </button>
    </div>
    <p class="mt-2 text-sm text-muted-foreground">
      Re-run the guided setup for adding clients, indexers and checking the AI connection.
    </p>
  </div>

  <div class="surface p-5">
    <div class="flex items-start justify-between">
      <h3 class="flex items-center gap-2 text-base font-semibold">
        <Globe class="h-4 w-4" /> System
      </h3>
      <button
        class="btn-secondary"
        onclick={() => loadVersion(true)}
        disabled={versionChecking}
      >
        {#if versionChecking}
          <Loader2 class="h-3.5 w-3.5 animate-spin" />
        {:else}
          <RefreshCw class="h-3.5 w-3.5" />
        {/if}
        Check for updates
      </button>
    </div>

    <dl class="mt-4 grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
      <dt class="text-muted-foreground">Installed</dt>
      <dd class="flex items-center gap-2 font-mono">
        v{version ?? "?"}
        {#if versionInfo?.update_available}
          <span class="chip-primary inline-flex items-center gap-1">
            <Rocket class="h-3 w-3" />
            Update available
          </span>
        {:else if versionInfo && versionInfo.latest && !versionInfo.update_available}
          <span class="chip-success inline-flex items-center gap-1">
            <CheckCircle2 class="h-3 w-3" />
            Up to date
          </span>
        {/if}
      </dd>

      {#if versionInfo?.latest}
        <dt class="text-muted-foreground">Latest on GitHub</dt>
        <dd class="font-mono">
          v{versionInfo.latest}
          {#if versionInfo.source === "github_releases"}
            <span class="ml-2 text-[10px] text-muted-foreground">(release)</span>
          {:else if versionInfo.source === "github_pyproject"}
            <span class="ml-2 text-[10px] text-muted-foreground">(pyproject main)</span>
          {/if}
        </dd>
      {/if}

      <dt class="text-muted-foreground">Web origin</dt>
      <dd class="font-mono text-xs">{location.origin}</dd>
    </dl>

    {#if versionInfo?.error}
      <div class="mt-4 rounded-xl border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-300">
        <AlertTriangle class="inline h-3 w-3" /> {versionInfo.error}
      </div>
    {/if}

    {#if versionInfo?.update_available}
      <div class="mt-4 rounded-xl border border-primary/30 bg-primary/10 p-4">
        <div class="flex items-start gap-3">
          <Rocket class="mt-0.5 h-4 w-4 text-primary" />
          <div class="flex-1">
            <div class="text-sm font-semibold">
              Trove v{versionInfo.latest} is available
            </div>
            <div class="mt-1 text-xs text-muted-foreground">
              You're running v{versionInfo.current}. Your database and session secret are
              preserved across upgrades.
            </div>

            <div class="mt-4 flex flex-wrap gap-2">
              <button
                class="btn-primary"
                onclick={runUpdate}
                disabled={updating}
              >
                {#if updating}
                  <Loader2 class="h-3.5 w-3.5 animate-spin" />
                {:else}
                  <Rocket class="h-3.5 w-3.5" />
                {/if}
                Update now
              </button>
              {#if versionInfo.release_url}
                <a
                  href={versionInfo.release_url}
                  target="_blank"
                  rel="noopener"
                  class="btn-secondary"
                >
                  <ExternalLink class="h-3.5 w-3.5" />
                  View on GitHub
                </a>
              {/if}
            </div>

            {#if updating || updateStage}
              <div class="mt-3 rounded-xl border border-border/50 bg-background/60 px-3 py-2 text-xs">
                <div class="flex items-center gap-2 font-mono">
                  {#if updating}
                    <Loader2 class="h-3 w-3 animate-spin text-primary" />
                  {:else}
                    <CheckCircle2 class="h-3 w-3 text-success" />
                  {/if}
                  {updateStage}
                </div>
              </div>
            {/if}
            {#if updateError}
              <div class="mt-3 rounded-xl border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive">
                <XCircle class="inline h-3 w-3" /> {updateError}
              </div>
            {/if}

            {#if versionInfo.release_notes}
              <details class="mt-4">
                <summary class="cursor-pointer text-xs text-primary hover:underline">
                  Release notes
                </summary>
                <pre class="mt-2 max-h-60 overflow-y-auto whitespace-pre-wrap rounded-md bg-background/50 p-3 text-[11px] text-foreground/80">{versionInfo.release_notes}</pre>
              </details>
            {/if}
          </div>
        </div>
      </div>
    {/if}
  </div>

  <div class="surface relative overflow-hidden p-6">
    <div class="absolute inset-0 bg-gradient-to-br from-fuchsia-500/10 via-transparent to-primary/10"></div>
    <div class="relative">
      <div class="flex items-start justify-between">
        <div class="flex items-center gap-3">
          <div
            class="flex h-10 w-10 items-center justify-center rounded-xl glow-primary"
            style="background-image: linear-gradient(135deg, hsl(300 85% 60%) 0%, hsl(var(--primary)) 100%);"
          >
            <Sparkles class="h-5 w-5 text-white" />
          </div>
          <div>
            <h3 class="text-base font-semibold">AI Assistant</h3>
            <p class="text-xs text-muted-foreground">Local LLM via Ollama + litellm</p>
          </div>
        </div>
        <button
          class="btn-secondary"
          onclick={runAiTest}
          disabled={testing}
        >
          {#if testing}
            <Loader2 class="h-3.5 w-3.5 animate-spin" />
          {:else if testResult?.ok}
            <CheckCircle2 class="h-3.5 w-3.5 text-success" />
          {:else if testResult && !testResult.ok}
            <XCircle class="h-3.5 w-3.5 text-destructive" />
          {/if}
          Test connection
        </button>
      </div>

      {#if testResult}
        <div
          class="mt-4 rounded-xl border px-3 py-2 text-xs {testResult.ok
            ? 'border-success/30 bg-success/10 text-success'
            : 'border-destructive/30 bg-destructive/10 text-destructive'}"
        >
          {testResult.message}
        </div>
      {/if}

      {#if !settingsLoading}
        {@const endpointSpec = settings.find((s) => s.key === "ai.endpoint")}
        {@const modelSpec = settings.find((s) => s.key === "ai.model")}
        {@const enabledSpec = settings.find((s) => s.key === "ai.enabled")}
        {@const tempSpec = settings.find((s) => s.key === "ai.default_temperature")}

        <div class="mt-5 grid gap-4">
          <!-- Enabled toggle -->
          {#if enabledSpec}
            <label class="flex items-center gap-3 rounded-xl border border-border/60 bg-background/40 px-4 py-3">
              <input
                type="checkbox"
                checked={draft["ai.enabled"] as boolean}
                onchange={(e) => (draft["ai.enabled"] = (e.currentTarget as HTMLInputElement).checked)}
                class="h-4 w-4 rounded"
              />
              <div class="flex-1">
                <div class="text-sm font-medium">Enabled</div>
                <div class="text-xs text-muted-foreground">{enabledSpec.description}</div>
              </div>
            </label>
          {/if}

          <!-- Endpoint -->
          {#if endpointSpec}
            <div>
              <label class="mb-1.5 block text-sm font-medium" for="ai-endpoint">
                Endpoint URL
              </label>
              <input
                id="ai-endpoint"
                type="url"
                value={draft["ai.endpoint"] as string}
                oninput={(e) => (draft["ai.endpoint"] = (e.currentTarget as HTMLInputElement).value)}
                class="input-base font-mono text-xs"
                placeholder="http://localhost:11434"
              />
              <div class="mt-1 text-xs text-muted-foreground">{endpointSpec.description}</div>
            </div>
          {/if}

          <!-- Model with picker -->
          {#if modelSpec}
            <div>
              <div class="mb-1.5 flex items-center justify-between">
                <label class="text-sm font-medium" for="ai-model">Model</label>
                <button
                  type="button"
                  class="btn-ghost"
                  onclick={loadOllamaModels}
                  disabled={loadingModels}
                >
                  {#if loadingModels}
                    <Loader2 class="h-3 w-3 animate-spin" />
                  {/if}
                  {availableModels.length > 0 ? "Reload models" : "Load available models"}
                </button>
              </div>
              <input
                id="ai-model"
                type="text"
                value={draft["ai.model"] as string}
                oninput={(e) => (draft["ai.model"] = (e.currentTarget as HTMLInputElement).value)}
                class="input-base font-mono text-xs"
                placeholder="ollama/gemma4:latest"
              />
              <div class="mt-1 text-xs text-muted-foreground">{modelSpec.description}</div>

              {#if modelsError}
                <div class="mt-2 rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive">
                  {modelsError}
                </div>
              {/if}

              {#if availableModels.length > 0}
                <div class="mt-3 space-y-1">
                  <div class="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                    Available on server ({availableModels.length})
                  </div>
                  <div class="grid gap-1.5 sm:grid-cols-2">
                    {#each availableModels as m}
                      {@const fullName = `ollama/${m.name}`}
                      {@const selected = draft["ai.model"] === fullName}
                      <button
                        type="button"
                        class="flex items-center justify-between rounded-lg border px-3 py-2 text-left text-xs transition-colors {selected
                          ? 'border-primary/60 bg-primary/10'
                          : 'border-border/60 bg-background/40 hover:bg-card hover:border-border'}"
                        onclick={() => pickModel(m.name)}
                      >
                        <div class="min-w-0">
                          <div class="truncate font-mono font-medium {selected ? 'text-primary' : ''}">
                            {m.name}
                          </div>
                          <div class="truncate text-[10px] text-muted-foreground">
                            {m.parameter_size ?? ""}
                            {m.family ? `· ${m.family}` : ""}
                            {m.size ? `· ${formatBytes(m.size)}` : ""}
                          </div>
                        </div>
                        {#if selected}
                          <CheckCircle2 class="h-3.5 w-3.5 shrink-0 text-primary" />
                        {/if}
                      </button>
                    {/each}
                  </div>
                </div>
              {/if}
            </div>
          {/if}

          <!-- Temperature -->
          {#if tempSpec}
            <div>
              <label class="mb-1.5 block text-sm font-medium" for="ai-temp">
                Temperature: {((Number(draft["ai.default_temperature"]) || 0) / 100).toFixed(2)}
              </label>
              <input
                id="ai-temp"
                type="range"
                min="0"
                max="100"
                value={draft["ai.default_temperature"] as number}
                oninput={(e) => {
                  draft["ai.default_temperature"] = (e.currentTarget as HTMLInputElement).valueAsNumber;
                }}
                class="w-full accent-primary"
              />
              <div class="flex justify-between text-[10px] text-muted-foreground">
                <span>0.00 — focused</span>
                <span>0.50 — balanced</span>
                <span>1.00 — creative</span>
              </div>
            </div>
          {/if}
        </div>

        <div class="mt-5 flex items-center justify-between">
          <div class="text-xs text-muted-foreground">
            Changes apply after clicking Save in the Defaults panel above.
          </div>
          <button
            class="btn-primary"
            onclick={saveSettings}
            disabled={settingsSaving || !isDirty()}
          >
            {#if settingsSaving}
              <Loader2 class="h-3.5 w-3.5 animate-spin" />
            {:else}
              <Save class="h-3.5 w-3.5" />
            {/if}
            Save AI settings
          </button>
        </div>
      {/if}
    </div>
  </div>

  <div class="surface relative overflow-hidden p-6">
    <div class="absolute inset-0 bg-gradient-to-br from-rose-500/10 via-transparent to-primary/10"></div>
    <div class="relative">
      <div class="flex items-start justify-between">
        <div class="flex items-center gap-3">
          <div class="flex h-10 w-10 items-center justify-center rounded-xl bg-rose-500/20 text-rose-400">
            <TrendingUp class="h-5 w-5" />
          </div>
          <div>
            <h3 class="text-base font-semibold">TMDB (Discover)</h3>
            <p class="text-xs text-muted-foreground">
              Powers the Discover page and poster-rich watchlist.
            </p>
          </div>
        </div>
        <button class="btn-secondary" onclick={runTmdbTest} disabled={tmdbTesting}>
          {#if tmdbTesting}
            <Loader2 class="h-3.5 w-3.5 animate-spin" />
          {:else if tmdbResult?.ok}
            <CheckCircle2 class="h-3.5 w-3.5 text-success" />
          {:else if tmdbResult && !tmdbResult.ok}
            <XCircle class="h-3.5 w-3.5 text-destructive" />
          {/if}
          Test connection
        </button>
      </div>

      {#if tmdbResult}
        <div
          class="mt-4 rounded-xl border px-3 py-2 text-xs {tmdbResult.ok
            ? 'border-success/30 bg-success/10 text-success'
            : 'border-destructive/30 bg-destructive/10 text-destructive'}"
        >
          {tmdbResult.message}
        </div>
      {/if}

      {#if !settingsLoading}
        {@const tokenSpec = settings.find((s) => s.key === "tmdb.api_token")}
        {#if tokenSpec}
          <div class="mt-5 space-y-3">
            <label class="block">
              <span class="mb-1.5 block text-sm font-medium">API read token</span>
              <input
                type="password"
                value={(draft["tmdb.api_token"] as string) ?? ""}
                oninput={(e) => (draft["tmdb.api_token"] = (e.currentTarget as HTMLInputElement).value)}
                placeholder="eyJhbGciOi..."
                class="input-base font-mono text-xs"
              />
              <div class="mt-1 flex items-center gap-1 text-xs text-muted-foreground">
                Get a free token at
                <a
                  href="https://www.themoviedb.org/settings/api"
                  target="_blank"
                  rel="noopener"
                  class="inline-flex items-center gap-0.5 text-primary hover:underline"
                >
                  themoviedb.org/settings/api <ExternalLink class="h-2.5 w-2.5" />
                </a>
                — look for "API Read Access Token" (v4).
              </div>
            </label>
          </div>

          <div class="mt-4 flex items-center justify-between">
            <div class="text-xs text-muted-foreground">
              Leave blank to disable Discover.
            </div>
            <button
              class="btn-primary"
              onclick={saveSettings}
              disabled={settingsSaving || !isDirty()}
            >
              {#if settingsSaving}
                <Loader2 class="h-3.5 w-3.5 animate-spin" />
              {:else}
                <Save class="h-3.5 w-3.5" />
              {/if}
              Save TMDB settings
            </button>
          </div>
        {/if}
      {/if}
    </div>
  </div>

  <div class="rounded-xl border border-border bg-card p-5">
    <h3 class="text-base font-semibold">Torznab export</h3>
    <p class="mt-2 text-sm text-muted-foreground">
      Point Sonarr/Radarr/Lidarr at the URL below. Keep the apikey secret — it's derived from
      your session secret and grants anonymous search access.
    </p>
    {#if torznabInfo}
      {@const baseUrl = `${location.origin}${torznabInfo.path}?apikey=${torznabInfo.apikey}`}
      <div class="mt-4 space-y-3">
        <div>
          <span class="block text-xs font-semibold uppercase tracking-wide text-muted-foreground">Sonarr / Radarr URL (caps)</span>
          <div class="mt-1 flex gap-2">
            <input
              readonly
              value={`${baseUrl}&t=caps`}
              class="w-full rounded-md border border-border bg-muted/40 px-3 py-2 font-mono text-xs"
              onclick={(e) => (e.currentTarget as HTMLInputElement).select()}
            />
            <button
              class="btn-secondary shrink-0"
              onclick={() => navigator.clipboard.writeText(`${baseUrl}&t=caps`)}
              title="Copy"
            >
              <Copy class="h-3.5 w-3.5" />
            </button>
          </div>
        </div>
        <div>
          <span class="block text-xs font-semibold uppercase tracking-wide text-muted-foreground">Example search</span>
          <div class="mt-1 flex gap-2">
            <input
              readonly
              value={`${baseUrl}&t=search&q=ubuntu`}
              class="w-full rounded-md border border-border bg-muted/40 px-3 py-2 font-mono text-xs"
              onclick={(e) => (e.currentTarget as HTMLInputElement).select()}
            />
            <button
              class="btn-secondary shrink-0"
              onclick={() => navigator.clipboard.writeText(`${baseUrl}&t=search&q=ubuntu`)}
              title="Copy"
            >
              <Copy class="h-3.5 w-3.5" />
            </button>
          </div>
        </div>
        <div>
          <span class="block text-xs font-semibold uppercase tracking-wide text-muted-foreground">API key</span>
          <div class="mt-1 flex gap-2">
            <input
              readonly
              type={showApikey ? "text" : "password"}
              value={torznabInfo.apikey}
              class="w-full rounded-md border border-border bg-muted/40 px-3 py-2 font-mono text-xs"
            />
            <button
              class="btn-secondary shrink-0"
              onclick={() => (showApikey = !showApikey)}
              title={showApikey ? "Hide" : "Show"}
            >
              {#if showApikey}
                <EyeOff class="h-3.5 w-3.5" />
              {:else}
                <Eye class="h-3.5 w-3.5" />
              {/if}
            </button>
            <button
              class="btn-secondary shrink-0"
              onclick={() => torznabInfo && navigator.clipboard.writeText(torznabInfo.apikey)}
              title="Copy"
            >
              <Copy class="h-3.5 w-3.5" />
            </button>
          </div>
        </div>
      </div>
    {:else}
      <pre class="mt-3 overflow-x-auto rounded-md bg-muted p-3 font-mono text-xs">Loading…</pre>
    {/if}
  </div>

  <NotificationsPanel />

  <div class="surface p-6">
    <div class="flex items-center gap-3">
      <div class="flex h-10 w-10 items-center justify-center rounded-xl bg-amber-500/20 text-amber-400">
        <Archive class="h-5 w-5" />
      </div>
      <div>
        <h3 class="text-base font-semibold">Backup & restore</h3>
        <p class="text-xs text-muted-foreground">
          Export or import a complete Trove install (database + session secret).
        </p>
      </div>
    </div>

    <div class="mt-5 grid gap-4 lg:grid-cols-2">
      <!-- Download -->
      <div class="rounded-xl border border-border/60 bg-background/40 p-4">
        <div class="mb-2 flex items-center gap-2">
          <Download class="h-4 w-4 text-primary" />
          <span class="text-sm font-semibold">Download backup</span>
        </div>
        <p class="text-xs text-muted-foreground">
          Grabs a zip with your database, session secret, and a manifest. The session secret
          is required to decrypt stored credentials — keep the zip safe.
        </p>
        <a
          href={api.backup.downloadUrl}
          download
          class="btn-primary mt-4 inline-flex"
        >
          <Download class="h-3.5 w-3.5" />
          Download .zip
        </a>
      </div>

      <!-- Restore -->
      <div class="rounded-xl border border-destructive/30 bg-destructive/5 p-4">
        <div class="mb-2 flex items-center gap-2">
          <Upload class="h-4 w-4 text-destructive" />
          <span class="text-sm font-semibold">Restore from backup</span>
        </div>
        <div class="mb-3 flex items-start gap-1.5 text-xs text-muted-foreground">
          <AlertTriangle class="mt-0.5 h-3 w-3 shrink-0 text-amber-500" />
          <span>
            Destructive. Overwrites your current DB and session secret. The old files are
            moved to <code class="font-mono">config/.pre-restore/</code> as a safety net.
          </span>
        </div>
        <input
          type="file"
          accept=".zip,application/zip"
          onchange={pickRestoreFile}
          class="mt-1 block w-full text-xs text-muted-foreground file:mr-3 file:rounded-md file:border file:border-border file:bg-card file:px-3 file:py-1.5 file:text-xs file:font-medium file:text-foreground hover:file:bg-muted"
        />
        {#if restoreFile}
          <div class="mt-2 text-xs text-muted-foreground">
            Selected: <span class="font-mono">{restoreFile.name}</span> ({(restoreFile.size / 1024).toFixed(1)} KB)
          </div>
        {/if}
        <button
          class="btn-primary mt-4 inline-flex disabled:opacity-60"
          disabled={!restoreFile || restoring}
          onclick={doRestore}
        >
          {#if restoring}
            <Loader2 class="h-3.5 w-3.5 animate-spin" />
          {:else}
            <Upload class="h-3.5 w-3.5" />
          {/if}
          Restore
        </button>
        {#if restoreMsg}
          <div
            class="mt-3 rounded-md border px-3 py-2 text-xs {restoreMsg.ok
              ? 'border-success/30 bg-success/10 text-success'
              : 'border-destructive/30 bg-destructive/10 text-destructive'}"
          >
            {restoreMsg.text}
          </div>
        {/if}
      </div>
    </div>

    <p class="mt-4 text-xs text-muted-foreground">
      Tip: to migrate Trove to a new host, download a backup here, install Trove on the new
      host (run through setup wizard with any throwaway credentials), log in, and restore the
      backup on the new host. All clients, indexers, feeds, tasks, and your original user
      account come with it.
    </p>
  </div>

  <!-- About -->
  <div class="surface relative overflow-hidden p-6">
    <div class="absolute inset-0 bg-gradient-to-br from-amber-500/5 via-transparent to-primary/10"></div>
    <div class="relative">
      <div class="flex items-center gap-2">
        <Info class="h-5 w-5 text-amber-400" />
        <h3 class="text-base font-semibold">About Trove</h3>
      </div>
      <p class="mt-2 text-sm text-muted-foreground">
        Trove is a modern, self-hosted media automation hub — search across multiple
        indexers, watch shows and movies, run hourly tasks, and (optionally) talk to
        a local AI to manage it all.
      </p>
      <dl class="mt-4 grid gap-2 text-sm sm:grid-cols-2">
        <div class="flex items-center justify-between rounded-md border border-border/40 bg-background/40 px-3 py-2">
          <dt class="text-muted-foreground">Version</dt>
          <dd class="font-mono">{version ?? "—"}</dd>
        </div>
        <div class="flex items-center justify-between rounded-md border border-border/40 bg-background/40 px-3 py-2">
          <dt class="text-muted-foreground">Developed by</dt>
          <dd class="font-semibold">PowerData</dd>
        </div>
        <div class="flex items-center justify-between rounded-md border border-border/40 bg-background/40 px-3 py-2">
          <dt class="text-muted-foreground">License</dt>
          <dd class="font-mono">GPL-3.0-or-later</dd>
        </div>
        <div class="flex items-center justify-between rounded-md border border-border/40 bg-background/40 px-3 py-2">
          <dt class="text-muted-foreground">Source</dt>
          <dd>
            <a
              href="https://github.com/masterdraco/Trove"
              target="_blank"
              rel="noopener noreferrer"
              class="font-mono text-primary underline-offset-2 hover:underline"
            >
              github.com/masterdraco/Trove
            </a>
          </dd>
        </div>
      </dl>
      <div class="mt-5 rounded-xl border border-amber-500/30 bg-amber-500/5 p-4">
        <p class="text-sm">
          <strong>Like Trove?</strong> It's free and open source, but it's also a one-person
          project built in evenings and weekends. If it saves you time, consider
          buying a coffee — it keeps the late-night commits going.
        </p>
        <a
          href="https://www.buymeacoffee.com/MasterDraco"
          target="_blank"
          rel="noopener noreferrer"
          class="btn-primary mt-3 inline-flex"
        >
          ☕ Buy me a coffee
        </a>
      </div>
    </div>
  </div>
</div>
