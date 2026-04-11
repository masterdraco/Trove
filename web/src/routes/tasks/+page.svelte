<script lang="ts">
  import { onMount } from "svelte";
  import { api, type TaskOut, type TaskRunOut } from "$lib/api";
  import { Plus, Play, FlaskConical, Trash2, ListChecks } from "lucide-svelte";

  let tasks = $state<TaskOut[]>([]);
  let loading = $state(true);
  let selected = $state<TaskOut | null>(null);
  let runs = $state<TaskRunOut[]>([]);
  let showForm = $state(false);
  let saving = $state(false);
  let running = $state(false);

  let form = $state({
    name: "",
    schedule_cron: "",
    enabled: true,
    config_yaml: defaultYaml()
  });

  function defaultYaml(): string {
    return `inputs:
  - kind: search
    query: ubuntu
    categories: [other]

filters:
  min_seeders: 3
  reject: [cam, telesync]

outputs:
  - my-client-name
`;
  }

  async function load() {
    loading = true;
    tasks = await api.tasks.list();
    loading = false;
  }

  async function loadRuns(task: TaskOut) {
    runs = await api.tasks.runs(task.id);
  }

  async function select_(task: TaskOut) {
    selected = task;
    form = {
      name: task.name,
      schedule_cron: task.schedule_cron ?? "",
      enabled: task.enabled,
      config_yaml: task.config_yaml
    };
    await loadRuns(task);
  }

  onMount(load);

  function newTask() {
    selected = null;
    showForm = true;
    form = {
      name: "",
      schedule_cron: "",
      enabled: true,
      config_yaml: defaultYaml()
    };
  }

  async function save() {
    saving = true;
    try {
      if (selected) {
        await api.tasks.update(selected.id, {
          name: form.name,
          enabled: form.enabled,
          schedule_cron: form.schedule_cron || null,
          config_yaml: form.config_yaml
        });
      } else {
        await api.tasks.create({
          name: form.name,
          enabled: form.enabled,
          schedule_cron: form.schedule_cron || null,
          config_yaml: form.config_yaml
        });
      }
      showForm = false;
      await load();
    } finally {
      saving = false;
    }
  }

  async function run(dry: boolean) {
    if (!selected) return;
    running = true;
    try {
      await api.tasks.run(selected.id, dry);
      await loadRuns(selected);
      await load();
    } finally {
      running = false;
    }
  }

  async function remove(task: TaskOut) {
    if (!confirm(`Delete task "${task.name}"?`)) return;
    await api.tasks.remove(task.id);
    if (selected?.id === task.id) selected = null;
    await load();
  }
</script>

<div class="grid gap-6 lg:grid-cols-[320px_1fr]">
  <!-- Left: task list -->
  <div class="space-y-3">
    <div class="flex items-center justify-between">
      <h2 class="text-lg font-semibold">Tasks</h2>
      <button
        class="inline-flex items-center gap-1 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90"
        onclick={newTask}
      >
        <Plus class="h-3.5 w-3.5" /> New
      </button>
    </div>
    {#if loading}
      <div class="text-sm text-muted-foreground">Loading…</div>
    {:else if tasks.length === 0}
      <div class="rounded-xl border border-dashed border-border bg-card p-6 text-center text-sm text-muted-foreground">
        <ListChecks class="mx-auto mb-2 h-5 w-5" />
        No tasks yet.
      </div>
    {:else}
      <div class="space-y-1">
        {#each tasks as task (task.id)}
          <button
            class="flex w-full items-center justify-between rounded-md border border-border bg-card px-3 py-2 text-left text-sm transition-colors {selected?.id ===
            task.id
              ? 'border-primary bg-primary/5'
              : 'hover:bg-muted'}"
            onclick={() => select_(task)}
          >
            <div class="min-w-0">
              <div class="truncate font-medium">{task.name}</div>
              <div class="truncate text-xs text-muted-foreground">
                {task.schedule_cron ?? "manual"} · {task.last_run_status ?? "never run"}
              </div>
            </div>
            {#if !task.enabled}
              <span class="ml-2 text-[10px] uppercase text-muted-foreground">off</span>
            {/if}
          </button>
        {/each}
      </div>
    {/if}
  </div>

  <!-- Right: editor -->
  <div class="space-y-4">
    {#if showForm || selected}
      <div class="rounded-xl border border-border bg-card p-5 shadow-sm">
        <div class="flex items-center justify-between">
          <h3 class="text-lg font-semibold">
            {selected ? `Edit: ${selected.name}` : "New task"}
          </h3>
          <div class="flex gap-2">
            {#if selected}
              <button
                class="inline-flex items-center gap-1 rounded-md border border-border bg-background px-3 py-1.5 text-xs hover:bg-muted"
                onclick={() => run(true)}
                disabled={running}
              >
                <FlaskConical class="h-3.5 w-3.5" /> Dry run
              </button>
              <button
                class="inline-flex items-center gap-1 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90"
                onclick={() => run(false)}
                disabled={running}
              >
                <Play class="h-3.5 w-3.5" /> Run now
              </button>
              <button
                class="inline-flex items-center gap-1 rounded-md border border-border bg-background px-3 py-1.5 text-xs text-destructive hover:bg-destructive/10"
                onclick={() => remove(selected!)}
              >
                <Trash2 class="h-3.5 w-3.5" /> Delete
              </button>
            {/if}
          </div>
        </div>

        <div class="mt-4 grid grid-cols-2 gap-3">
          <label class="block">
            <span class="mb-1 block text-sm font-medium">Name</span>
            <input
              type="text"
              bind:value={form.name}
              class="w-full rounded-md border border-input bg-background px-3 py-2 text-sm outline-none ring-ring focus:ring-2"
            />
          </label>
          <label class="block">
            <span class="mb-1 block text-sm font-medium">Cron (UTC)</span>
            <input
              type="text"
              bind:value={form.schedule_cron}
              placeholder="0 */2 * * *"
              class="w-full rounded-md border border-input bg-background px-3 py-2 font-mono text-xs outline-none ring-ring focus:ring-2"
            />
          </label>
          <label class="col-span-2 flex items-center gap-2 text-sm">
            <input type="checkbox" bind:checked={form.enabled} />
            Enabled
          </label>
          <label class="col-span-2 block">
            <span class="mb-1 block text-sm font-medium">Task YAML</span>
            <textarea
              bind:value={form.config_yaml}
              rows="14"
              class="w-full rounded-md border border-input bg-background px-3 py-2 font-mono text-xs outline-none ring-ring focus:ring-2"
            ></textarea>
          </label>
        </div>

        <div class="mt-4 flex justify-end gap-2">
          <button
            class="rounded-md border border-border bg-background px-4 py-2 text-sm hover:bg-muted"
            onclick={() => {
              showForm = false;
              selected = null;
            }}
          >
            Cancel
          </button>
          <button
            class="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-60"
            onclick={save}
            disabled={saving}
          >
            {saving ? "Saving…" : "Save"}
          </button>
        </div>
      </div>

      {#if selected && runs.length > 0}
        <div class="rounded-xl border border-border bg-card p-5">
          <h3 class="text-sm font-semibold">Recent runs</h3>
          <div class="mt-3 space-y-2">
            {#each runs as run}
              <details class="rounded-md border border-border bg-background">
                <summary class="cursor-pointer px-3 py-2 text-xs">
                  <span class="font-mono">{run.started_at}</span>
                  · {run.status}
                  · {run.accepted}/{run.considered}
                  {run.dry_run ? "(dry)" : ""}
                </summary>
                <pre class="max-h-80 overflow-auto whitespace-pre-wrap px-3 py-2 font-mono text-[11px] text-muted-foreground">{run.log}</pre>
              </details>
            {/each}
          </div>
        </div>
      {/if}
    {:else}
      <div class="rounded-xl border border-dashed border-border bg-card p-10 text-center text-sm text-muted-foreground">
        Select a task or create a new one.
      </div>
    {/if}
  </div>
</div>
