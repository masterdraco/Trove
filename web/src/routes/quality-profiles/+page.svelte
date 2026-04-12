<script lang="ts">
  import { onMount } from "svelte";
  import { api, type QualityProfile, type QualityProfilesOut } from "$lib/api";
  import {
    Plus,
    Trash2,
    Save,
    Star,
    Loader2,
    CheckCircle2,
    Award
  } from "lucide-svelte";

  let store = $state<QualityProfilesOut | null>(null);
  let loading = $state(true);
  let selected = $state<string | null>(null);
  let saving = $state(false);
  let showNew = $state(false);
  let newName = $state("");

  let editProfile = $state<QualityProfile | null>(null);

  const QUALITY_PRESETS: Record<string, number> = {
    "2160p": 4, "4k": 4, "uhd": 4,
    "1080p": 3,
    "720p": 2,
    "576p": 1, "480p": 1, "sd": 1
  };

  const SOURCE_PRESETS: Record<string, number> = {
    "remux": 6, "bluray": 5, "blu-ray": 5,
    "bdrip": 4, "web-dl": 4, "webdl": 4,
    "webrip": 3, "hdtv": 2, "dvdrip": 1,
    "hdts": -5, "telesync": -5, "cam": -10
  };

  const CODEC_PRESETS: Record<string, number> = {
    "x265": 2, "h265": 2, "h.265": 2, "hevc": 2,
    "x264": 1, "h264": 1
  };

  const AUDIO_PRESETS: Record<string, number> = {
    "atmos": 3, "truehd": 3, "dts-hd": 3, "dts-hd.ma": 3, "dtshd": 3,
    "ddp5.1": 2, "dd+5.1": 2, "eac3": 2,
    "dd5.1": 1, "ac3": 1, "aac5.1": 1,
    "aac": 0, "mp3": -1
  };

  async function load() {
    loading = true;
    try {
      store = await api.qualityProfiles.list();
    } finally {
      loading = false;
    }
  }

  function selectProfile(name: string) {
    selected = name;
    const p = store?.profiles[name];
    if (p) {
      editProfile = JSON.parse(JSON.stringify(p));
    }
  }

  function newProfile() {
    showNew = true;
    newName = "";
  }

  async function createProfile() {
    if (!newName.trim()) return;
    const profile: QualityProfile = {
      name: newName.trim(),
      quality_tiers: { ...QUALITY_PRESETS },
      source_tiers: { ...SOURCE_PRESETS },
      codec_bonus: { ...CODEC_PRESETS },
      audio_bonus: { ...AUDIO_PRESETS },
      reject_tokens: ["cam", "telesync", "hdcam", "workprint"],
      prefer_quality: "1080p",
      min_acceptable_tier: 0
    };
    saving = true;
    try {
      await api.qualityProfiles.upsert(profile.name, profile);
      await load();
      selectProfile(profile.name);
      showNew = false;
    } finally {
      saving = false;
    }
  }

  async function saveProfile() {
    if (!editProfile) return;
    saving = true;
    try {
      await api.qualityProfiles.upsert(editProfile.name, editProfile);
      await load();
    } finally {
      saving = false;
    }
  }

  async function deleteProfile(name: string) {
    if (!confirm(`Delete profile "${name}"?`)) return;
    try {
      await api.qualityProfiles.remove(name);
      if (selected === name) {
        selected = null;
        editProfile = null;
      }
      await load();
    } catch (e) {
      alert((e as { detail?: string }).detail ?? "Cannot delete");
    }
  }

  async function setDefault(name: string) {
    await api.qualityProfiles.setDefault(name);
    await load();
  }

  function tierLabel(tier: number): string {
    if (tier >= 4) return "2160p";
    if (tier === 3) return "1080p";
    if (tier === 2) return "720p";
    if (tier === 1) return "SD";
    return "Any";
  }

  function updateTier(table: Record<string, number>, key: string, val: string) {
    const n = parseInt(val, 10);
    if (!isNaN(n)) table[key] = n;
  }

  function addRejectToken() {
    if (!editProfile) return;
    const tok = prompt("Token to reject (e.g. cam, ts):");
    if (tok && !editProfile.reject_tokens.includes(tok.toLowerCase())) {
      editProfile.reject_tokens = [...editProfile.reject_tokens, tok.toLowerCase()];
    }
  }

  function removeRejectToken(tok: string) {
    if (!editProfile) return;
    editProfile.reject_tokens = editProfile.reject_tokens.filter((t) => t !== tok);
  }

  onMount(load);
</script>

<div class="max-w-4xl space-y-6">
  <div class="flex items-center justify-between">
    <div>
      <h2 class="text-xl font-semibold">Quality Profiles</h2>
      <p class="mt-1 text-sm text-muted-foreground">
        Define ranking weights for quality, source, and codec. Tasks use these to pick the best release.
      </p>
    </div>
    <button
      class="inline-flex items-center gap-1 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90"
      onclick={newProfile}
    >
      <Plus class="h-3.5 w-3.5" /> New profile
    </button>
  </div>

  {#if loading}
    <div class="text-sm text-muted-foreground">Loading...</div>
  {:else if store}
    <div class="grid gap-6 lg:grid-cols-[280px_1fr]">
      <!-- Profile list -->
      <div class="space-y-1">
        {#each Object.entries(store.profiles) as [name, profile] (name)}
          <button
            class="flex w-full items-center justify-between rounded-md border border-border bg-card px-3 py-2 text-left text-sm transition-colors {selected === name
              ? 'border-primary bg-primary/5'
              : 'hover:bg-muted'}"
            onclick={() => selectProfile(name)}
          >
            <div class="min-w-0">
              <div class="flex items-center gap-2 font-medium">
                {name}
                {#if store.default === name}
                  <Star class="h-3 w-3 fill-amber-400 text-amber-400" />
                {/if}
              </div>
              <div class="text-xs text-muted-foreground">
                prefer {profile.prefer_quality ?? "any"} · {Object.keys(profile.quality_tiers).length} tiers
              </div>
            </div>
          </button>
        {/each}

        {#if showNew}
          <div class="rounded-md border border-primary bg-primary/5 p-3">
            <input
              type="text"
              bind:value={newName}
              placeholder="Profile name"
              class="w-full rounded-md border border-input bg-background px-3 py-1.5 text-sm outline-none ring-ring focus:ring-2"
            />
            <div class="mt-2 flex gap-2">
              <button
                class="rounded-md bg-primary px-3 py-1 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-60"
                onclick={createProfile}
                disabled={saving || !newName.trim()}
              >
                Create
              </button>
              <button
                class="rounded-md border border-border bg-background px-3 py-1 text-xs hover:bg-muted"
                onclick={() => (showNew = false)}
              >
                Cancel
              </button>
            </div>
          </div>
        {/if}
      </div>

      <!-- Profile editor -->
      <div>
        {#if editProfile}
          <div class="space-y-5">
            <div class="rounded-xl border border-border bg-card p-5">
              <div class="flex items-center justify-between">
                <h3 class="flex items-center gap-2 text-base font-semibold">
                  <Award class="h-4 w-4 text-primary" />
                  {editProfile.name}
                </h3>
                <div class="flex gap-2">
                  {#if store.default !== editProfile.name}
                    <button
                      class="inline-flex items-center gap-1 rounded-md border border-border bg-background px-3 py-1.5 text-xs hover:bg-muted"
                      onclick={() => setDefault(editProfile!.name)}
                    >
                      <Star class="h-3.5 w-3.5" /> Set default
                    </button>
                  {:else}
                    <span class="inline-flex items-center gap-1 rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-1.5 text-xs text-amber-400">
                      <Star class="h-3.5 w-3.5 fill-current" /> Default
                    </span>
                  {/if}
                  <button
                    class="inline-flex items-center gap-1 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-60"
                    onclick={saveProfile}
                    disabled={saving}
                  >
                    {#if saving}
                      <Loader2 class="h-3.5 w-3.5 animate-spin" />
                    {:else}
                      <Save class="h-3.5 w-3.5" />
                    {/if}
                    Save
                  </button>
                  {#if editProfile.name !== "default-2160p"}
                    <button
                      class="inline-flex items-center gap-1 rounded-md border border-border bg-background px-3 py-1.5 text-xs text-destructive hover:bg-destructive/10"
                      onclick={() => deleteProfile(editProfile!.name)}
                    >
                      <Trash2 class="h-3.5 w-3.5" />
                    </button>
                  {/if}
                </div>
              </div>

              <!-- Prefer quality -->
              <div class="mt-4">
                <label class="block text-sm font-medium">Preferred quality</label>
                <p class="text-xs text-muted-foreground">Soft bonus (+500 score) for releases matching this quality.</p>
                <select
                  class="mt-1 rounded-md border border-input bg-background px-3 py-1.5 text-sm"
                  value={editProfile.prefer_quality ?? ""}
                  onchange={(e) => { if (editProfile) editProfile.prefer_quality = (e.currentTarget as HTMLSelectElement).value || null; }}
                >
                  <option value="">Any</option>
                  <option value="2160p">2160p (4K)</option>
                  <option value="1080p">1080p</option>
                  <option value="720p">720p</option>
                </select>
              </div>
            </div>

            <!-- Quality tiers -->
            <div class="rounded-xl border border-border bg-card p-5">
              <h4 class="text-sm font-semibold">Quality tiers</h4>
              <p class="text-xs text-muted-foreground">Higher weight = better. Used for ranking and upgrade cutoff.</p>
              <div class="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
                {#each Object.entries(editProfile.quality_tiers) as [key, val] (key)}
                  <div class="flex items-center gap-2 rounded-md border border-border bg-background px-2 py-1.5">
                    <span class="flex-1 font-mono text-xs">{key}</span>
                    <input
                      type="number"
                      value={val}
                      oninput={(e) => updateTier(editProfile!.quality_tiers, key, (e.currentTarget as HTMLInputElement).value)}
                      class="w-14 rounded border border-input bg-muted/40 px-2 py-0.5 text-center font-mono text-xs"
                    />
                  </div>
                {/each}
              </div>
            </div>

            <!-- Source tiers -->
            <div class="rounded-xl border border-border bg-card p-5">
              <h4 class="text-sm font-semibold">Source tiers</h4>
              <p class="text-xs text-muted-foreground">Remux &gt; BluRay &gt; WEB-DL &gt; HDTV &gt; CAM. Negative = penalty.</p>
              <div class="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
                {#each Object.entries(editProfile.source_tiers) as [key, val] (key)}
                  <div class="flex items-center gap-2 rounded-md border border-border bg-background px-2 py-1.5">
                    <span class="flex-1 font-mono text-xs">{key}</span>
                    <input
                      type="number"
                      value={val}
                      oninput={(e) => updateTier(editProfile!.source_tiers, key, (e.currentTarget as HTMLInputElement).value)}
                      class="w-14 rounded border border-input bg-muted/40 px-2 py-0.5 text-center font-mono text-xs"
                    />
                  </div>
                {/each}
              </div>
            </div>

            <!-- Codec bonus -->
            <div class="rounded-xl border border-border bg-card p-5">
              <h4 class="text-sm font-semibold">Codec bonus</h4>
              <p class="text-xs text-muted-foreground">Extra points for preferred codecs (x265/HEVC preferred).</p>
              <div class="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
                {#each Object.entries(editProfile.codec_bonus) as [key, val] (key)}
                  <div class="flex items-center gap-2 rounded-md border border-border bg-background px-2 py-1.5">
                    <span class="flex-1 font-mono text-xs">{key}</span>
                    <input
                      type="number"
                      value={val}
                      oninput={(e) => updateTier(editProfile!.codec_bonus, key, (e.currentTarget as HTMLInputElement).value)}
                      class="w-14 rounded border border-input bg-muted/40 px-2 py-0.5 text-center font-mono text-xs"
                    />
                  </div>
                {/each}
              </div>
            </div>

            <!-- Audio bonus -->
            <div class="rounded-xl border border-border bg-card p-5">
              <h4 class="text-sm font-semibold">Audio bonus</h4>
              <p class="text-xs text-muted-foreground">Atmos/TrueHD &gt; DDP/EAC3 &gt; DD/AC3 &gt; AAC. Negative = penalty.</p>
              <div class="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
                {#each Object.entries(editProfile.audio_bonus || {}) as [key, val] (key)}
                  <div class="flex items-center gap-2 rounded-md border border-border bg-background px-2 py-1.5">
                    <span class="flex-1 font-mono text-xs">{key}</span>
                    <input
                      type="number"
                      value={val}
                      oninput={(e) => updateTier(editProfile!.audio_bonus, key, (e.currentTarget as HTMLInputElement).value)}
                      class="w-14 rounded border border-input bg-muted/40 px-2 py-0.5 text-center font-mono text-xs"
                    />
                  </div>
                {/each}
              </div>
            </div>

            <!-- Reject tokens -->
            <div class="rounded-xl border border-border bg-card p-5">
              <div class="flex items-center justify-between">
                <div>
                  <h4 class="text-sm font-semibold">Reject tokens</h4>
                  <p class="text-xs text-muted-foreground">Releases containing these words are automatically rejected.</p>
                </div>
                <button
                  class="inline-flex items-center gap-1 rounded-md border border-border bg-background px-2 py-1 text-xs hover:bg-muted"
                  onclick={addRejectToken}
                >
                  <Plus class="h-3 w-3" /> Add
                </button>
              </div>
              <div class="mt-3 flex flex-wrap gap-1.5">
                {#each editProfile.reject_tokens as tok (tok)}
                  <span class="inline-flex items-center gap-1 rounded-full border border-destructive/30 bg-destructive/10 px-2.5 py-0.5 text-xs text-destructive">
                    {tok}
                    <button
                      class="ml-0.5 hover:text-foreground"
                      onclick={() => removeRejectToken(tok)}
                    >x</button>
                  </span>
                {/each}
              </div>
            </div>
          </div>
        {:else}
          <div class="rounded-xl border border-dashed border-border bg-card p-10 text-center text-sm text-muted-foreground">
            Select a profile to edit, or create a new one.
          </div>
        {/if}
      </div>
    </div>
  {/if}
</div>
