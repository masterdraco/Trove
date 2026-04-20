<script lang="ts">
  import { onMount } from "svelte";
  import { api, type CatalogEntryOut } from "$lib/api";
  import { Database, Loader2, Check, ArrowLeft } from "lucide-svelte";

  let entries = $state<CatalogEntryOut[]>([]);
  let loading = $state(true);
  let errorMsg = $state<string | null>(null);
  let installingSlug = $state<string | null>(null);
  let selectedMirror = $state<Record<string, string>>({});
  let perEntryError = $state<Record<string, string>>({});

  async function load() {
    loading = true;
    errorMsg = null;
    try {
      entries = await api.indexers.catalog.list();
      const next: Record<string, string> = {};
      for (const e of entries) next[e.slug] = e.default_mirror;
      selectedMirror = next;
    } catch (e) {
      const err = e as { detail?: string };
      errorMsg = err.detail ?? "Failed to load catalog.";
    } finally {
      loading = false;
    }
  }

  onMount(load);

  async function install(entry: CatalogEntryOut) {
    installingSlug = entry.slug;
    perEntryError[entry.slug] = "";
    try {
      await api.indexers.catalog.install(entry.slug, {
        base_url: selectedMirror[entry.slug],
        name: null
      });
      await load();
    } catch (e) {
      const err = e as { detail?: string };
      perEntryError[entry.slug] = err.detail ?? "Install failed.";
    } finally {
      installingSlug = null;
    }
  }
</script>

<div class="space-y-6">
  <div class="flex items-center gap-3">
    <a
      href="/indexers"
      class="inline-flex items-center gap-1 rounded-md border border-border bg-background px-3 py-1.5 text-sm hover:bg-muted"
    >
      <ArrowLeft class="h-3.5 w-3.5" /> Indexers
    </a>
    <div>
      <h2 class="text-xl font-semibold">Catalog</h2>
      <p class="mt-1 text-sm text-muted-foreground">
        One-click install for public, no-account torrent sites.
      </p>
    </div>
  </div>

  {#if loading}
    <div class="rounded-xl border border-border bg-card p-8 text-center text-sm text-muted-foreground">
      Loading…
    </div>
  {:else if errorMsg}
    <div class="rounded-xl border border-destructive/30 bg-destructive/10 p-6 text-sm text-destructive">
      {errorMsg}
    </div>
  {:else}
    <div class="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {#each entries as entry (entry.slug)}
        <div class="flex flex-col rounded-xl border border-border bg-card p-5 shadow-sm">
          <div class="mb-2 flex items-start gap-3">
            <div class="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-muted">
              <Database class="h-5 w-5 text-muted-foreground" />
            </div>
            <div class="min-w-0">
              <div class="truncate text-base font-semibold">{entry.display_name}</div>
              <div class="mt-0.5 flex flex-wrap gap-1">
                {#each entry.categories as cat (cat)}
                  <span class="inline-flex items-center rounded-full bg-muted px-2 py-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">
                    {cat}
                  </span>
                {/each}
              </div>
            </div>
          </div>
          <p class="mb-4 flex-1 text-sm text-muted-foreground">{entry.description}</p>

          <label class="mb-3 block">
            <span class="mb-1 block text-xs font-medium text-muted-foreground">Mirror</span>
            <select
              bind:value={selectedMirror[entry.slug]}
              disabled={entry.already_installed}
              class="w-full rounded-md border border-input bg-background px-2 py-1.5 text-xs disabled:opacity-60"
            >
              {#each entry.mirrors as mirror (mirror)}
                <option value={mirror}>{mirror}</option>
              {/each}
            </select>
          </label>

          {#if entry.already_installed}
            <button
              type="button"
              class="inline-flex items-center justify-center gap-2 rounded-md bg-muted px-3 py-2 text-sm font-medium text-muted-foreground"
              disabled
            >
              <Check class="h-4 w-4" /> Installed
            </button>
          {:else}
            <button
              type="button"
              class="inline-flex items-center justify-center gap-2 rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-60"
              disabled={installingSlug === entry.slug}
              onclick={() => install(entry)}
            >
              {#if installingSlug === entry.slug}
                <Loader2 class="h-4 w-4 animate-spin" /> Installing…
              {:else}
                Add
              {/if}
            </button>
          {/if}

          {#if perEntryError[entry.slug]}
            <div class="mt-2 text-xs text-destructive">{perEntryError[entry.slug]}</div>
          {/if}
        </div>
      {/each}
    </div>
  {/if}
</div>
