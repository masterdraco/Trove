<script lang="ts">
  import { onMount } from "svelte";
  import { api } from "$lib/api";
  import { Plus, Trash2, Eye } from "lucide-svelte";

  type Item = Awaited<ReturnType<typeof api.watchlist.list>>[number];

  let items = $state<Item[]>([]);
  let loading = $state(true);
  let showForm = $state(false);
  let form = $state({
    kind: "series" as "series" | "movie",
    title: "",
    year: null as number | null,
    target_quality: "",
    notes: ""
  });

  async function load() {
    loading = true;
    items = await api.watchlist.list();
    loading = false;
  }

  onMount(load);

  async function save(e: Event) {
    e.preventDefault();
    await api.watchlist.create({
      kind: form.kind,
      title: form.title,
      year: form.year,
      target_quality: form.target_quality || null,
      notes: form.notes || null
    });
    showForm = false;
    form = { kind: "series", title: "", year: null, target_quality: "", notes: "" };
    await load();
  }

  async function remove(id: number) {
    if (!confirm("Remove from watchlist?")) return;
    await api.watchlist.remove(id);
    await load();
  }
</script>

<div class="space-y-6">
  <div class="flex items-center justify-between">
    <div>
      <h2 class="text-xl font-semibold">Watchlist</h2>
      <p class="mt-1 text-sm text-muted-foreground">
        Track what you want to find. Tasks can read this list as input.
      </p>
    </div>
    <button
      class="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
      onclick={() => (showForm = true)}
    >
      <Plus class="h-4 w-4" /> Add item
    </button>
  </div>

  {#if loading}
    <div class="text-sm text-muted-foreground">Loading…</div>
  {:else if items.length === 0}
    <div class="rounded-xl border border-dashed border-border bg-card p-10 text-center">
      <Eye class="mx-auto mb-2 h-5 w-5 text-muted-foreground" />
      <div class="text-sm font-medium">Nothing on your watchlist yet</div>
    </div>
  {:else}
    <div class="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
      {#each items as item (item.id)}
        <div class="rounded-xl border border-border bg-card p-4">
          <div class="flex items-start justify-between gap-2">
            <div>
              <div class="text-xs uppercase text-muted-foreground">{item.kind}</div>
              <div class="text-base font-semibold">{item.title}</div>
              {#if item.year}
                <div class="text-xs text-muted-foreground">{item.year}</div>
              {/if}
            </div>
            <button
              class="rounded-md p-1 text-muted-foreground hover:bg-muted hover:text-destructive"
              onclick={() => remove(item.id)}
              aria-label="Remove"
            >
              <Trash2 class="h-4 w-4" />
            </button>
          </div>
          {#if item.target_quality}
            <div class="mt-2 inline-block rounded-full bg-muted px-2 py-0.5 text-xs">
              {item.target_quality}
            </div>
          {/if}
          {#if item.notes}
            <div class="mt-2 text-xs text-muted-foreground">{item.notes}</div>
          {/if}
        </div>
      {/each}
    </div>
  {/if}
</div>

{#if showForm}
  <div class="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-background/80 p-6 backdrop-blur-sm">
    <form
      onsubmit={save}
      class="mt-16 w-full max-w-md rounded-2xl border border-border bg-card p-6 shadow-2xl"
    >
      <div class="mb-4 flex items-center justify-between">
        <h3 class="text-lg font-semibold">Add to watchlist</h3>
        <button
          type="button"
          class="rounded-md p-1 text-muted-foreground hover:bg-muted"
          onclick={() => (showForm = false)}
        >
          ✕
        </button>
      </div>
      <div class="space-y-3">
        <label class="block">
          <span class="mb-1 block text-sm font-medium">Kind</span>
          <select
            bind:value={form.kind}
            class="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
          >
            <option value="series">Series</option>
            <option value="movie">Movie</option>
          </select>
        </label>
        <label class="block">
          <span class="mb-1 block text-sm font-medium">Title</span>
          <input
            type="text"
            required
            bind:value={form.title}
            class="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
          />
        </label>
        <div class="grid grid-cols-2 gap-3">
          <label class="block">
            <span class="mb-1 block text-sm font-medium">Year</span>
            <input
              type="number"
              bind:value={form.year}
              class="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
            />
          </label>
          <label class="block">
            <span class="mb-1 block text-sm font-medium">Quality</span>
            <input
              type="text"
              bind:value={form.target_quality}
              placeholder="1080p"
              class="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
            />
          </label>
        </div>
        <label class="block">
          <span class="mb-1 block text-sm font-medium">Notes</span>
          <textarea
            rows="3"
            bind:value={form.notes}
            class="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
          ></textarea>
        </label>
      </div>
      <div class="mt-4 flex justify-end gap-2">
        <button
          type="button"
          class="rounded-md border border-border bg-background px-4 py-2 text-sm hover:bg-muted"
          onclick={() => (showForm = false)}
        >
          Cancel
        </button>
        <button
          type="submit"
          class="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
        >
          Save
        </button>
      </div>
    </form>
  </div>
{/if}
