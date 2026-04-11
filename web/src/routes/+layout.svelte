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
    BookOpen
  } from "lucide-svelte";

  let booting = $state(true);

  const publicRoutes = ["/login", "/setup"];
  const noChromeRoutes = ["/login", "/setup", "/onboarding"];

  let { children } = $props();

  const nav = [
    { href: "/", label: "Dashboard", icon: LayoutDashboard, color: "text-sky-400" },
    { href: "/search", label: "Search", icon: Search, color: "text-cyan-400" },
    { href: "/indexers", label: "Indexers", icon: Database, color: "text-blue-400" },
    { href: "/feeds", label: "Feeds", icon: Rss, color: "text-orange-400" },
    { href: "/clients", label: "Clients", icon: Download, color: "text-emerald-400" },
    { href: "/tasks", label: "Tasks", icon: ListChecks, color: "text-violet-400" },
    { href: "/watchlist", label: "Watchlist", icon: Eye, color: "text-pink-400" },
    { href: "/history", label: "History", icon: History, color: "text-amber-400" },
    { href: "/logs", label: "Logs", icon: ScrollText, color: "text-slate-400" },
    { href: "/ai", label: "AI", icon: Sparkles, color: "text-fuchsia-400" },
    { href: "/docs", label: "Docs", icon: BookOpen, color: "text-teal-400" },
    { href: "/settings", label: "Settings", icon: Settings, color: "text-zinc-400" }
  ];

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

      <nav class="flex-1 space-y-0.5">
        {#each nav as item}
          {@const active =
            item.href === "/"
              ? $page.url.pathname === "/"
              : $page.url.pathname.startsWith(item.href)}
          {@const Icon = item.icon}
          <a
            href={item.href}
            class="nav-item {active ? 'nav-item-active' : 'nav-item-inactive'}"
          >
            <Icon class="h-4 w-4 {active ? item.color : ''}" />
            <span class="font-medium">{item.label}</span>
          </a>
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
      <div class="mx-auto max-w-[1400px] px-8 py-8 animate-fade-in">
        {@render children()}
      </div>
    </main>
  </div>
{/if}
