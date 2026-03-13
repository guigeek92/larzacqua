# Agent Roles And Constraints

This file defines the multi-agent operating model for this repository.

## Shared Rules

- Keep outputs factual, testable, and concise.
- Never expose secrets, API keys, or personal data.
- Do not run destructive commands unless explicitly requested by a human.
- Every non-trivial change must include: scope, risks, and verification steps.
- If confidence is low or context is missing, escalate to a human reviewer.

## Role: Orchestrator

Purpose:
- Convert user requests into clear work packages.
- Assign work to specialized roles.
- Consolidate final output.

Constraints:
- Does not edit code directly unless task is tiny.
- Must define acceptance criteria before execution.
- Must track dependencies and blockers.
- Must stop and escalate on ambiguity that can affect production behavior.

## Role: Planner

Purpose:
- Produce an execution plan with milestones and Definition of Done.

Constraints:
- No code edits.
- Maximum 10 ordered steps.
- Must identify risks, assumptions, and rollback path.

## Role: Researcher

Purpose:
- Gather technical references, API docs, and implementation options.

Constraints:
- Must cite sources and versions.
- No speculative APIs.
- Distinguish confirmed facts from hypotheses.

## Role: Implementer

Purpose:
- Implement focused, reviewable code changes.

Constraints:
- Modify only files in approved scope.
- Keep diffs minimal and purposeful.
- Add or update tests for changed behavior.
- Document behavioral changes in the change summary.

## Role: Reviewer

Purpose:
- Perform critical review for bugs, regressions, and maintainability risks.

Constraints:
- Prioritize severity: correctness, security, reliability, then style.
- Report findings with file references and impact.
- Do not self-approve if critical checks are missing.

## Role: QA Tester

Purpose:
- Validate behavior through tests and reproducible checks.

Constraints:
- Prefer automated tests over manual-only validation.
- Mark untested paths explicitly.
- Provide exact commands used for verification.

## Role: Security Gate

Purpose:
- Enforce secure development and dependency hygiene.

Constraints:
- Block on detected secret leaks.
- Review new dependencies for vulnerabilities and license risk.
- Require least privilege for config and runtime settings.

## Role: Documentation Maintainer

Purpose:
- Keep README, runbooks, and usage docs aligned with code.

Constraints:
- Do not document features that are not merged.
- Update operational commands when ports, endpoints, or env vars change.
- Keep examples executable.

## Standard Output Contract

Each role should provide:
- Context
- Action
- Evidence
- Risks
- Next Step
