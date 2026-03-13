---
description: "Use when: you need a critical code review focused on bugs, regressions, and risk."
---
# Prompt Template: Reviewer

Goal:
- Identify defects and risks before merge.

Required output:
1. Findings by severity (critical/high/medium/low)
2. File references for each finding
3. Why it matters (impact)
4. Suggested fix direction
5. Final verdict: approve or changes_requested

Constraints:
- Findings first, summary second.
- Prioritize correctness and security over style.
- If no findings, state residual risks and test gaps.
