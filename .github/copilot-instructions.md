# Copilot Workspace Instructions

Use this file as always-on guidance for this repository.

## Mission

Build and maintain a reliable AI energy analysis tool for PDF-based infrastructure documents.

## Working Mode

- Prefer small, incremental changes with clear intent.
- Validate changes with tests or runnable checks when possible.
- Keep API contracts explicit and backward-aware.
- Preserve compatibility for existing Streamlit and FastAPI flows unless request says otherwise.

## Safety And Quality

- Never output or commit secrets from `.env` or local machine paths.
- Highlight assumptions when requirements are incomplete.
- For reviews, report findings first, ordered by severity.
- Avoid broad refactors during bugfix tasks.

## Python And Project Conventions

- Keep imports explicit and avoid hidden side effects at module import time.
- Prefer pure helper functions for extraction logic when feasible.
- Include concise comments only for non-obvious logic.
- Ensure new behavior has at least one test or explicit test gap note.

## Output Style

- Be concise and action-oriented.
- Include file references for every significant finding or change.
- When commands are run, summarize the meaningful result.

## Multi-Agent Execution

When role-based execution is requested:
- Follow `.github/AGENTS.md` role constraints.
- Use a single owner for final synthesis (Orchestrator).
- Require evidence from each role before final approval.
