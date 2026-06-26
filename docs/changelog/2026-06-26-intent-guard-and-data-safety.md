# 2026-06-26 Intent Guard and Data Safety

## Summary

This change hardens the intent-routing path, separates Docker development and
production workflows, and tightens runtime-data safety. The guiding principle is
small boundary improvements: keep skill loading and agent scheduling intact,
but make the edges safer and easier to reason about.

At a high level:

- Intent recognition now has guardrails before and after LLM routing.
- Intent names are aligned with skill-backed agents through one catalog.
- Model response parsing and intent-result validation are split out of
  `IntentionAgent`.
- Docker production still copies source into the image, while development can
  mount source code into `/app`.
- Redis, RAG, model, and local memory data are treated as runtime/private data
  rather than ordinary source code.

## Intent Guard

- Added `core.intent_guard` as a small, dependency-light guard layer.
- Short, vague, malformed, or social inputs are classified before any skill is
  called.
- Added structured routing fields:
  - `intent`
  - `confidence`
  - `reason`
  - `should_call_skill`
- Added structured non-skill intents that never call a skill:
  - `unclear`
  - `unsupported`
  - `fallback`
- Greetings and social small talk are routed to the `chitchat` skill (see
  *Intent ↔ Skill 1:1 Alignment* below) rather than an earlier `smalltalk`
  no-op label, so every intent now maps to exactly one skill.
- `information_query` now has a higher threshold and requires a clear query
  target.
- Intent recognition failures no longer fall back to `information_query`.

## Routing Changes

- `FastIntentRouter` now consults the guard first.
- `IntentionAgent` applies the same guard before LLM routing and after LLM
  output normalization.
- `OrchestrationAgent` respects `should_call_skill=false` as a final safety
  check and returns a clarification instead of touching the skill registry.
- CLI, legacy WebUI, and new WebUI now prefer the orchestrator clarification
  message for `no_agents` responses instead of always falling back to chitchat.

## Intent Agent Refactor

- Added `core.llm_response` to normalize model responses into text.
- Added `core.intent_result` for intent JSON cleaning, parsing, and Pydantic
  schema validation.
- Removed inline response extraction and JSON parsing from `IntentionAgent`.
- Fixed streaming response handling so chunks are appended instead of
  overwritten.
- Fixed routing guard precedence so `routing.intent` is preferred over
  `intents[0].type`.
- Fixed `should_call_skill` post-processing so guard decisions override LLM
  output instead of preserving unsafe `true` values.

## Intent ↔ Skill 1:1 Alignment

The intent vocabulary and the skill registry used to drift apart: greetings were
classified as a non-skill `smalltalk` label by the guard/router while a real
`chitchat` skill (with its own agent) already existed for CLI/WebUI, so the same
"hello" had two competing paths and the prompt listed `chitchat` and `smalltalk`
inconsistently. This change makes intent ↔ skill a strict 1:1 mapping with a
single source of truth.

- Added `core.intent_catalog` as the single source of truth:
  - `SKILL_INTENTS` — each intent mapped to exactly one skill folder
    (`chitchat`, `preference`, `memory_query`, `event_collection`,
    `itinerary_planning`, `information_query`, `rag_knowledge`, `mcp_tool`).
  - `NON_SKILL_INTENTS` — only `unclear` and `unsupported`.
  - Shared `CHITCHAT_EXACT` / `CHITCHAT_KEYWORDS` (replacing three overlapping
    keyword sets scattered across guard, router, and WebUI).
  - `INTENT_DISPLAY_NAMES` and `build_intent_prompt_section()` helpers.
- Retired the `smalltalk` label. Greetings and social dialogue now route to the
  existing `chitchat` skill, which already provides rule-template → LLM →
  offline-fallback branching — no skill code change was needed.
- `core.intent_guard` and `core.intent_router` now emit a skill-backed `chitchat`
  route for greetings. The greeting check stays ahead of the `length <= 2`
  guard so short greetings (`你好`, `在吗`, `嗨`) are not misread as `unclear`.
- `IntentionAgent` builds its intent list from the catalog, merging the
  previously duplicated "available skills" and "intent type" prompt sections into
  one, and `smalltalk` is no longer in the no-skill override set.
- `OrchestrationAgent` dropped its `smalltalk` special-case; greetings now
  execute through the normal agent path.
- Consolidated the three duplicated Chinese display-name dictionaries in CLI,
  legacy WebUI, and new WebUI into `INTENT_DISPLAY_NAMES` from the catalog.
- Added `tests/test_intent_catalog.py` (catalog invariants plus a drift guard
  against the skills discovered by `SkillLoader`) and updated
  `tests/test_intent_guard.py` to assert greetings route to `chitchat`.

## Data Safety

- Local Claude settings are ignored and replaced with sanitized example files.
- Runtime memory JSON files remain ignored.
- RAG source documents are ignored by default; only sanitized `example_*.txt`
  files are intended for version control.
- RAG vector indexes and local model weights are ignored.
- Existing tracked local settings, RAG source documents, and model artifacts were
  removed from the Git index with `git rm --cached`, leaving local files on disk.
- Added lightweight README/example placeholders for local memory, local models,
  and sanitized RAG documents so the directory layout remains understandable
  without committing private data.

## Docker Runtime

Docker is now split into two modes without changing application code.

- Production mode keeps the existing immutable image behavior:
  - `docker/Dockerfile` still uses `WORKDIR /app`.
  - Source code is copied into the image with `COPY . .`.
  - `docker/docker-compose.yml` does not mount the full source tree.
  - Use this mode for reproducible deploys and rollback-friendly images.
- Development mode adds `docker/docker-compose.dev.yml`:
  - Mounts the project root into `/app`.
  - Keeps existing `data/documents`, `data/models`, and `data/rag_knowledge`
    mounts.
  - Masks `/app/.venv`, `/app/venv`, `/app/env`, and `/app/node_modules` with
    anonymous volumes so local virtualenvs or frontend dependencies do not
    overwrite the container environment.
  - Ordinary Python, Markdown, and JSON source/config changes only require
    restarting the `hommey` container.

Commands:

```bash
# Development
docker compose -f docker/docker-compose.yml -f docker/docker-compose.dev.yml up -d hommey

# Production
docker compose -f docker/docker-compose.yml up -d --build hommey
```

Rebuild rules:

- Development usually only needs `restart hommey` for ordinary source changes.
- Rebuild when Dockerfile, apt packages, Python dependencies, or base image
  change.
- Production should rebuild for any code change because source is copied into
  the image.

## Redis Configuration

Docker `env_file` treats values differently from `python-dotenv` in a few edge
cases. A line like `HOMMEY_REDIS_PASSWORD= # comment` can become a non-empty
string inside the container, causing the Redis client to send `AUTH` to a Redis
server that has no password configured.

Fixes:

- `settings.py` and `config.example.py` now parse optional environment values
  through `_optional_env()`, treating blank and comment-like values as `None`.
- `docker/docker-compose.yml` explicitly sets `HOMMEY_REDIS_PASSWORD: ""`.
- `.env.example` now keeps the Redis password comment on a separate line.

This keeps local memory/Redis behavior consistent across direct Python runs and
Docker runs.

## RAG Pipeline

The RAG pipeline expected `rag.config.RAGPipelineConfig`, but the module was
missing. This caused `rag_knowledge` requests to fail when the ask-question skill
loaded the shared retriever/pipeline.

Fixes:

- Added `rag.config.RAGPipelineConfig` as a typed adapter around
  `settings.RAG_CONFIG`.
- Kept `settings.py` as the source of runtime defaults; `rag.config` exists to
  give the RAG package a small typed object, not a second configuration center.
- `rag.parser.TxtParser` now accepts both `txt` and `md`, because sanitized
  Markdown placeholders and README files may live under document directories.
- `rag.loader.FileSystemDocumentLoader` skips unsupported file extensions during
  directory scans instead of letting incidental files break the whole ingest.

Operational note:

- Milvus Lite locks `data/rag_knowledge/milvus_lite.db` while WebUI is running.
  Stop the `hommey` app container before rebuilding the local knowledge base,
  then start it again:

```bash
docker compose -f docker/docker-compose.yml -f docker/docker-compose.dev.yml stop hommey
docker compose -f docker/docker-compose.yml -f docker/docker-compose.dev.yml run --rm hommey python .claude/skills/ask-question/script/init_knowledge_base.py
docker compose -f docker/docker-compose.yml -f docker/docker-compose.dev.yml up -d hommey
```

Do not use `down -v` unless you intentionally want to remove Docker volumes.

## Notes

`data/rag_knowledge/` is currently owned by a Docker-created `nobody:nogroup`
user on this machine, so a README placeholder could not be written there without
local sudo credentials. The directory remains ignored by Git.

The local Python environment used during this change did not have `pytest` or
`agentscope` installed, so full pytest execution was not possible there. Syntax
checks and dependency-light smoke checks were run for the modified core/RAG
modules.
