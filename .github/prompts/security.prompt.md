---
description: "Use when: you need a security and compliance gate before merge or release."
---
# Prompt Template: Security Gate

Goal:
- Prevent insecure changes from reaching production.

Checklist:
1. Secret exposure check
2. Dependency vulnerability and license check
3. Input validation and error-handling review
4. Least-privilege config review
5. Logging and sensitive data redaction review

Required output:
- Pass/fail decision
- Blocking issues with file references
- Required remediations
- Non-blocking recommendations

Constraints:
- Block on secret leaks and critical vulnerabilities.
- Require explicit exception approval for temporary risk acceptance.
