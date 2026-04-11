<script lang="ts">
  import { onMount } from "svelte";
  import { goto } from "$app/navigation";
  import { api } from "$lib/api";
  import {
    Sparkles,
    Send,
    Loader2,
    CheckCircle2,
    XCircle,
    Wand2,
    AlertTriangle
  } from "lucide-svelte";

  type Proposal = {
    intent: string;
    description: string;
    preview: Record<string, unknown>;
    params: Record<string, unknown>;
    requires_confirmation: boolean;
    message: string | null;
    warnings: string[];
  };

  type Msg =
    | { role: "user"; content: string }
    | { role: "assistant"; content: string }
    | { role: "proposal"; proposal: Proposal; status: "pending" | "executed" | "cancelled"; result?: string };

  let status = $state<{ enabled: boolean; endpoint: string; model: string } | null>(null);
  let messages = $state<Msg[]>([]);
  let input = $state("");
  let sending = $state(false);
  let testResult = $state<{ ok: boolean; message: string } | null>(null);
  let testing = $state(false);

  onMount(async () => {
    try {
      status = await api.ai.status();
    } catch {
      status = null;
    }
  });

  async function send(event: Event) {
    event.preventDefault();
    if (!input.trim()) return;
    const prompt = input;
    messages = [...messages, { role: "user", content: prompt }];
    input = "";
    sending = true;
    try {
      const proposal = await api.ai.agentPropose(prompt);
      if (proposal.intent === "chat") {
        messages = [
          ...messages,
          { role: "assistant", content: proposal.message ?? "(no response)" }
        ];
      } else if (proposal.intent === "search_now") {
        // Non-destructive: just show a confirm card that navigates
        messages = [
          ...messages,
          { role: "proposal", proposal, status: "pending" }
        ];
      } else {
        messages = [
          ...messages,
          { role: "proposal", proposal, status: "pending" }
        ];
      }
    } catch (e) {
      messages = [
        ...messages,
        {
          role: "assistant",
          content: `⚠️ ${(e as { detail?: string }).detail ?? "request failed"}`
        }
      ];
    } finally {
      sending = false;
    }
  }

  async function confirmProposal(index: number) {
    const msg = messages[index];
    if (msg?.role !== "proposal" || msg.status !== "pending") return;
    const p = msg.proposal;

    if (p.intent === "search_now") {
      const query = String((p.params.query as string) ?? "");
      messages[index] = { ...msg, status: "executed", result: `Searching for '${query}'…` };
      await goto(`/search?q=${encodeURIComponent(query)}`);
      return;
    }

    try {
      const result = await api.ai.agentExecute(p.intent, p.params);
      messages[index] = {
        ...msg,
        status: "executed",
        result: `✅ ${result.message}`
      };
    } catch (e) {
      messages[index] = {
        ...msg,
        status: "executed",
        result: `❌ ${(e as { detail?: string }).detail ?? "failed"}`
      };
    }
  }

  function cancelProposal(index: number) {
    const msg = messages[index];
    if (msg?.role !== "proposal") return;
    messages[index] = { ...msg, status: "cancelled" };
  }

  async function runTest() {
    testing = true;
    testResult = null;
    try {
      const r = await api.ai.test();
      testResult = { ok: true, message: r.response.trim() || "(empty response)" };
    } catch (e) {
      testResult = { ok: false, message: (e as { detail?: string }).detail ?? "failed" };
    } finally {
      testing = false;
    }
  }

  function renderMarkdown(text: string): string {
    // Tiny safe subset: **bold** only. Everything else is escaped.
    const escaped = text
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
    return escaped.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  }

  function intentLabel(intent: string): string {
    switch (intent) {
      case "add_series":
        return "Auto-download series";
      case "add_movie":
        return "Auto-download movie";
      case "add_filter_task":
        return "Standing filter rule";
      case "add_to_watchlist":
        return "Add to watchlist";
      case "search_now":
        return "Run search";
      default:
        return intent;
    }
  }
</script>

<div class="space-y-4">
  <div class="flex items-center justify-between">
    <div>
      <h2 class="flex items-center gap-2 text-xl font-semibold">
        <Sparkles class="h-5 w-5 text-primary" /> AI Assistant
      </h2>
      <p class="mt-1 text-sm text-muted-foreground">
        {#if status}
          {status.model} @ <span class="font-mono text-xs">{status.endpoint}</span>
        {:else}
          Unknown AI status
        {/if}
      </p>
    </div>
    <button
      class="inline-flex items-center gap-2 rounded-md border border-border bg-background px-4 py-2 text-sm hover:bg-muted"
      onclick={runTest}
      disabled={testing}
    >
      {#if testing}
        <Loader2 class="h-4 w-4 animate-spin" />
      {:else if testResult?.ok}
        <CheckCircle2 class="h-4 w-4 text-green-600" />
      {:else if testResult && !testResult.ok}
        <XCircle class="h-4 w-4 text-destructive" />
      {/if}
      Test connection
    </button>
  </div>

  {#if testResult}
    <div
      class="rounded-md border px-3 py-2 text-xs {testResult.ok
        ? 'border-green-500/30 bg-green-500/10 text-green-700 dark:text-green-300'
        : 'border-destructive/30 bg-destructive/10 text-destructive'}"
    >
      {testResult.message}
    </div>
  {/if}

  <div class="rounded-xl border border-border bg-card p-4">
    <div class="min-h-[420px] space-y-3">
      {#if messages.length === 0}
        <div class="py-16 text-center text-sm text-muted-foreground">
          <Wand2 class="mx-auto mb-3 h-6 w-6" />
          <div class="font-medium text-foreground">Try saying something like:</div>
          <div class="mt-3 space-y-1.5 text-xs">
            <div>"Add The Big Bang Theory to my downloads"</div>
            <div>"I want Dune: Part Two in 4K"</div>
            <div>"Search for the bear season 3"</div>
            <div>"Remember Severance, I might grab it later"</div>
          </div>
        </div>
      {/if}

      {#each messages as msg, idx}
        {#if msg.role === "user"}
          <div class="flex justify-end">
            <div class="max-w-[80%] rounded-2xl bg-primary px-4 py-2 text-sm text-primary-foreground">
              {msg.content}
            </div>
          </div>
        {:else if msg.role === "assistant"}
          <div class="flex justify-start">
            <div class="max-w-[80%] rounded-2xl bg-muted px-4 py-2 text-sm text-foreground">
              <div class="whitespace-pre-wrap">{msg.content}</div>
            </div>
          </div>
        {:else if msg.role === "proposal"}
          <div class="flex justify-start">
            <div class="w-full max-w-[90%] rounded-2xl border border-primary/30 bg-primary/5 p-4">
              <div class="flex items-start gap-3">
                <div class="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-primary/10">
                  <Wand2 class="h-4 w-4 text-primary" />
                </div>
                <div class="flex-1">
                  <div class="text-xs font-semibold uppercase tracking-wide text-primary">
                    {intentLabel(msg.proposal.intent)}
                  </div>
                  <div class="mt-1 text-sm">
                    {@html renderMarkdown(msg.proposal.description)}
                  </div>

                  {#if msg.proposal.warnings.length > 0}
                    {#each msg.proposal.warnings as w}
                      <div class="mt-2 flex items-start gap-1.5 rounded-md border border-yellow-500/30 bg-yellow-500/10 px-2 py-1 text-xs">
                        <AlertTriangle class="mt-0.5 h-3 w-3 text-yellow-600" />
                        <span>{w}</span>
                      </div>
                    {/each}
                  {/if}

                  {#if msg.proposal.preview.config_yaml}
                    <details class="mt-3">
                      <summary class="cursor-pointer text-xs text-muted-foreground hover:text-foreground">
                        Show task details
                      </summary>
                      <div class="mt-2 space-y-1 text-xs">
                        <div><span class="text-muted-foreground">Name:</span> <span class="font-mono">{msg.proposal.preview.task_name}</span></div>
                        <div><span class="text-muted-foreground">Schedule:</span> <span class="font-mono">{msg.proposal.preview.schedule_cron}</span></div>
                        <div><span class="text-muted-foreground">Output:</span> <span class="font-mono">{msg.proposal.preview.client}</span></div>
                        <pre class="mt-2 overflow-x-auto rounded-md bg-background p-2 font-mono text-[10px]">{msg.proposal.preview.config_yaml}</pre>
                      </div>
                    </details>
                  {/if}

                  {#if msg.status === "pending"}
                    <div class="mt-3 flex gap-2">
                      <button
                        class="inline-flex items-center gap-1 rounded-md bg-primary px-4 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90"
                        onclick={() => confirmProposal(idx)}
                      >
                        <CheckCircle2 class="h-3.5 w-3.5" />
                        {msg.proposal.intent === "search_now" ? "Run" : "Confirm"}
                      </button>
                      <button
                        class="inline-flex items-center gap-1 rounded-md border border-border bg-background px-4 py-1.5 text-xs hover:bg-muted"
                        onclick={() => cancelProposal(idx)}
                      >
                        Cancel
                      </button>
                    </div>
                  {:else if msg.status === "executed"}
                    <div class="mt-3 rounded-md bg-background px-3 py-2 text-xs">
                      {msg.result}
                    </div>
                  {:else}
                    <div class="mt-3 text-xs text-muted-foreground">Cancelled</div>
                  {/if}
                </div>
              </div>
            </div>
          </div>
        {/if}
      {/each}

      {#if sending}
        <div class="flex justify-start">
          <div class="flex items-center gap-2 rounded-2xl bg-muted px-4 py-2 text-sm">
            <Loader2 class="h-4 w-4 animate-spin" />
            thinking…
          </div>
        </div>
      {/if}
    </div>

    <form onsubmit={send} class="mt-4 flex gap-2">
      <input
        type="text"
        bind:value={input}
        placeholder="Ask anything…"
        class="flex-1 rounded-md border border-input bg-background px-3 py-2 text-sm outline-none ring-ring focus:ring-2"
      />
      <button
        type="submit"
        disabled={sending || !input.trim()}
        class="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-60"
      >
        <Send class="h-4 w-4" /> Send
      </button>
    </form>
  </div>
</div>
