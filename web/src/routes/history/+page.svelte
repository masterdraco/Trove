<script lang="ts">
  import { onMount } from "svelte";
  import { api, type TaskOut, type TaskRunOut } from "$lib/api";

  let rows = $state<(TaskRunOut & { task_name: string })[]>([]);
  let loading = $state(true);

  async function load() {
    loading = true;
    try {
      const tasks = await api.tasks.list();
      const all: (TaskRunOut & { task_name: string })[] = [];
      for (const task of tasks) {
        try {
          const runs = await api.tasks.runs(task.id);
          for (const r of runs) all.push({ ...r, task_name: task.name });
        } catch {}
      }
      all.sort((a, b) => (a.started_at > b.started_at ? -1 : 1));
      rows = all;
    } finally {
      loading = false;
    }
  }

  onMount(load);
</script>

<div class="space-y-4">
  <div>
    <h2 class="text-xl font-semibold">History</h2>
    <p class="mt-1 text-sm text-muted-foreground">All task runs in reverse chronological order.</p>
  </div>

  {#if loading}
    <div class="text-sm text-muted-foreground">Loading…</div>
  {:else if rows.length === 0}
    <div class="rounded-xl border border-dashed border-border bg-card p-10 text-center text-sm text-muted-foreground">
      No history yet.
    </div>
  {:else}
    <div class="overflow-hidden rounded-xl border border-border bg-card">
      <table class="w-full text-sm">
        <thead class="bg-muted/50 text-left text-xs uppercase tracking-wide text-muted-foreground">
          <tr>
            <th class="px-4 py-3">Time</th>
            <th class="px-4 py-3">Task</th>
            <th class="px-4 py-3">Status</th>
            <th class="px-4 py-3">Accepted</th>
            <th class="px-4 py-3">Considered</th>
          </tr>
        </thead>
        <tbody>
          {#each rows as row}
            <tr class="border-t border-border">
              <td class="px-4 py-3 font-mono text-xs">{row.started_at}</td>
              <td class="px-4 py-3">{row.task_name}</td>
              <td class="px-4 py-3">
                <span
                  class="rounded-full px-2 py-0.5 text-xs {row.status === 'success'
                    ? 'bg-green-500/10 text-green-600'
                    : 'bg-destructive/10 text-destructive'}"
                >
                  {row.status}
                </span>
                {#if row.dry_run}
                  <span class="ml-1 text-[10px] text-muted-foreground">dry</span>
                {/if}
              </td>
              <td class="px-4 py-3">{row.accepted}</td>
              <td class="px-4 py-3">{row.considered}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}
</div>
