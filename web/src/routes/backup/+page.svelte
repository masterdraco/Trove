<script lang="ts">
  import { api } from "$lib/api";
  import {
    Archive,
    Download,
    Upload,
    Loader2,
    AlertTriangle
  } from "lucide-svelte";

  let restoreFile = $state<File | null>(null);
  let restoring = $state(false);
  let restoreMsg = $state<{ ok: boolean; text: string } | null>(null);

  function pickRestoreFile(e: Event) {
    const target = e.currentTarget as HTMLInputElement;
    restoreFile = target.files?.[0] ?? null;
    restoreMsg = null;
  }

  async function doRestore() {
    if (!restoreFile) return;
    if (
      !confirm(
        `Restore from ${restoreFile.name}? This will OVERWRITE your current database and session secret. The current files are backed up to config/.pre-restore/ first, but this is still a destructive operation.`
      )
    )
      return;
    restoring = true;
    restoreMsg = null;
    try {
      const result = await api.backup.restore(restoreFile);
      restoreMsg = {
        ok: true,
        text: `Restored backup from ${result.backup_created_at ?? "unknown time"} (Trove ${result.restored_version ?? "?"}). Reload the page to see your restored data.`
      };
      restoreFile = null;
    } catch (e) {
      const err = e as { detail?: string };
      restoreMsg = { ok: false, text: err.detail ?? "restore failed" };
    } finally {
      restoring = false;
    }
  }
</script>

<div class="max-w-3xl space-y-6">
  <div>
    <h2 class="text-xl font-semibold">Backup & Restore</h2>
    <p class="mt-1 text-sm text-muted-foreground">
      Export or import a complete Trove install (database + session secret).
    </p>
  </div>

  <div class="surface p-6">
    <div class="flex items-center gap-3">
      <div class="flex h-10 w-10 items-center justify-center rounded-xl bg-amber-500/20 text-amber-400">
        <Archive class="h-5 w-5" />
      </div>
      <div>
        <h3 class="text-base font-semibold">Backup & restore</h3>
        <p class="text-xs text-muted-foreground">
          Export or import a complete Trove install (database + session secret).
        </p>
      </div>
    </div>

    <div class="mt-5 grid gap-4 lg:grid-cols-2">
      <div class="rounded-xl border border-border/60 bg-background/40 p-4">
        <div class="mb-2 flex items-center gap-2">
          <Download class="h-4 w-4 text-primary" />
          <span class="text-sm font-semibold">Download backup</span>
        </div>
        <p class="text-xs text-muted-foreground">
          Grabs a zip with your database, session secret, and a manifest. The session secret
          is required to decrypt stored credentials — keep the zip safe.
        </p>
        <a
          href={api.backup.downloadUrl}
          download
          class="btn-primary mt-4 inline-flex"
        >
          <Download class="h-3.5 w-3.5" />
          Download .zip
        </a>
      </div>

      <div class="rounded-xl border border-destructive/30 bg-destructive/5 p-4">
        <div class="mb-2 flex items-center gap-2">
          <Upload class="h-4 w-4 text-destructive" />
          <span class="text-sm font-semibold">Restore from backup</span>
        </div>
        <div class="mb-3 flex items-start gap-1.5 text-xs text-muted-foreground">
          <AlertTriangle class="mt-0.5 h-3 w-3 shrink-0 text-amber-500" />
          <span>
            Destructive. Overwrites your current DB and session secret. The old files are
            moved to <code class="font-mono">config/.pre-restore/</code> as a safety net.
          </span>
        </div>
        <input
          type="file"
          accept=".zip,application/zip"
          onchange={pickRestoreFile}
          class="mt-1 block w-full text-xs text-muted-foreground file:mr-3 file:rounded-md file:border file:border-border file:bg-card file:px-3 file:py-1.5 file:text-xs file:font-medium file:text-foreground hover:file:bg-muted"
        />
        {#if restoreFile}
          <div class="mt-2 text-xs text-muted-foreground">
            Selected: <span class="font-mono">{restoreFile.name}</span> ({(restoreFile.size / 1024).toFixed(1)} KB)
          </div>
        {/if}
        <button
          class="btn-primary mt-4 inline-flex disabled:opacity-60"
          disabled={!restoreFile || restoring}
          onclick={doRestore}
        >
          {#if restoring}
            <Loader2 class="h-3.5 w-3.5 animate-spin" />
          {:else}
            <Upload class="h-3.5 w-3.5" />
          {/if}
          Restore
        </button>
        {#if restoreMsg}
          <div
            class="mt-3 rounded-md border px-3 py-2 text-xs {restoreMsg.ok
              ? 'border-success/30 bg-success/10 text-success'
              : 'border-destructive/30 bg-destructive/10 text-destructive'}"
          >
            {restoreMsg.text}
          </div>
        {/if}
      </div>
    </div>

    <p class="mt-4 text-xs text-muted-foreground">
      Tip: to migrate Trove to a new host, download a backup here, install Trove on the new
      host (run through setup wizard with any throwaway credentials), log in, and restore the
      backup on the new host. All clients, indexers, feeds, tasks, and your original user
      account come with it.
    </p>
  </div>
</div>
