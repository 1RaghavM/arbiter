# Start implementation only when authorized

Repository setup is complete. These prompts are for a later, explicitly authorized phase session; their presence does not authorize starting a phase.

Copy the following into a Codex session opened at the target repository root:

```text
Build Arbiter using the specifications in this repository. First read AGENTS.md,
docs/STATUS.md, docs/steering.md, docs/requirements.md, docs/design.md,
docs/quality.md, and docs/phases.md.
Inspect the existing repository and applicable nested instructions before edits.

Keep the implementation small: React/TypeScript/Vite/shadcn frontend, FastAPI,
PostgreSQL, direct cloud API adapters, a deterministic routing function, and a
CLI for background benchmarks. No production platform, local models, agent
framework, Redis, or distributed queue. Write minimal, clear code in a style a
junior developer can maintain; add comments only for non-obvious reasons.

Begin with Phase 00 unless repository evidence and STATUS prove it is complete.
Implement only the earliest eligible phase. Use its own phase branch, create
meaningful incremental commits (usually 3–6 per phase), checking each slice
and pushing immediately after every commit. Use my configured Git identity as
sole author/committer, with no Codex or assistant co-author trailers. If push
access is missing, finish local edits and checks but do not create more commits.
Run the phase gates, update STATUS, commit and push that update, and create one PR. Stop at the PR review boundary; do not
merge or begin the next phase without authorization. Later phases begin from
the updated default branch after the preceding PR is merged.

Verify exact provider APIs, model IDs, pricing, and SDK versions from official
docs before using them. Never invent credentials, live test results, PR URLs,
or benchmark savings. Complete useful offline work when access is missing,
then report the smallest blocker. Treat mock and live evidence distinctly.

Start by stating the active phase, the concrete changes you will make, and the
checks you will use. Then implement it. Do not stop after a plan.
```

## Continue after a PR is merged

```text
The previous phase PR is merged. Read AGENTS.md and docs/STATUS.md, verify the actual
git state, update the default branch safely, and implement the next eligible
phase on its own branch. Check each slice, commit with my sole authorship and
no assistant co-author trailers, and immediately push before the next commit.
Run its gates, update STATUS, and create its PR. Stop for review afterward.
```

## Inputs the implementation environment must supply

Repository path; GitHub remote/authentication for real PRs; PostgreSQL connection; TypeSafe/Jev key; OpenAI, Anthropic, and Google keys; request/benchmark spending ceilings; deployment host credentials when reaching Phase 08. Store secrets only in environment/host secret settings, never in these docs. Do not block Phase 00 just because later credentials are absent.
