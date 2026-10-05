# Arbiter

A student project to evaluate whether routing across cloud AI models can preserve response quality while reducing cost or latency.

**Status: repository setup only. Phases 00–08 are pending.** No application, dependencies, services, or CI have been created. Phase implementation requires explicit authorization.

## Documentation index

| Document | Purpose |
| --- | --- |
| [Agent instructions](AGENTS.md) | Repository workflow, scope boundaries, and review rules |
| [Documentation guide](docs/README.md) | Reading order and specification ownership |
| [Status](docs/STATUS.md) | Verified repository state, evidence, and next action |
| [Requirements](docs/requirements.md) | Product scope and acceptance criteria R01–R14 |
| [Steering](docs/steering.md) | Stack, architectural decisions, and exclusions |
| [Design](docs/design.md) | Runtime flow, API, storage, routing, and accounting contracts |
| [Quality](docs/quality.md) | Phase gates and benchmark protocol |
| [Phases](docs/phases.md) | Ordered phases, branch names, deliverables, and dependencies |
| [Handoff](docs/HANDOFF.md) | Prompts for explicitly starting or continuing implementation |
| [Sources](docs/SOURCES.md) | Official references to verify during integration |
| [PR template](.github/pull_request_template.md) | Evidence and review checklist for future phase PRs |

## Starting implementation later

Read the agent instructions and current status, then explicitly authorize Phase 00 using the handoff prompt. Each phase has its own branch and PR; subsequent phases wait for the preceding PR to be merged. Installation and development commands will be documented when Phase 00 creates the application.

Git is initialized on `master`. No remote is configured; GitHub remote access and authentication will be needed to publish phase PRs.
