<script lang="ts">
  import { onMount } from "svelte";
  import { goto } from "$app/navigation";
  import {
    api,
    type ClientType,
    type IndexerType,
    type Protocol,
    type DownloadClientOut,
    type IndexerOut
  } from "$lib/api";
  import { CLIENT_TYPES } from "$lib/clientTypes";
  import {
    Sparkles,
    Download,
    Database,
    Check,
    ChevronRight,
    Loader2,
    CheckCircle2,
    XCircle,
    PartyPopper,
    SkipForward,
    Plus,
    Trash2
  } from "lucide-svelte";

  type Step = "welcome" | "client" | "indexer" | "ai" | "done";
  let step = $state<Step>("welcome");

  let clients = $state<DownloadClientOut[]>([]);
  let indexers = $state<IndexerOut[]>([]);

  // Client form state
  type ClientForm = {
    name: string;
    type: ClientType;
    url: string;
    credentials: Record<string, string>;
  };
  const emptyClientForm = (): ClientForm => ({
    name: "",
    type: "transmission",
    url: "",
    credentials: {}
  });
  let clientForm = $state<ClientForm>(emptyClientForm());
  let currentClientMeta = $derived(CLIENT_TYPES[clientForm.type]);
  let clientTesting = $state(false);
  let clientTestResult = $state<{ ok: boolean; msg: string } | null>(null);
  let clientSaving = $state(false);
  let clientError = $state<string | null>(null);
  let clientJustSaved = $state<string | null>(null);

  function normalizeUrl(raw: string): string {
    let u = raw.trim();
    u = u.replace(/^(https?:\/\/)+(https?:\/\/)/i, "$2");
    return u;
  }

  // Indexer form state
  type IndexerForm = {
    name: string;
    type: IndexerType;
    protocol: Protocol;
    base_url: string;
    api_key: string;
  };
  const emptyIndexerForm = (): IndexerForm => ({
    name: "",
    type: "newznab",
    protocol: "usenet",
    base_url: "",
    api_key: ""
  });
  let indexerForm = $state<IndexerForm>(emptyIndexerForm());
  let indexerSaving = $state(false);
  let indexerError = $state<string | null>(null);
  let indexerJustSaved = $state<string | null>(null);

  // AI state
  let aiTesting = $state(false);
  let aiResult = $state<{ ok: boolean; msg: string } | null>(null);

  function dismiss() {
    try {
      localStorage.setItem("trove_onboarding_dismissed", "1");
    } catch {}
  }

  function skipAll() {
    dismiss();
    goto("/");
  }

  onMount(async () => {
    try {
      clients = await api.clients.list();
      indexers = await api.indexers.list();
    } catch {}
    // Auto-advance if user already has things
    if (clients.length > 0 && indexers.length > 0) {
      step = "done";
    } else if (clients.length > 0) {
      step = "indexer";
    }
  });

  async function testClient() {
    clientTesting = true;
    clientTestResult = null;
    try {
      const r = await api.clients.testTransient({
        type: clientForm.type,
        url: normalizeUrl(clientForm.url),
        credentials: clientForm.credentials
      });
      clientTestResult = {
        ok: r.ok,
        msg: r.ok ? (r.version ? `Connected · ${r.version}` : "Connected") : r.message ?? "Failed"
      };
    } catch (e) {
      clientTestResult = { ok: false, msg: (e as { detail?: string }).detail ?? "Request failed" };
    } finally {
      clientTesting = false;
    }
  }

  async function saveClient() {
    clientSaving = true;
    clientError = null;
    try {
      await api.clients.create({
        name: clientForm.name,
        type: clientForm.type,
        url: normalizeUrl(clientForm.url),
        credentials: clientForm.credentials
      });
      clients = await api.clients.list();
      clientJustSaved = clientForm.name;
      clientForm = emptyClientForm();
      clientTestResult = null;
    } catch (e) {
      const err = e as { status?: number; detail?: string };
      clientError = err.status === 409 ? "Name already used." : err.detail ?? "Save failed.";
    } finally {
      clientSaving = false;
    }
  }

  function addAnotherClient() {
    clientJustSaved = null;
    clientForm = emptyClientForm();
    clientError = null;
    clientTestResult = null;
  }

  async function removeClientFromList(id: number) {
    if (!confirm("Delete this client?")) return;
    await api.clients.remove(id);
    clients = await api.clients.list();
  }

  async function saveIndexer() {
    indexerSaving = true;
    indexerError = null;
    try {
      await api.indexers.create({
        name: indexerForm.name,
        type: indexerForm.type,
        protocol: indexerForm.protocol,
        base_url: normalizeUrl(indexerForm.base_url),
        credentials: { api_key: indexerForm.api_key }
      });
      indexers = await api.indexers.list();
      indexerJustSaved = indexerForm.name;
      indexerForm = emptyIndexerForm();
    } catch (e) {
      const err = e as { status?: number; detail?: string };
      indexerError = err.status === 409 ? "Name already used." : err.detail ?? "Save failed.";
    } finally {
      indexerSaving = false;
    }
  }

  function addAnotherIndexer() {
    indexerJustSaved = null;
    indexerForm = emptyIndexerForm();
    indexerError = null;
  }

  async function removeIndexerFromList(id: number) {
    if (!confirm("Delete this indexer?")) return;
    await api.indexers.remove(id);
    indexers = await api.indexers.list();
  }

  async function testAI() {
    aiTesting = true;
    aiResult = null;
    try {
      const r = await api.ai.test();
      aiResult = { ok: true, msg: r.response.trim() || "Connected" };
    } catch (e) {
      aiResult = { ok: false, msg: (e as { detail?: string }).detail ?? "Not reachable" };
    } finally {
      aiTesting = false;
    }
  }

  function finish() {
    dismiss();
    goto("/");
  }

  const steps: { key: Step; label: string; icon: typeof Sparkles }[] = [
    { key: "welcome", label: "Welcome", icon: Sparkles },
    { key: "client", label: "Download client", icon: Download },
    { key: "indexer", label: "Indexer", icon: Database },
    { key: "ai", label: "AI", icon: Sparkles },
    { key: "done", label: "Done", icon: PartyPopper }
  ];

  const stepIndex = $derived(steps.findIndex((s) => s.key === step));
</script>

<div class="mx-auto max-w-3xl space-y-6">
  <!-- Stepper -->
  <div class="rounded-2xl border border-border bg-card p-5 shadow-sm">
    <div class="flex items-center justify-between">
      <div class="flex items-center gap-3">
        <img src="/logo-128.png" alt="Trove" class="h-10 w-10 object-contain drop-shadow-[0_0_12px_hsl(var(--primary)/0.6)]" />
        <div>
          <div class="text-sm font-semibold">Trove setup</div>
          <div class="text-xs text-muted-foreground">
            Step {stepIndex + 1} of {steps.length}
          </div>
        </div>
      </div>
      <button
        type="button"
        class="inline-flex items-center gap-1 rounded-md border border-border bg-background px-3 py-1.5 text-xs text-muted-foreground hover:bg-muted"
        onclick={skipAll}
      >
        <SkipForward class="h-3.5 w-3.5" />
        Skip setup
      </button>
    </div>

    <ol class="mt-5 flex items-center gap-2">
      {#each steps as s, idx}
        {@const done = idx < stepIndex}
        {@const active = idx === stepIndex}
        {@const Icon = s.icon}
        <li class="flex flex-1 items-center gap-2">
          <div
            class="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border transition-colors {done
              ? 'border-primary bg-primary text-primary-foreground'
              : active
                ? 'border-primary text-primary'
                : 'border-border text-muted-foreground'}"
          >
            {#if done}
              <Check class="h-4 w-4" />
            {:else}
              <Icon class="h-4 w-4" />
            {/if}
          </div>
          <div class="hidden text-xs sm:block {active ? 'font-medium' : 'text-muted-foreground'}">
            {s.label}
          </div>
          {#if idx < steps.length - 1}
            <div class="flex-1 border-t {done ? 'border-primary' : 'border-border'}"></div>
          {/if}
        </li>
      {/each}
    </ol>
  </div>

  <!-- Step content -->
  {#if step === "welcome"}
    <div class="rounded-2xl border border-border bg-card p-8 shadow-sm">
      <h2 class="text-2xl font-semibold">Welcome to Trove 👋</h2>
      <p class="mt-3 text-sm text-muted-foreground">
        You're 3 minutes away from a working FlexGet replacement. We'll walk you through
        connecting your first download client, your first indexer, and checking the AI layer.
      </p>
      <ul class="mt-5 space-y-2 text-sm">
        <li class="flex items-start gap-2">
          <Download class="mt-0.5 h-4 w-4 text-primary" />
          <div>
            <span class="font-medium">Download client</span> — Deluge, Transmission, SABnzbd or NZBGet.
          </div>
        </li>
        <li class="flex items-start gap-2">
          <Database class="mt-0.5 h-4 w-4 text-primary" />
          <div>
            <span class="font-medium">Indexer</span> — Newznab/Torznab API or a Cardigann YAML definition.
          </div>
        </li>
        <li class="flex items-start gap-2">
          <Sparkles class="mt-0.5 h-4 w-4 text-primary" />
          <div>
            <span class="font-medium">AI (optional)</span> — Verify Ollama connectivity for smart ranking.
          </div>
        </li>
      </ul>
      <div class="mt-8 flex justify-between">
        <button
          class="rounded-md border border-border bg-background px-4 py-2 text-sm hover:bg-muted"
          onclick={skipAll}
        >
          Skip for now
        </button>
        <button
          class="inline-flex items-center gap-1 rounded-md bg-primary px-5 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
          onclick={() => (step = "client")}
        >
          Get started <ChevronRight class="h-4 w-4" />
        </button>
      </div>
    </div>
  {/if}

  {#if step === "client"}
    <div class="rounded-2xl border border-border bg-card p-8 shadow-sm">
      <div class="flex items-start justify-between">
        <div>
          <h2 class="flex items-center gap-2 text-xl font-semibold">
            <Download class="h-5 w-5 text-primary" /> Download clients
          </h2>
          <p class="mt-1 text-sm text-muted-foreground">
            Add one or more targets where Trove will push matched releases. You can add as
            many as you like before continuing.
          </p>
        </div>
      </div>

      {#if clients.length > 0}
        <div class="mt-5 space-y-2">
          {#each clients as c (c.id)}
            <div class="flex items-center justify-between rounded-lg border border-border bg-background px-3 py-2 text-sm">
              <div class="flex items-center gap-2">
                <CheckCircle2 class="h-4 w-4 text-green-600" />
                <div>
                  <div class="font-medium">{c.name}</div>
                  <div class="text-xs text-muted-foreground">
                    {c.type} · <span class="font-mono">{c.url}</span>
                  </div>
                </div>
              </div>
              <button
                type="button"
                class="rounded-md p-1 text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
                onclick={() => removeClientFromList(c.id)}
                aria-label="Remove"
              >
                <Trash2 class="h-4 w-4" />
              </button>
            </div>
          {/each}
        </div>
      {/if}

      {#if clientJustSaved}
        <div class="mt-5 rounded-xl border border-green-500/30 bg-green-500/5 p-5">
          <div class="flex items-center gap-2 text-green-700 dark:text-green-400">
            <CheckCircle2 class="h-5 w-5" />
            <span class="text-sm font-medium">{clientJustSaved} added successfully</span>
          </div>
          <div class="mt-4 flex flex-wrap gap-2">
            <button
              type="button"
              class="inline-flex items-center gap-1 rounded-md border border-border bg-background px-4 py-2 text-sm hover:bg-muted"
              onclick={addAnotherClient}
            >
              <Plus class="h-4 w-4" /> Add another client
            </button>
            <button
              type="button"
              class="inline-flex items-center gap-1 rounded-md bg-primary px-5 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
              onclick={() => (step = "indexer")}
            >
              Continue to indexers <ChevronRight class="h-4 w-4" />
            </button>
          </div>
        </div>
      {:else}
        <div class="mt-6 space-y-4">
          <div class="grid grid-cols-4 gap-2">
            {#each Object.entries(CLIENT_TYPES) as [key, meta]}
              <button
                type="button"
                onclick={() => {
                  clientForm.type = key as ClientType;
                  clientForm.credentials = {};
                  clientTestResult = null;
                }}
                class="flex flex-col items-center gap-1 rounded-lg border p-3 text-center text-xs transition-colors {clientForm.type ===
                key
                  ? 'border-primary bg-primary/5'
                  : 'border-border bg-background hover:bg-muted'}"
              >
                <div class="font-medium">{meta.label}</div>
                <div class="text-[10px] uppercase text-muted-foreground">{meta.protocol}</div>
              </button>
            {/each}
          </div>

          <label class="block">
            <span class="mb-1 block text-sm font-medium">Name</span>
            <input
              type="text"
              bind:value={clientForm.name}
              placeholder="e.g. home-transmission"
              class="w-full rounded-md border border-input bg-background px-3 py-2 text-sm outline-none ring-ring focus:ring-2"
            />
          </label>

          <label class="block">
            <span class="mb-1 block text-sm font-medium">URL</span>
            <input
              type="url"
              bind:value={clientForm.url}
              placeholder={currentClientMeta.urlPlaceholder}
              class="w-full rounded-md border border-input bg-background px-3 py-2 font-mono text-sm outline-none ring-ring focus:ring-2"
            />
            <span class="mt-1 block text-xs text-muted-foreground">{currentClientMeta.urlHint}</span>
          </label>

          <div class="grid grid-cols-2 gap-3">
            {#each currentClientMeta.fields as field (field.key)}
              <label class="block">
                <span class="mb-1 block text-sm font-medium">{field.label}</span>
                <input
                  type={field.type}
                  value={clientForm.credentials[field.key] ?? ""}
                  oninput={(e) => {
                    clientForm.credentials[field.key] = (e.currentTarget as HTMLInputElement).value;
                  }}
                  class="w-full rounded-md border border-input bg-background px-3 py-2 text-sm outline-none ring-ring focus:ring-2"
                />
              </label>
            {/each}
          </div>

          {#if clientTestResult}
            <div
              class="rounded-md border px-3 py-2 text-xs {clientTestResult.ok
                ? 'border-green-500/30 bg-green-500/10 text-green-700 dark:text-green-300'
                : 'border-destructive/30 bg-destructive/10 text-destructive'}"
            >
              <div class="flex items-center gap-1.5">
                {#if clientTestResult.ok}
                  <CheckCircle2 class="h-3.5 w-3.5" />
                {:else}
                  <XCircle class="h-3.5 w-3.5" />
                {/if}
                {clientTestResult.msg}
              </div>
            </div>
          {/if}

          {#if clientError}
            <div class="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {clientError}
            </div>
          {/if}
        </div>

        <div class="mt-8 flex items-center justify-between">
          <div class="flex gap-2">
            <button
              type="button"
              class="rounded-md border border-border bg-background px-3 py-2 text-sm hover:bg-muted"
              onclick={testClient}
              disabled={clientTesting || !clientForm.url}
            >
              {#if clientTesting}
                <Loader2 class="inline h-3.5 w-3.5 animate-spin" />
              {/if}
              Test connection
            </button>
            <button
              type="button"
              class="rounded-md border border-border bg-background px-3 py-2 text-sm text-muted-foreground hover:bg-muted"
              onclick={() => (step = "indexer")}
            >
              {clients.length > 0 ? "Continue to indexers" : "Skip"}
            </button>
          </div>
          <button
            type="button"
            class="inline-flex items-center gap-1 rounded-md bg-primary px-5 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-60"
            onclick={saveClient}
            disabled={clientSaving || !clientForm.name || !clientForm.url}
          >
            {clientSaving ? "Saving…" : "Save client"}
          </button>
        </div>
      {/if}
    </div>
  {/if}

  {#if step === "indexer"}
    <div class="rounded-2xl border border-border bg-card p-8 shadow-sm">
      <div class="flex items-start justify-between">
        <div>
          <h2 class="flex items-center gap-2 text-xl font-semibold">
            <Database class="h-5 w-5 text-primary" /> Indexers
          </h2>
          <p class="mt-1 text-sm text-muted-foreground">
            Where Trove searches for releases. Add as many as you like.
          </p>
        </div>
      </div>

      {#if indexers.length > 0}
        <div class="mt-5 space-y-2">
          {#each indexers as i (i.id)}
            <div class="flex items-center justify-between rounded-lg border border-border bg-background px-3 py-2 text-sm">
              <div class="flex items-center gap-2">
                <CheckCircle2 class="h-4 w-4 text-green-600" />
                <div>
                  <div class="font-medium">{i.name}</div>
                  <div class="text-xs text-muted-foreground">
                    {i.type} · <span class="font-mono">{i.base_url}</span>
                  </div>
                </div>
              </div>
              <button
                type="button"
                class="rounded-md p-1 text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
                onclick={() => removeIndexerFromList(i.id)}
                aria-label="Remove"
              >
                <Trash2 class="h-4 w-4" />
              </button>
            </div>
          {/each}
        </div>
      {/if}

      {#if indexerJustSaved}
        <div class="mt-5 rounded-xl border border-green-500/30 bg-green-500/5 p-5">
          <div class="flex items-center gap-2 text-green-700 dark:text-green-400">
            <CheckCircle2 class="h-5 w-5" />
            <span class="text-sm font-medium">{indexerJustSaved} added successfully</span>
          </div>
          <div class="mt-4 flex flex-wrap gap-2">
            <button
              type="button"
              class="inline-flex items-center gap-1 rounded-md border border-border bg-background px-4 py-2 text-sm hover:bg-muted"
              onclick={addAnotherIndexer}
            >
              <Plus class="h-4 w-4" /> Add another indexer
            </button>
            <button
              type="button"
              class="inline-flex items-center gap-1 rounded-md bg-primary px-5 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
              onclick={() => (step = "ai")}
            >
              Continue <ChevronRight class="h-4 w-4" />
            </button>
          </div>
        </div>
      {:else}
        <div class="mt-6 space-y-4">
          <div class="grid grid-cols-2 gap-2">
            <button
              type="button"
              onclick={() => {
                indexerForm.type = "newznab";
                indexerForm.protocol = "usenet";
              }}
              class="rounded-lg border p-3 text-left text-xs transition-colors {indexerForm.type ===
              'newznab'
                ? 'border-primary bg-primary/5'
                : 'border-border bg-background hover:bg-muted'}"
            >
              <div class="text-sm font-medium">Newznab</div>
              <div class="text-muted-foreground">Usenet indexer — NZB files</div>
            </button>
            <button
              type="button"
              onclick={() => {
                indexerForm.type = "torznab";
                indexerForm.protocol = "torrent";
              }}
              class="rounded-lg border p-3 text-left text-xs transition-colors {indexerForm.type ===
              'torznab'
                ? 'border-primary bg-primary/5'
                : 'border-border bg-background hover:bg-muted'}"
            >
              <div class="text-sm font-medium">Torznab</div>
              <div class="text-muted-foreground">Torrent indexer using Newznab API</div>
            </button>
          </div>

          <label class="block">
            <span class="mb-1 block text-sm font-medium">Name</span>
            <input
              type="text"
              bind:value={indexerForm.name}
              placeholder="e.g. nzbgeek"
              class="w-full rounded-md border border-input bg-background px-3 py-2 text-sm outline-none ring-ring focus:ring-2"
            />
          </label>

          <label class="block">
            <span class="mb-1 block text-sm font-medium">Base URL</span>
            <input
              type="url"
              bind:value={indexerForm.base_url}
              placeholder="https://api.example.com"
              class="w-full rounded-md border border-input bg-background px-3 py-2 font-mono text-sm outline-none ring-ring focus:ring-2"
            />
          </label>

          <label class="block">
            <span class="mb-1 block text-sm font-medium">API key</span>
            <input
              type="password"
              bind:value={indexerForm.api_key}
              class="w-full rounded-md border border-input bg-background px-3 py-2 text-sm outline-none ring-ring focus:ring-2"
            />
          </label>

          {#if indexerError}
            <div class="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {indexerError}
            </div>
          {/if}
        </div>

        <div class="mt-8 flex items-center justify-between">
          <button
            type="button"
            class="rounded-md border border-border bg-background px-3 py-2 text-sm text-muted-foreground hover:bg-muted"
            onclick={() => (step = "ai")}
          >
            {indexers.length > 0 ? "Continue" : "Skip"}
          </button>
          <button
            type="button"
            class="inline-flex items-center gap-1 rounded-md bg-primary px-5 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-60"
            onclick={saveIndexer}
            disabled={indexerSaving || !indexerForm.name || !indexerForm.base_url || !indexerForm.api_key}
          >
            {indexerSaving ? "Saving…" : "Save indexer"}
          </button>
        </div>
      {/if}
    </div>
  {/if}

  {#if step === "ai"}
    <div class="rounded-2xl border border-border bg-card p-8 shadow-sm">
      <h2 class="flex items-center gap-2 text-xl font-semibold">
        <Sparkles class="h-5 w-5 text-primary" /> Check AI (optional)
      </h2>
      <p class="mt-1 text-sm text-muted-foreground">
        Trove uses a local Ollama model for fuzzy ranking and chat. This step just verifies
        the server can reach it — configuration is done via environment variables.
      </p>

      <div class="mt-6">
        <button
          type="button"
          class="inline-flex items-center gap-2 rounded-md border border-border bg-background px-4 py-2 text-sm hover:bg-muted"
          onclick={testAI}
          disabled={aiTesting}
        >
          {#if aiTesting}
            <Loader2 class="h-4 w-4 animate-spin" />
          {:else if aiResult?.ok}
            <CheckCircle2 class="h-4 w-4 text-green-600" />
          {:else if aiResult && !aiResult.ok}
            <XCircle class="h-4 w-4 text-destructive" />
          {/if}
          Test AI connection
        </button>
        {#if aiResult}
          <div
            class="mt-3 rounded-md border px-3 py-2 text-xs {aiResult.ok
              ? 'border-green-500/30 bg-green-500/10 text-green-700 dark:text-green-300'
              : 'border-destructive/30 bg-destructive/10 text-destructive'}"
          >
            {aiResult.msg}
          </div>
        {/if}
      </div>

      <div class="mt-8 flex items-center justify-between">
        <button
          type="button"
          class="rounded-md border border-border bg-background px-3 py-2 text-sm text-muted-foreground hover:bg-muted"
          onclick={() => (step = "done")}
        >
          Skip
        </button>
        <button
          type="button"
          class="inline-flex items-center gap-1 rounded-md bg-primary px-5 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
          onclick={() => (step = "done")}
        >
          Continue <ChevronRight class="h-4 w-4" />
        </button>
      </div>
    </div>
  {/if}

  {#if step === "done"}
    <div class="rounded-2xl border border-border bg-card p-8 text-center shadow-sm">
      <div class="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-primary/10 text-primary">
        <PartyPopper class="h-7 w-7" />
      </div>
      <h2 class="mt-4 text-2xl font-semibold">You're all set</h2>
      <p class="mt-2 text-sm text-muted-foreground">
        {clients.length} download client{clients.length === 1 ? "" : "s"} and
        {indexers.length} indexer{indexers.length === 1 ? "" : "s"} configured.
      </p>

      <div class="mt-6 grid gap-3 sm:grid-cols-3">
        <a
          href="/search"
          onclick={dismiss}
          class="rounded-lg border border-border bg-background p-4 text-left text-sm hover:bg-muted"
        >
          <div class="font-semibold">Try a search</div>
          <div class="mt-1 text-xs text-muted-foreground">Query all indexers at once</div>
        </a>
        <a
          href="/tasks"
          onclick={dismiss}
          class="rounded-lg border border-border bg-background p-4 text-left text-sm hover:bg-muted"
        >
          <div class="font-semibold">Create a task</div>
          <div class="mt-1 text-xs text-muted-foreground">Automate recurring searches</div>
        </a>
        <a
          href="/watchlist"
          onclick={dismiss}
          class="rounded-lg border border-border bg-background p-4 text-left text-sm hover:bg-muted"
        >
          <div class="font-semibold">Add to watchlist</div>
          <div class="mt-1 text-xs text-muted-foreground">Track shows and films</div>
        </a>
      </div>

      <button
        type="button"
        class="mt-6 inline-flex items-center gap-1 rounded-md bg-primary px-6 py-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/90"
        onclick={finish}
      >
        Go to dashboard <ChevronRight class="h-4 w-4" />
      </button>
    </div>
  {/if}
</div>
