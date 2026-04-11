<script lang="ts">
  import { onMount } from "svelte";
  import { api, type DownloadClientOut, type ClientType, type ClientTestResult } from "$lib/api";
  import { CLIENT_TYPES } from "$lib/clientTypes";
  import { Plus, Trash2, PlugZap, Loader2, CheckCircle2, XCircle, Pencil } from "lucide-svelte";

  let clients = $state<DownloadClientOut[]>([]);
  let loading = $state(true);
  let error = $state<string | null>(null);

  let showForm = $state(false);
  let saving = $state(false);
  let formError = $state<string | null>(null);
  let editingId = $state<number | null>(null);

  type FormState = {
    name: string;
    type: ClientType;
    url: string;
    credentials: Record<string, string>;
    default_category: string;
    default_save_path: string;
  };

  const emptyForm = (): FormState => ({
    name: "",
    type: "transmission",
    url: "",
    credentials: {},
    default_category: "",
    default_save_path: ""
  });

  function normalizeUrl(raw: string): string {
    let u = raw.trim();
    // Strip duplicate scheme prefixes like "http://http://..."
    u = u.replace(/^(https?:\/\/)+(https?:\/\/)/i, "$2");
    return u;
  }

  let form = $state<FormState>(emptyForm());
  let testingId = $state<number | null>(null);
  let testResults = $state<Record<number, ClientTestResult>>({});

  let currentMeta = $derived(CLIENT_TYPES[form.type]);

  async function load() {
    loading = true;
    error = null;
    try {
      clients = await api.clients.list();
    } catch (e) {
      error = "Failed to load clients.";
    } finally {
      loading = false;
    }
  }

  onMount(load);

  function openForm() {
    form = emptyForm();
    formError = null;
    editingId = null;
    showForm = true;
  }

  function openEdit(client: DownloadClientOut) {
    form = {
      name: client.name,
      type: client.type,
      url: client.url,
      credentials: {},
      default_category: client.default_category ?? "",
      default_save_path: client.default_save_path ?? ""
    };
    editingId = client.id;
    formError = null;
    showForm = true;
  }

  function closeForm() {
    showForm = false;
    editingId = null;
  }

  async function submitForm(event: Event) {
    event.preventDefault();
    formError = null;
    saving = true;
    const cleanUrl = normalizeUrl(form.url);
    try {
      if (editingId !== null) {
        // Only send credentials if the user actually typed new ones.
        const hasNewCreds = Object.values(form.credentials).some((v) => v && v.length > 0);
        await api.clients.update(editingId, {
          name: form.name,
          url: cleanUrl,
          credentials: hasNewCreds ? form.credentials : undefined,
          default_category: form.default_category || null,
          default_save_path: form.default_save_path || null
        });
      } else {
        await api.clients.create({
          name: form.name,
          type: form.type,
          url: cleanUrl,
          credentials: form.credentials,
          default_category: form.default_category || null,
          default_save_path: form.default_save_path || null
        });
      }
      showForm = false;
      editingId = null;
      await load();
    } catch (e) {
      const err = e as { status?: number; detail?: string };
      if (err.status === 409) formError = "A client with that name already exists.";
      else formError = err.detail ?? "Failed to save client.";
    } finally {
      saving = false;
    }
  }

  async function testExisting(client: DownloadClientOut) {
    testingId = client.id;
    try {
      testResults[client.id] = await api.clients.test(client.id);
      await load();
    } catch {
      testResults[client.id] = {
        ok: false,
        version: null,
        message: "Request failed",
        details: {},
        categories: []
      };
    } finally {
      testingId = null;
    }
  }

  async function remove(client: DownloadClientOut) {
    if (!confirm(`Delete client "${client.name}"?`)) return;
    await api.clients.remove(client.id);
    await load();
  }

  function formatTime(iso: string | null): string {
    if (!iso) return "never";
    return new Date(iso).toLocaleString();
  }
</script>

<div class="space-y-6">
  <div class="flex items-center justify-between">
    <div>
      <h2 class="text-xl font-semibold">Download clients</h2>
      <p class="mt-1 text-sm text-muted-foreground">
        Connect Trove to Deluge, Transmission, SABnzbd or NZBGet.
      </p>
    </div>
    <button
      class="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
      onclick={openForm}
    >
      <Plus class="h-4 w-4" /> Add client
    </button>
  </div>

  {#if loading}
    <div class="rounded-xl border border-border bg-card p-8 text-center text-sm text-muted-foreground">
      Loading…
    </div>
  {:else if error}
    <div class="rounded-xl border border-destructive/40 bg-destructive/10 p-4 text-sm text-destructive">
      {error}
    </div>
  {:else if clients.length === 0}
    <div class="rounded-xl border border-dashed border-border bg-card p-10 text-center">
      <div class="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-muted">
        <PlugZap class="h-5 w-5 text-muted-foreground" />
      </div>
      <div class="text-base font-medium">No clients yet</div>
      <p class="mt-1 text-sm text-muted-foreground">
        Add your first Deluge, Transmission, SABnzbd or NZBGet connection to get started.
      </p>
    </div>
  {:else}
    <div class="overflow-hidden rounded-xl border border-border bg-card">
      <table class="w-full text-sm">
        <thead class="bg-muted/50 text-left text-xs uppercase tracking-wide text-muted-foreground">
          <tr>
            <th class="px-4 py-3 font-medium">Name</th>
            <th class="px-4 py-3 font-medium">Type</th>
            <th class="px-4 py-3 font-medium">URL</th>
            <th class="px-4 py-3 font-medium">Last test</th>
            <th class="px-4 py-3 font-medium"></th>
          </tr>
        </thead>
        <tbody>
          {#each clients as client (client.id)}
            {@const meta = CLIENT_TYPES[client.type]}
            <tr class="border-t border-border">
              <td class="px-4 py-3">
                <div class="font-medium">{client.name}</div>
                {#if !client.enabled}
                  <div class="text-xs text-muted-foreground">disabled</div>
                {/if}
              </td>
              <td class="px-4 py-3">
                <span class="inline-flex items-center rounded-full bg-muted px-2 py-0.5 text-xs">
                  {meta.label}
                </span>
                <span class="ml-2 text-xs text-muted-foreground">{client.protocol}</span>
              </td>
              <td class="px-4 py-3 font-mono text-xs text-muted-foreground">{client.url}</td>
              <td class="px-4 py-3">
                {#if client.last_test_at}
                  <div class="flex items-center gap-1.5 text-xs">
                    {#if client.last_test_ok}
                      <CheckCircle2 class="h-3.5 w-3.5 text-green-600" />
                      <span>ok</span>
                    {:else}
                      <XCircle class="h-3.5 w-3.5 text-destructive" />
                      <span class="text-destructive">{client.last_test_message ?? "failed"}</span>
                    {/if}
                  </div>
                  <div class="text-xs text-muted-foreground">{formatTime(client.last_test_at)}</div>
                {:else}
                  <span class="text-xs text-muted-foreground">never</span>
                {/if}
              </td>
              <td class="px-4 py-3 text-right">
                <div class="flex justify-end gap-2">
                  <button
                    class="inline-flex items-center gap-1 rounded-md border border-border bg-background px-3 py-1.5 text-xs hover:bg-muted"
                    onclick={() => testExisting(client)}
                    disabled={testingId === client.id}
                  >
                    {#if testingId === client.id}
                      <Loader2 class="h-3.5 w-3.5 animate-spin" />
                    {:else}
                      <PlugZap class="h-3.5 w-3.5" />
                    {/if}
                    Test
                  </button>
                  <button
                    class="inline-flex items-center gap-1 rounded-md border border-border bg-background px-3 py-1.5 text-xs hover:bg-muted"
                    onclick={() => openEdit(client)}
                  >
                    <Pencil class="h-3.5 w-3.5" />
                    Edit
                  </button>
                  <button
                    class="inline-flex items-center gap-1 rounded-md border border-border bg-background px-3 py-1.5 text-xs text-destructive hover:bg-destructive/10"
                    onclick={() => remove(client)}
                  >
                    <Trash2 class="h-3.5 w-3.5" />
                    Delete
                  </button>
                </div>
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}
</div>

{#if showForm}
  <div
    class="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-background/80 p-6 backdrop-blur-sm"
  >
    <form
      onsubmit={submitForm}
      class="mt-10 w-full max-w-lg rounded-2xl border border-border bg-card p-6 shadow-2xl"
    >
      <div class="mb-4 flex items-center justify-between">
        <h3 class="text-lg font-semibold">
          {editingId !== null ? "Edit download client" : "Add download client"}
        </h3>
        <button
          type="button"
          class="rounded-md p-1 text-muted-foreground hover:bg-muted"
          onclick={closeForm}
          aria-label="Close"
        >
          ✕
        </button>
      </div>

      <div class="space-y-4">
        <div class="grid grid-cols-2 gap-3">
          <label class="col-span-2 block">
            <span class="mb-1 block text-sm font-medium">Name</span>
            <input
              type="text"
              bind:value={form.name}
              required
              class="w-full rounded-md border border-input bg-background px-3 py-2 text-sm outline-none ring-ring focus:ring-2"
            />
          </label>
          <label class="block">
            <span class="mb-1 block text-sm font-medium">Type</span>
            <select
              bind:value={form.type}
              disabled={editingId !== null}
              class="w-full rounded-md border border-input bg-background px-3 py-2 text-sm outline-none ring-ring focus:ring-2 disabled:opacity-60"
            >
              {#each Object.entries(CLIENT_TYPES) as [key, meta]}
                <option value={key}>{meta.label}</option>
              {/each}
            </select>
          </label>
          <div class="block">
            <span class="mb-1 block text-sm font-medium text-transparent">Protocol</span>
            <div
              class="rounded-md border border-dashed border-border bg-muted/40 px-3 py-2 text-sm text-muted-foreground"
            >
              {currentMeta.protocol}
            </div>
          </div>
        </div>

        <label class="block">
          <span class="mb-1 block text-sm font-medium">URL</span>
          <input
            type="url"
            bind:value={form.url}
            placeholder={currentMeta.urlPlaceholder}
            required
            class="w-full rounded-md border border-input bg-background px-3 py-2 font-mono text-sm outline-none ring-ring focus:ring-2"
          />
          <span class="mt-1 block text-xs text-muted-foreground">{currentMeta.urlHint}</span>
        </label>

        <div class="grid grid-cols-2 gap-3">
          {#each currentMeta.fields as field (field.key)}
            <label class="block">
              <span class="mb-1 block text-sm font-medium">{field.label}</span>
              <input
                type={field.type}
                value={form.credentials[field.key] ?? ""}
                oninput={(e) => {
                  form.credentials[field.key] = (e.currentTarget as HTMLInputElement).value;
                }}
                required={editingId === null && (field.required ?? false)}
                placeholder={editingId !== null ? "•••••• (leave blank to keep)" : (field.placeholder ?? "")}
                class="w-full rounded-md border border-input bg-background px-3 py-2 text-sm outline-none ring-ring focus:ring-2"
              />
            </label>
          {/each}
        </div>

        <div class="grid grid-cols-2 gap-3">
          <label class="block">
            <span class="mb-1 block text-sm font-medium">Default category</span>
            <input
              type="text"
              bind:value={form.default_category}
              placeholder="tv"
              class="w-full rounded-md border border-input bg-background px-3 py-2 text-sm outline-none ring-ring focus:ring-2"
            />
          </label>
          <label class="block">
            <span class="mb-1 block text-sm font-medium">Default save path</span>
            <input
              type="text"
              bind:value={form.default_save_path}
              placeholder="/downloads"
              class="w-full rounded-md border border-input bg-background px-3 py-2 text-sm outline-none ring-ring focus:ring-2"
            />
          </label>
        </div>
      </div>

      {#if formError}
        <div class="mt-4 rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {formError}
        </div>
      {/if}

      <div class="mt-6 flex justify-end gap-2">
        <button
          type="button"
          class="rounded-md border border-border bg-background px-4 py-2 text-sm hover:bg-muted"
          onclick={closeForm}
        >
          Cancel
        </button>
        <button
          type="submit"
          class="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-60"
          disabled={saving}
        >
          {saving ? "Saving…" : editingId !== null ? "Update client" : "Save client"}
        </button>
      </div>
    </form>
  </div>
{/if}
