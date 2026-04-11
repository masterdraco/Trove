<script lang="ts">
  import { goto } from "$app/navigation";
  import { api, type ApiError } from "$lib/api";
  import { currentUser } from "$lib/stores/auth";
  import { Sparkles } from "lucide-svelte";

  let username = $state("");
  let password = $state("");
  let confirm = $state("");
  let error = $state<string | null>(null);
  let submitting = $state(false);

  async function handleSubmit(event: Event) {
    event.preventDefault();
    error = null;
    if (password.length < 8) {
      error = "Password must be at least 8 characters.";
      return;
    }
    if (password !== confirm) {
      error = "Passwords do not match.";
      return;
    }
    submitting = true;
    try {
      const user = await api.setup(username, password);
      currentUser.set(user);
      await goto("/");
    } catch (e) {
      const err = e as ApiError;
      if (err?.detail === "setup_already_completed") {
        error = "Setup has already been completed. Please sign in.";
        setTimeout(() => goto("/login"), 1500);
      } else {
        error = "Setup failed.";
      }
    } finally {
      submitting = false;
    }
  }
</script>

<div class="flex h-full items-center justify-center p-6">
  <form onsubmit={handleSubmit} class="surface w-full max-w-md p-8 animate-fade-in glow-primary">
    <div class="mb-8 flex flex-col items-center text-center">
      <img
        src="/logo-256.png"
        alt="Trove"
        class="h-24 w-24 object-contain drop-shadow-[0_0_32px_hsl(var(--primary)/0.7)]"
      />
      <div class="mt-4 text-2xl font-bold">
        Welcome to <span class="text-gradient">Trove</span>
      </div>
      <div class="mt-1 text-[11px] uppercase tracking-widest text-muted-foreground">
        Create your admin account
      </div>
    </div>

    <label class="mb-4 block">
      <span class="mb-1.5 block text-sm font-medium">Username</span>
      <input type="text" bind:value={username} autocomplete="username" required class="input-base" />
    </label>
    <label class="mb-4 block">
      <span class="mb-1.5 block text-sm font-medium">Password</span>
      <input
        type="password"
        bind:value={password}
        autocomplete="new-password"
        required
        minlength={8}
        class="input-base"
      />
    </label>
    <label class="mb-5 block">
      <span class="mb-1.5 block text-sm font-medium">Confirm password</span>
      <input
        type="password"
        bind:value={confirm}
        autocomplete="new-password"
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
      {submitting ? "Creating account…" : "Create admin account"}
    </button>
  </form>
</div>
