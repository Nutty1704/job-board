# 0001: Use a monorepo

## Decision

Start with a single monorepo containing top-level areas:

- `apps/` for deployable apps and workers as they are created
- `packages/` for shared libraries as they are created
- `infra/` for infrastructure code as it is introduced
- `docs/` for architecture notes and decisions
- `scripts/` for development and deployment helpers
- CI/CD configuration when the tooling is decided

## Consequences

- Keeps the initial repo lightweight.
- Leaves implementation details undecided until development starts.
