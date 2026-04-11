<script lang="ts">
  import { onMount } from "svelte";
  import { api } from "$lib/api";
  import { goto } from "$app/navigation";
  import {
    Sparkles,
    Globe,
    CheckCircle2,
    XCircle,
    Loader2,
    Wand2,
    SlidersHorizontal,
    Save
  } from "lucide-svelte";

  type AppSetting = Awaited<ReturnType<typeof api.appSettings.list>>[number];

  let aiStatus = $state<{ enabled: boolean; endpoint: string; model: string } | null>(null);
  let version = $state<string | null>(null);
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

  onMount(async () => {
    try {
      aiStatus = await api.ai.status();
    } catch {
      aiStatus = null;
    }
    try {
      const h = await api.health();
      version = h.version;
    } catch {
      version = null;
    }
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
      // AI settings get their own dedicated panel below
      if (s.group === "ai") continue;
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
        general: "General"
      }[group] ?? group
    );
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

  <div class="rounded-xl border border-border bg-card p-5">
    <h3 class="flex items-center gap-2 text-base font-semibold">
      <Globe class="h-4 w-4" /> System
    </h3>
    <dl class="mt-3 grid grid-cols-2 gap-3 text-sm">
      <dt class="text-muted-foreground">Version</dt>
      <dd class="font-mono">{version ?? "?"}</dd>
      <dt class="text-muted-foreground">Web origin</dt>
      <dd class="font-mono text-xs">{location.origin}</dd>
    </dl>
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

  <div class="rounded-xl border border-border bg-card p-5">
    <h3 class="text-base font-semibold">Torznab export</h3>
    <p class="mt-2 text-sm text-muted-foreground">
      Point Sonarr/Radarr at this URL. The apikey is the first 32 characters of your session
      secret — check <code class="font-mono text-xs">config/session.secret</code>.
    </p>
    <pre class="mt-3 overflow-x-auto rounded-md bg-muted p-3 font-mono text-xs">{location.origin}/torznab/api?apikey=&lt;first-32-chars&gt;&amp;t=search&amp;q=ubuntu</pre>
  </div>
</div>
