---
title: AI Assistant
order: 6
description: Talk to Trove in natural language — it proposes and you confirm.
---

# AI Assistant

Trove ships with an optional **AI agent** that understands natural-language commands and turns them into structured actions (tasks, watchlist entries, searches). It uses a local LLM via [litellm](https://github.com/BerriAI/litellm) — by default pointing at an Ollama server.

## How it works

1. You type a request in the `/ai` chat
2. Trove sends your text to the LLM with a system prompt that defines the available **intents** and expected JSON output
3. The LLM replies with a structured JSON describing its interpretation
4. Trove turns that into a **proposed action** with a preview (task name, YAML, schedule, target client)
5. You click **Confirm** — and only then does Trove actually create the resource

This propose-confirm-execute pattern means the LLM never performs destructive actions directly. Even if gemma hallucinates, you see the full preview before anything is saved. Just click Cancel if it's wrong.

## Supported intents

### `add_series`
> "add the big bang theory to my downloads"
> "I want every new episode of Severance in 1080p"

Creates a task that hourly searches for new episodes of a specific show and sends them to your default torrent client.

### `add_movie`
> "i want dune part two in 4k"
> "download The Godfather 1972 whenever it shows up"

Creates a task that searches every 2 hours for a specific movie and downloads the best-quality match.

### `add_filter_task`
> "always grab all movies newer than 2022 in 1080p"
> "download every 4k movie from the last 3 years"
> "grab any movie from 2020-2023 under 5gb"
> "download all new linux iso releases"
> "grab every new switch game"
> "always get new audiobooks"

Creates a **standing rule** that continuously scoops up content matching a broad filter from your local RSS cache. This requires at least one RSS feed to be configured — it reads from the `rss_item` table, not from live indexer searches.

Supported kinds: `movie`, `series`, `game`, `software`, `audiobook`, `comic`, `music`, `any`.

For non-movie kinds, you can use `require_tokens` (must-appear keywords) and `reject_tokens` (must-not-appear keywords). Example: *"grab every new switch game"* generates a filter with `kind=game, require_tokens=['switch']`.

### `add_to_watchlist`
> "remember severance, i might grab it later"

Adds to your passive watchlist without creating an auto-download rule. Useful for "I'll think about it" titles.

### `search_now`
> "search for the bear season 3"

Opens the `/search` page with the query pre-filled and runs it immediately.

### `chat`
> "why did last night's run fail?"
> "what does the dry-run button do?"

Plain question-and-answer. No action is created — you just get a text response.

## Choosing a model

Go to `/settings` → **AI Assistant** panel. The model field expects a litellm-formatted identifier:

- Ollama: `ollama/<tag>` — e.g. `ollama/gemma4:latest`, `ollama/llama3.1:70b`, `ollama/llama4:16x17b`
- Other providers: litellm supports Claude, OpenAI, etc. — but requires their API keys set as env vars

Click **Load available models** and Trove queries your Ollama server's `/api/tags` endpoint, showing all installed models with their parameter size, family, and disk size. Click a model card to pre-fill the field.

**Recommended**: for intent classification, a small-to-medium instruct model is ideal — it's fast and follows JSON instructions well. `gemma4:latest` (8B), `llama3.1:8b`, or `qwen2.5:7b` are all good choices.

## Temperature

The `ai.default_temperature` setting (slider in the AI panel) controls creativity:

- **0.0–0.2** — Focused, deterministic. Best for intent classification and task generation
- **0.3–0.5** — Balanced. Good for chat Q&A
- **0.7–1.0** — Creative. Use for brainstorming only — don't use this for agent actions

Default is 0.2, which is right for the agent.

## Caching

AI responses are cached by prompt hash in the `ai_cache` table with a 7-day TTL. If you ask the same question twice, the second request is instant. The cache is cleared automatically when it expires.

## When the AI isn't enough

The agent handles common cases but has blind spots:

- **Very specific YAML** — write it yourself on `/tasks`
- **Login-requiring Cardigann trackers** — not supported yet
- **Complex multi-input tasks** — the agent generates single-input tasks; you can edit the YAML after creation
- **Filter combinations it doesn't understand** — fall back to manual YAML

Nothing the AI does is magic — every proposed task YAML is shown in the confirmation card under "Show task details". You can read it, copy it, and edit it in `/tasks` after creation.
