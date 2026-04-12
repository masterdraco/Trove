<script lang="ts">
  import "../app.css";
  import { onMount } from "svelte";
  import { goto } from "$app/navigation";
  import { page } from "$app/stores";
  import { api, type ApiError } from "$lib/api";
  import { currentUser } from "$lib/stores/auth";
  import {
    LayoutDashboard,
    Search,
    Database,
    Download,
    ListChecks,
    Eye,
    History,
    ScrollText,
    Settings,
    Sparkles,
    LogOut,
    Rss,
    BookOpen,
    TrendingUp,
    ChevronDown,
    Info,
    Calendar
  } from "lucide-svelte";

  type NavChild = {
    href: string;
    label: string;
    icon: typeof LayoutDashboard;
    color: string;
  };
  type NavItem = NavChild & { children?: NavChild[] };

  let booting = $state(true);

  const publicRoutes = ["/login", "/setup"];
  const noChromeRoutes = ["/login", "/setup", "/onboarding"];

  let { children } = $props();

  const nav: NavItem[] = [
    { href: "/", label: "Dashboard", icon: LayoutDashboard, color: "text-sky-400" },
    { href: "/discover", label: "Discover", icon: TrendingUp, color: "text-rose-400" },
    { href: "/search", label: "Search", icon: Search, color: "text-cyan-400" },
    { href: "/tasks", label: "Tasks", icon: ListChecks, color: "text-violet-400" },
    { href: "/watchlist", label: "Watchlist", icon: Eye, color: "text-pink-400" },
    { href: "/calendar", label: "Calendar", icon: Calendar, color: "text-indigo-400" },
    { href: "/ai", label: "AI", icon: Sparkles, color: "text-fuchsia-400" },
    { href: "/history", label: "History", icon: History, color: "text-amber-400" },
    { href: "/logs", label: "Logs", icon: ScrollText, color: "text-slate-400" },
    { href: "/docs", label: "Docs", icon: BookOpen, color: "text-teal-400" },
    {
      href: "/settings",
      label: "Settings",
      icon: Settings,
      color: "text-zinc-400",
      children: [
        { href: "/clients", label: "Clients", icon: Download, color: "text-emerald-400" },
        { href: "/indexers", label: "Indexers", icon: Database, color: "text-blue-400" },
        { href: "/feeds", label: "Feeds", icon: Rss, color: "text-orange-400" }
      ]
    },
    { href: "/about", label: "About", icon: Info, color: "text-amber-400" }
  ];

  // Manually-toggled groups. A group is considered expanded if it's in
  // this set OR if the current route is the parent or a child.
  let manuallyExpanded = $state<Set<string>>(new Set());

  function isRouteActive(href: string): boolean {
    if (href === "/") return $page.url.pathname === "/";
    return $page.url.pathname.startsWith(href);
  }

  function isGroupExpanded(item: NavItem): boolean {
    if (manuallyExpanded.has(item.href)) return true;
    if (isRouteActive(item.href)) return true;
    if (item.children?.some((c) => isRouteActive(c.href))) return true;
    return false;
  }

  function toggleGroup(item: NavItem, event: MouseEvent) {
    event.preventDefault();
    event.stopPropagation();
    const next = new Set(manuallyExpanded);
    if (isGroupExpanded(item)) {
      next.delete(item.href);
    } else {
      next.add(item.href);
    }
    manuallyExpanded = next;
  }

  onMount(async () => {
    try {
      const status = await api.authStatus();
      if (status.needs_setup) {
        if ($page.url.pathname !== "/setup") await goto("/setup");
        booting = false;
        return;
      }
      try {
        const me = await api.me();
        currentUser.set(me);
        if ($page.url.pathname === "/login" || $page.url.pathname === "/setup") {
          await goto("/");
        }
        // Redirect to onboarding on fresh installs
        const dismissed = (() => {
          try {
            return localStorage.getItem("trove_onboarding_dismissed") === "1";
          } catch {
            return false;
          }
        })();
        if (
          !dismissed &&
          !noChromeRoutes.includes($page.url.pathname) &&
          $page.url.pathname !== "/onboarding"
        ) {
          try {
            const [cl, idx] = await Promise.all([api.clients.list(), api.indexers.list()]);
            if (cl.length === 0 && idx.length === 0) {
              await goto("/onboarding");
            }
          } catch {}
        }
      } catch (err) {
        const e = err as ApiError;
        if (e?.status === 401 && !publicRoutes.includes($page.url.pathname)) {
          await goto("/login");
        }
      }
    } catch (err) {
      console.error("boot failed", err);
    } finally {
      booting = false;
    }
  });

  async function handleLogout() {
    await api.logout();
    currentUser.set(null);
    await goto("/login");
  }

  const isPublic = $derived(noChromeRoutes.includes($page.url.pathname));
</script>

{#if booting}
  <div class="flex h-full items-center justify-center">
    <div class="flex items-center gap-3 text-sm text-muted-foreground">
      <div class="h-6 w-6 animate-pulse-glow rounded-full bg-gradient-to-br from-primary to-primary-2"></div>
      Loading Trove…
    </div>
  </div>
{:else if isPublic}
  {@render children()}
{:else}
  <div class="flex h-full">
    <aside
      class="flex w-64 shrink-0 flex-col border-r border-border/50 bg-card/30 px-4 py-5 backdrop-blur-xl"
    >
      <div class="mb-6 flex items-center gap-3 px-2">
        <div class="relative flex h-11 w-11 shrink-0 items-center justify-center overflow-hidden rounded-xl">
          <img
            src="/logo-128.png"
            alt="Trove"
            class="h-full w-full object-contain drop-shadow-[0_0_12px_hsl(var(--primary)/0.6)]"
          />
        </div>
        <div>
          <div class="text-base font-bold tracking-tight">
            <span class="text-gradient">Trove</span>
          </div>
          <div class="text-[10px] uppercase tracking-widest text-muted-foreground">
            Media automation
          </div>
        </div>
      </div>

      <nav class="flex-1 space-y-0.5 overflow-y-auto">
        {#each nav as item}
          {@const active = isRouteActive(item.href)}
          {@const Icon = item.icon}
          {#if item.children}
            {@const expanded = isGroupExpanded(item)}
            <div class="relative">
              <a
                href={item.href}
                class="nav-item pr-8 {active ? 'nav-item-active' : 'nav-item-inactive'}"
              >
                <Icon class="h-4 w-4 {active ? item.color : ''}" />
                <span class="font-medium">{item.label}</span>
              </a>
              <button
                type="button"
                class="absolute right-1 top-1/2 flex h-7 w-7 -translate-y-1/2 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-white/[0.06] hover:text-foreground"
                onclick={(e) => toggleGroup(item, e)}
                aria-label={expanded ? "Collapse" : "Expand"}
                aria-expanded={expanded}
              >
                <ChevronDown
                  class="h-3.5 w-3.5 transition-transform {expanded ? 'rotate-180' : ''}"
                />
              </button>
            </div>
            {#if expanded}
              <div class="ml-3 mt-0.5 space-y-0.5 border-l border-border/40 pl-2">
                {#each item.children as child}
                  {@const childActive = isRouteActive(child.href)}
                  {@const ChildIcon = child.icon}
                  <a
                    href={child.href}
                    class="nav-item py-1.5 text-[13px] {childActive
                      ? 'nav-item-active'
                      : 'nav-item-inactive'}"
                  >
                    <ChildIcon class="h-3.5 w-3.5 {childActive ? child.color : ''}" />
                    <span class="font-medium">{child.label}</span>
                  </a>
                {/each}
              </div>
            {/if}
          {:else}
            <a
              href={item.href}
              class="nav-item {active ? 'nav-item-active' : 'nav-item-inactive'}"
            >
              <Icon class="h-4 w-4 {active ? item.color : ''}" />
              <span class="font-medium">{item.label}</span>
            </a>
          {/if}
        {/each}
      </nav>

      <div class="mt-4 border-t border-border/50 pt-4">
        {#if $currentUser}
          <div class="flex items-center justify-between gap-2 rounded-xl bg-card/50 px-3 py-2">
            <div class="flex min-w-0 items-center gap-2">
              <div
                class="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-primary to-primary-2 text-xs font-bold text-white"
              >
                {$currentUser.username.slice(0, 2).toUpperCase()}
              </div>
              <div class="min-w-0">
                <div class="truncate text-sm font-medium">{$currentUser.username}</div>
                <div class="text-[10px] text-muted-foreground">signed in</div>
              </div>
            </div>
            <button
              class="rounded-lg p-2 text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
              onclick={handleLogout}
              aria-label="Log out"
            >
              <LogOut class="h-4 w-4" />
            </button>
          </div>
        {/if}
      </div>
    </aside>

    <main class="min-w-0 flex-1 overflow-auto">
      <div class="sticky top-0 z-30 border-b border-border/40 bg-background/70 backdrop-blur-xl">
        <a
          href="https://www.buymeacoffee.com/MasterDraco"
          target="_blank"
          rel="noopener noreferrer"
          class="group flex w-full items-center justify-center gap-4 bg-gradient-to-r from-primary/10 via-primary-2/15 to-primary/10 px-6 py-4 text-sm font-medium text-foreground/90 transition-all hover:from-primary/15 hover:via-primary-2/25 hover:to-primary/15 hover:text-foreground hover:shadow-[0_4px_32px_-8px_hsl(var(--primary)/0.55)]"
          title="Support Trove development with a coffee ☕"
        >
          <span class="hidden text-base sm:block">Enjoying Trove? Support the project</span>
          <img
            src="/coffee-480.png"
            srcset="/coffee-480.png 1x, /coffee-720.png 2x"
            alt="Buy me a coffee"
            class="h-24 w-auto transition-transform group-hover:scale-105"
            loading="lazy"
          />
        </a>
      </div>
      <div class="mx-auto max-w-[1400px] px-8 py-8 animate-fade-in">
        {@render children()}
      </div>
    </main>
  </div>
{/if}
