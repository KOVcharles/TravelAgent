# Project Structure

This repository is currently a modular monolith for the Hommey travel agent.
The first cleanup pass keeps the existing runtime layout intact, but makes the
main boundaries explicit so later refactors can be done safely.

## Current Runtime Boundaries

- `agents/`: core orchestration layer.
  - `intention_agent.py` classifies user intent and builds the execution plan.
  - `orchestration_agent.py` schedules skill-backed agents and aggregates results.
  - `lazy_agent_registry.py` discovers and lazily loads skill plugins.
- `.claude/skills/`: canonical runtime skill plugin directory for this branch.
  - Each skill owns concise `SKILL.md` instructions, a validated `manifest.yaml`, and an optional `script/agent.py` implementation.
  - Manifests declare versions, intent mapping, tool permissions, dependencies, schemas, and execution stages.
  - The runtime path is configurable with `HOMMEY_SKILLS_ROOT`.
- `context/`: short-term and long-term memory implementations.
- `hommey_mcp/`: project-owned MCP client/server integration. This name avoids
  shadowing the third-party `mcp` protocol package.
- `webui_new/`: current FastAPI web application.
- `webui_new/skill_platform/`: administrator Skill registry, graph, settings, and trace service.
- `core/skill_manifest.py`: machine-readable Skill contract.
- `core/skill_store.py`: PostgreSQL-backed Skill settings and sanitized execution traces.
- `legacy/webui_gradio.py`: legacy Gradio web entry point retained for compatibility.
- `cli.py`: command-line entry point.
- `runtime.py`: shared factory for model, memory, registry, and orchestrator wiring.
- `settings.py`: tracked runtime configuration that reads environment variables.
- `utils/`: shared infrastructure helpers.
- `data/`: local runtime data and large assets. New runtime data should not be
  committed.

## Cleanup Decisions In This Branch

- Skill discovery now resolves paths from the project root instead of the
  process working directory.
- Skill metadata loading and skill agent loading now use the same configured
  root: `HOMMEY_SKILLS_ROOT`, defaulting to `.claude/skills`.
- `.agents/` is treated as a local/generated duplicate and ignored by Git.
- Secrets are removed from `config.py`; runtime configuration is read from
  environment variables.
- New memory files, local model assets, test reports, and `.env` files are
  ignored for future commits.

## Skill Platform Runtime

```text
User request
  -> domain guard
  -> manifest-derived intent catalog
  -> manifest-derived execution schedule
  -> lazy skill agent loading
  -> optional Skill enablement policy
  -> orchestration and sanitized trace recording
```

The current business workflow composes `event-collection`, `ask-question`,
`plan-trip`, and `check-trip-compliance`. Company policy remains RAG data; the
Skill stores the reusable procedure for retrieving, evaluating, and citing it.

## Target Structure For A Later Refactor

The next larger refactor should move runtime code into a package without
changing behavior:

```text
src/
  hommey/
    app/
      cli.py
      web/
    core/
      agents/
      memory/
      resilience/
    skills/
    integrations/
      mcp/
    config/
tests/
docs/
scripts/
```

That migration should be done only after the current tests are aligned with
the skill-plugin architecture, because several tests still import legacy agent
module paths directly.
