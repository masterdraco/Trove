<script lang="ts">
  import { goto } from "$app/navigation";
  import { api, type ApiError } from "$lib/api";
  import { currentUser } from "$lib/stores/auth";
  import { Sparkles } from "lucide-svelte";

  let username = $state("");
  let password = $state("");
  let error = $state<string | null>(null);
  let submitting = $state(false);

  async function handleSubmit(event: Event) {
    event.preventDefault();
    error = null;
    submitting = true;
    try {
      const user = await api.login(username, password);
      currentUser.set(user);
      await goto("/");
    } catch (e) {
      const err = e as ApiError;
      error = err?.detail === "invalid_credentials" ? "Wrong username or password." : "Login failed.";
    } finally {
      submitting = false;
    }
  }
</script>

<div class="flex h-full items-center justify-center p-6">
  <form
    onsubmit={handleSubmit}
    class="surface w-full max-w-sm p-8 animate-fade-in glow-primary"
  >
    <div class="mb-8 flex flex-col items-center text-center">
      <img
        src="/logo-256.png"
        alt="Trove"
        class="h-20 w-20 object-contain drop-shadow-[0_0_24px_hsl(var(--primary)/0.7)]"
      />
      <div class="mt-4 text-2xl font-bold">
        <span class="text-gradient">Trove</span>
      </div>
      <div class="mt-1 text-[11px] uppercase tracking-widest text-muted-foreground">
        Sign in to continue
      </div>
    </div>

    <label class="mb-4 block">
      <span class="mb-1.5 block text-sm font-medium">Username</span>
      <input
        type="text"
        bind:value={username}
        autocomplete="username"
        required
        class="input-base"
      />
    </label>
    <label class="mb-5 block">
      <span class="mb-1.5 block text-sm font-medium">Password</span>
      <input
        type="password"
        bind:value={password}
        autocomplete="current-password"
        required
        class="input-base"
      />
    </label>

    {#if error}
      <div class="mb-4 rounded-xl border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
        {error}
      </div>
    {/if}

    <button type="submit" disabled={submitting} class="btn-primary w-full">
      {submitting ? "Signing in…" : "Sign in"}
    </button>
  </form>
</div>
