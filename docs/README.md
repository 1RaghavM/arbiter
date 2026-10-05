# Arbiter documentation guide

These are the canonical project specifications. Phase 00 establishes the local development foundation; see STATUS.md for review progress.

Read the [project overview](../README.md), use [SETUP.md](SETUP.md) for install/dev/check commands, and consult the [current status](STATUS.md) for verified progress.

## Reading order and ownership

1. [Repository agent instructions](../AGENTS.md): workflow, scope, and review boundaries.
2. [Status](STATUS.md): current evidence and next action.
3. [Steering](steering.md): architectural choices and simplicity constraints.
4. [Requirements](requirements.md): product scope and acceptance requirements.
5. [Design](design.md): technical contracts and failure behavior.
6. [Quality](quality.md): tests and experimental gates.
7. [Phases](phases.md): implementation order and the authorized phase's deliverables.

[HANDOFF.md](HANDOFF.md) contains prompts for a future implementation session. [SOURCES.md](SOURCES.md) records official integration references and verification policy. The [PR template](../.github/pull_request_template.md) is installed at the repository root for GitHub discovery.

Keep these specs in `docs/`; do not copy a second set into the root. `AGENTS.md` at the root applies repository-wide, and [docs/AGENTS.md](AGENTS.md) adds documentation-specific guidance.

Exact dependency versions and available model IDs are implementation work. Credentials and live provider access remain unverified.
