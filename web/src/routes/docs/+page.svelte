<script lang="ts">
  import { onMount } from "svelte";
  import { page } from "$app/stores";
  import { goto } from "$app/navigation";
  import { marked } from "marked";
  import { api } from "$lib/api";
  import { BookOpen, Loader2 } from "lucide-svelte";

  type DocMeta = Awaited<ReturnType<typeof api.docs.list>>[number];
  type DocContent = Awaited<ReturnType<typeof api.docs.get>>;

  let docs = $state<DocMeta[]>([]);
  let current = $state<DocContent | null>(null);
  let loading = $state(true);
  let loadingDoc = $state(false);
  let error = $state<string | null>(null);

  marked.setOptions({ breaks: true, gfm: true });

  async function loadList() {
    loading = true;
    try {
      docs = await api.docs.list();
      const slug = $page.url.searchParams.get("slug") || docs[0]?.slug;
      if (slug) await loadDoc(slug);
    } catch (e) {
      error = (e as { detail?: string }).detail ?? "Failed to load docs";
    } finally {
      loading = false;
    }
  }

  async function loadDoc(slug: string) {
    loadingDoc = true;
    try {
      current = await api.docs.get(slug);
      // Update URL without a full navigation
      const url = new URL(window.location.href);
      url.searchParams.set("slug", slug);
      history.replaceState(null, "", url.toString());
    } catch (e) {
      error = (e as { detail?: string }).detail ?? "Failed to load doc";
    } finally {
      loadingDoc = false;
    }
  }

  function selectDoc(slug: string) {
    void loadDoc(slug);
  }

  onMount(loadList);

  // Rewrite relative links inside markdown to open the matching doc
  function handleDocClick(event: Event) {
    const target = event.target as HTMLElement;
    if (target.tagName !== "A") return;
    const href = (target as HTMLAnchorElement).getAttribute("href");
    if (!href || href.startsWith("http") || href.startsWith("#") || href.startsWith("/")) return;
    event.preventDefault();
    selectDoc(href);
  }

  const html = $derived(current ? marked.parse(current.markdown) : "");
</script>

<div class="flex gap-8">
  <!-- Sidebar with doc list -->
  <aside class="surface sticky top-0 w-60 shrink-0 self-start p-4">
    <div class="mb-3 flex items-center gap-2 px-2">
      <BookOpen class="h-4 w-4 text-primary" />
      <h2 class="text-sm font-semibold">Documentation</h2>
    </div>
    {#if loading}
      <div class="px-2 text-xs text-muted-foreground">Loading…</div>
    {:else}
      <nav class="space-y-0.5">
        {#each docs as doc (doc.slug)}
          <button
            class="nav-item w-full {current?.slug === doc.slug
              ? 'nav-item-active'
              : 'nav-item-inactive'}"
            onclick={() => selectDoc(doc.slug)}
          >
            <span class="truncate text-sm">{doc.title}</span>
          </button>
        {/each}
      </nav>
    {/if}
  </aside>

  <!-- Content -->
  <div class="min-w-0 flex-1">
    {#if loadingDoc || (loading && !current)}
      <div class="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 class="h-4 w-4 animate-spin" /> Loading document…
      </div>
    {:else if error}
      <div class="rounded-xl border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
        {error}
      </div>
    {:else if current}
      <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
      <!-- svelte-ignore a11y_click_events_have_key_events -->
      <article
        class="doc-content max-w-3xl"
        onclick={handleDocClick}
        role="region"
        aria-label={current.title}
      >
        {@html html}
      </article>
    {/if}
  </div>
</div>

<style>
  .doc-content :global(h1) {
    font-size: 2.25rem;
    font-weight: 700;
    letter-spacing: -0.025em;
    margin-bottom: 0.75rem;
    background-image: linear-gradient(
      135deg,
      hsl(var(--primary)) 0%,
      hsl(var(--primary-2)) 60%,
      hsl(var(--accent)) 100%
    );
    -webkit-background-clip: text;
    background-clip: text;
    -webkit-text-fill-color: transparent;
  }
  .doc-content :global(h2) {
    font-size: 1.5rem;
    font-weight: 700;
    letter-spacing: -0.01em;
    margin-top: 2.25rem;
    margin-bottom: 0.75rem;
    padding-bottom: 0.5rem;
    border-bottom: 1px solid hsl(var(--border));
  }
  .doc-content :global(h3) {
    font-size: 1.125rem;
    font-weight: 600;
    margin-top: 1.5rem;
    margin-bottom: 0.5rem;
  }
  .doc-content :global(p) {
    font-size: 0.9rem;
    line-height: 1.7;
    color: hsl(var(--foreground));
    margin-bottom: 0.875rem;
  }
  .doc-content :global(a) {
    color: hsl(var(--primary));
    text-decoration: underline;
    text-decoration-color: hsl(var(--primary) / 0.4);
    text-underline-offset: 3px;
  }
  .doc-content :global(a:hover) {
    text-decoration-color: hsl(var(--primary));
  }
  .doc-content :global(ul),
  .doc-content :global(ol) {
    padding-left: 1.25rem;
    margin-bottom: 0.875rem;
  }
  .doc-content :global(ul) {
    list-style: disc;
  }
  .doc-content :global(ol) {
    list-style: decimal;
  }
  .doc-content :global(li) {
    font-size: 0.9rem;
    line-height: 1.7;
    margin-bottom: 0.25rem;
  }
  .doc-content :global(code) {
    font-family: "JetBrains Mono", ui-monospace, monospace;
    font-size: 0.8125rem;
    background: hsl(var(--muted));
    padding: 0.125rem 0.375rem;
    border-radius: 0.375rem;
    border: 1px solid hsl(var(--border));
  }
  .doc-content :global(pre) {
    background: hsl(var(--card));
    border: 1px solid hsl(var(--border));
    border-radius: 0.75rem;
    padding: 1rem;
    overflow-x: auto;
    margin-bottom: 1rem;
    font-size: 0.8125rem;
  }
  .doc-content :global(pre code) {
    background: transparent;
    border: none;
    padding: 0;
    font-size: inherit;
  }
  .doc-content :global(blockquote) {
    border-left: 3px solid hsl(var(--primary));
    padding: 0.5rem 1rem;
    margin-bottom: 1rem;
    color: hsl(var(--muted-foreground));
    background: hsl(var(--primary) / 0.05);
    border-radius: 0 0.5rem 0.5rem 0;
  }
  .doc-content :global(table) {
    width: 100%;
    border-collapse: collapse;
    margin-bottom: 1rem;
    font-size: 0.8125rem;
  }
  .doc-content :global(th),
  .doc-content :global(td) {
    text-align: left;
    padding: 0.5rem 0.75rem;
    border-bottom: 1px solid hsl(var(--border));
  }
  .doc-content :global(th) {
    font-weight: 600;
    color: hsl(var(--muted-foreground));
    text-transform: uppercase;
    font-size: 0.6875rem;
    letter-spacing: 0.05em;
  }
  .doc-content :global(strong) {
    color: hsl(var(--foreground));
    font-weight: 600;
  }
  .doc-content :global(hr) {
    border: none;
    border-top: 1px solid hsl(var(--border));
    margin: 2rem 0;
  }
</style>
