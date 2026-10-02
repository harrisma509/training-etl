# Training System Service Boundaries

**Status:** Accepted
**Date:** 2026-10-01
**Scope:** Cross-repository architecture for `training-etl`, `training-runner`, `training-api`, `training-web`, PostgreSQL, browser clients, and AI-provider adapters.

## 1. Purpose

This Architecture Requirements Document (ARD) is the authoritative boundary decision for the Training Intelligence system. It removes ambiguity between repository ownership, runtime service responsibility, database access, browser access, ETL orchestration, and AI-provider integration.

This document records the approved architecture. It does not redesign runtime behavior or claim that every approved future capability is already implemented.

## 2. Scope

This ARD governs:

- The `training-etl` repository and its deployed ETL services.
- The `training-runner` asynchronous and scheduled service.
- The `training-api` authenticated synchronous ETL facade.
- The `training-web` repository and browser-facing service.
- Shared PostgreSQL access and ownership.
- Browser, internal-service, external-source, and AI-provider boundaries.
- Search, Coach context, resync, and future cross-service decisions.

Detailed endpoint, schema, feature, and operational contracts remain in their owning documents.

## 3. Context and Problem Statement

The system has both direct server-side PostgreSQL reads and a separate internal API. Treating those paths as one universal chain creates two opposite risks: forcing ordinary dashboard reads through an unnecessary service, or placing ETL ingestion and authoritative calculations in the browser-facing application. The architecture must distinguish repository ownership from container purpose and preserve the current deployed behavior.

## 4. Architectural Drivers

- PostgreSQL must remain the shared durable system of record.
- Authoritative field meaning and calculations require one owner.
- Browser clients must not receive internal credentials or access internal services.
- Ordinary product reads should remain bounded, parameterized, and operationally simple.
- Long-running external work must not be held open by browser requests.
- Cross-service contracts must be justified by coordination, security, scaling, or schema-insulation value.
- Current deployed behavior must be documented separately from future possibilities.

## 5. Approved System Topology

```text
External sources
    -> training-runner / authoritative ETL functions
    -> PostgreSQL

Browser
    -> training-web browser-facing routes
    -> bounded server-side PostgreSQL queries
    -> PostgreSQL

training-web trusted server-side consumer
    -> authenticated training-api contract
    -> authoritative ETL function or coordinated PostgreSQL read

Browser
    -> training-web only

training-web
    -> configured AI provider for explicit Coach turns only

training-web
    -> queue/orchestration records for approved ETL work
    -> training-runner executes the authoritative ETL function
```

The arrows are approved paths, not a claim that every feature uses every path. `training-api` is not a mandatory hop for ordinary PostgreSQL reads.

## 6. Repository Responsibilities

### `training-etl` repository

Owns:

- External-source ingestion, including Strava, and ETL-owned OAuth credentials.
- Normalization, authoritative field semantics, and ETL-managed writes.
- Schema SQL, migrations, and schema evolution.
- Daily, Weekly, Load, TID, Fitness, Fatigue, Form, Weekly Audit, and other authoritative calculations/builders.
- Historical imports, backfills, rebuilds, reconciliation, and targeted repair logic.
- Sync queue worker behavior and operational ETL scripts.
- Implementation and deployment artifacts for `training-runner` and `training-api`.

It does not own browser presentation, ordinary dashboard UI routes, Coach conversation persistence, or browser-facing product workflows.

### `training-web` repository

Owns:

- FastAPI browser application setup and route registration.
- Server-side browser-facing API routes, static frontend, navigation, and presentation.
- Bounded, parameterized, read-only PostgreSQL queries over processed data for dashboard, Search, reporting, lookup, and presentation workflows.
- Stable response shaping, approved CSV exports, sync orchestration/status presentation, and web-owned CRUD.
- Coach sessions, messages, turns, settings, memories, receipts, and other explicitly web-owned application records.
- AI-provider orchestration, policy, usage, and cost accounting.
- On-demand narrative presentation and future Search presentation.

It must not ingest from ETL-owned external sources, receive Strava credentials, duplicate authoritative calculations, redefine persisted field semantics, or expose PostgreSQL directly to browser JavaScript.

## 7. Runtime and Container Responsibilities

### `training-runner`

`training-runner` is the asynchronous and scheduled ETL execution service. It runs scheduled synchronization, queue-driven sync processing, background ETL work, and explicitly invoked backfills, rebuilds, and maintenance. It reuses authoritative ETL functions. It is not a browser API, presentation service, generic task runner, or arbitrary command shell.

### `training-api`

`training-api` is a narrow authenticated synchronous facade over explicitly approved ETL functions and coordinated ETL-owned contracts. Current justified examples are the bounded, time-aligned Coach context contract, synchronous activity resync, and service health/readiness. It is not a universal query layer, arbitrary SQL surface, AI-provider client, duplicate calculation engine, Coach persistence owner, or browser-accessible admin shell.

### `training-web` service

The `training-web` container runs the browser-facing FastAPI application. Its server-side routes may read processed PostgreSQL data directly when the route is a bounded product query. Browser JavaScript communicates only with these routes.

## 8. PostgreSQL Ownership and Access Rules

PostgreSQL is the shared durable system of record. `training-etl` owns schema meaning, schema evolution, ETL-managed writes, normalization, and authoritative calculations. Schema ownership and read access are separate concerns.

Approved access rules:

- `training-web` may perform bounded, parameterized, server-side, read-only queries over processed data for ordinary dashboard, Search, reporting, lookup, narrative presentation, and export workflows.
- `training-api` may query or coordinate ETL-owned data only for an explicitly approved internal contract.
- Browser JavaScript never connects to PostgreSQL.
- No route may expose arbitrary SQL, unrestricted table access, or unbounded export behavior.
- Web-owned application records may be managed by `training-web` under explicit ownership.
- Schema evolution remains in `training-etl`, coordinated with affected consumers.

## 9. Browser and Secret Boundaries

The browser calls `training-web` only. It must never receive PostgreSQL credentials, `TRAINING_API_TOKEN`, Strava credentials, AI-provider credentials, raw provider payloads, or direct internal `training-api` access. `training-web` may call `training-api` server-to-server for approved contracts using the configured internal token.

AI providers receive only explicit, bounded Coach requests assembled by `training-web`. Providers do not own authoritative data, durable conversation history, policy, or user-managed memory.

## 10. Read-Path Decision Matrix

| Read or result | Approved owner and path | Boundary rule |
|---|---|---|
| Ordinary dashboard table | `training-web` -> bounded read-only PostgreSQL query | No `training-api` hop required. |
| Activity Search and CSV export | `training-web` -> bounded read-only PostgreSQL query -> shaped route response | No new Search endpoint in `training-api` for Search V1. |
| On-demand activity narrative display | `training-web` -> narrow read-only PostgreSQL query | Narrative remains allowlisted and on demand. |
| Coach multi-section authoritative context | `training-web` -> `training-api` coordinated contract | One time-aligned ETL-owned aggregate justifies the boundary. |
| One authoritative ETL function requiring Strava credentials | `training-api` for an approved synchronous operation, or `training-runner` when queued/background | `training-web` never receives provider credentials. |
| Browser request to internal `training-api` | Prohibited | Browser calls `training-web` only. |
| Generic or arbitrary database query endpoint | Prohibited | Use an explicit bounded product or internal contract. |

## 11. Write and Operation-Path Decision Matrix

| Operation | Approved owner and path |
|---|---|
| ETL-owned source or aggregate mutation | Authoritative ETL function in `training-etl`, normally executed by `training-runner`. |
| Scheduled or background work | `training-runner`. |
| Synchronous ETL operation with an explicit contract | Authenticated `training-api` facade calling the existing ETL function. |
| Browser-triggered long-running ETL work | `training-web` validates and enqueues/orchestrates an approved request; `training-runner` executes it. |
| Web-owned application data | `training-web` may perform bounded CRUD for its assigned records. |
| Schema evolution | `training-etl` only, coordinated with consumers. |

A web route may not perform direct Strava mutation or duplicate ETL calculation. Enqueueing an approved operation is orchestration, not ETL ownership.

## 12. Decision Criteria for Using `training-api`

Use `training-api` only when at least one demonstrated condition applies:

- The operation must invoke authoritative ETL logic or an ETL-owned external source.
- The result coordinates multiple ETL-owned calculations into one stable, time-aligned contract.
- Multiple independent consumers need the same abstraction and schema insulation has clear value.
- A distinct authentication, security, scaling, or deployment boundary has clear value.

A direct web read is preferred when the workflow is an ordinary bounded product query over already-processed data. Service boundaries are added from demonstrated need, not architectural fashion.

## 13. Explicitly Approved Direct `training-web` Database Reads

Direct server-side reads are approved and expected for ordinary dashboard tables, Search V1, reporting, lookup, on-demand narrative display, and CSV export. Queries must be parameterized, bounded, read-only where the workflow is a read, and shaped into a stable browser-facing response. This permission does not grant browser JavaScript database access, schema ownership, arbitrary SQL access, or permission to duplicate ETL calculations.

## 14. Explicit Prohibitions

- Do not require all PostgreSQL reads to traverse `training-api`.
- Do not place Strava ingestion, OAuth credentials, normalization, rebuilds, or authoritative calculations in `training-web`.
- Do not expose internal `training-api` endpoints directly to browser JavaScript.
- Do not turn `training-api` into generic SQL, a universal data layer, or an admin shell.
- Do not make AI providers the system of record or call them from `training-api`.
- Do not silently change ETL-owned field semantics in web routes.
- Do not hold a browser request open for long-running ETL work when queue orchestration is appropriate.

## 15. Current Examples

- `training-runner` runs scheduled and queue-driven synchronization from the ETL deployment.
- `training-api` currently serves health, the authenticated Coach context contract, and authenticated synchronous activity resync from ETL-owned functions.
- `training-web` serves browser-facing dashboard routes and owns Coach persistence and provider orchestration.
- Daily resync UI in `training-web` resolves and enqueues approved request rows; ETL and `training-runner` own the provider call and rebuild behavior.
- Coach context uses `training-api` because it coordinates bounded, time-aligned ETL-owned projections; Coach sessions and messages remain web-owned.

These examples describe current or documented behavior and do not imply that every future capability is deployed.

## 16. Search Architecture Application

Search V1 belongs in `training-web`:

```text
Browser -> training-web /api/activities/search
        -> bounded parameterized read-only PostgreSQL query
        -> shaped response -> Browser
```

`training-etl` owns schema and field semantics. New persisted fields, ingestion, or normalization belong there. The browser-facing Search route, UI, preview, and approved CSV export belong in `training-web`. Search V1 does not require a `training-api` Search endpoint. Reconsider only if coordinated aggregates, multiple consumers, security, scaling, or schema insulation demonstrate value greater than the additional complexity.

## 17. Coach Architecture Application

The Coach request begins at `training-web`. For each real turn, `training-web` persists the web-owned turn state, requests the bounded current context from authenticated `training-api`, adds bounded conversation and policy, and calls the configured AI provider. `training-api` supplies authoritative context; it does not store Coach messages, call the provider, or own provider policy and cost accounting.

The Coach exception is specifically the coordinated, time-aligned context contract. It does not establish a universal rule that all `training-web` reads must use `training-api`.

## 18. Resync Architecture Application

For a browser-triggered day or activity resync, `training-web` validates the request, resolves canonical IDs, and enqueues or invokes the approved existing operation according to the current contract. `training-runner` owns queued/background execution; `training-api` may expose an explicitly authenticated synchronous activity-resync facade. ETL owns Strava access, normalization, database mutation, and affected-date rebuilds. The browser receives status and sanitized results through `training-web`.

## 19. Consequences and Tradeoffs

Direct web reads keep ordinary dashboard and Search workflows simple and avoid an unnecessary network hop, but require disciplined query bounds, response shaping, and coordination when schema meaning changes. `training-api` adds authentication, deployment, testing, and failure complexity, but is valuable for coordinated context and ETL operations that must stay behind a trusted boundary. Queue orchestration improves reliability for long-running work but introduces status and retry state.

## 20. Alternatives Rejected

- Universal `PostgreSQL -> training-api -> training-web` reads: rejected because schema ownership does not require a service hop for ordinary bounded product reads.
- Browser -> `training-api`: rejected because it exposes an internal boundary and complicates secrets and authorization.
- ETL calculations duplicated in `training-web`: rejected because it creates conflicting authoritative values.
- A generic SQL or export service: rejected because it expands security, privacy, performance, and contract risk.
- A new Search service for Search V1: rejected because one web consumer can perform the bounded read directly.

## 21. Reconsideration Triggers

Reconsider a boundary when evidence shows one or more of the following:

- Multiple independent consumers need a stable coordinated contract.
- An aggregate requires cross-source time alignment that direct web reads cannot safely provide.
- Security, authentication, scaling, or deployment isolation materially improves.
- Query cost, schema churn, or failure behavior demonstrates a service abstraction is worthwhile.
- A workflow becomes long-running or provider-credential-bearing and needs queue or synchronous ETL mediation.

Reconsideration must preserve browser and secret boundaries and must not silently move schema ownership.

## 22. Documentation Precedence and Links

For cross-repository service boundaries, this ARD is authoritative. The Constitutions establish durable principles and link here. Detailed contracts remain authoritative for their feature: `docs/TRAINING_API.md`, `docs/STRAVA_ARCHITECTURE.md`, `docs/targeted_activity_resync.md`, `training-web/docs/AI_DEV_GUIDE.md`, `training-web/docs/AI_COACH.md`, and Search documentation. Runtime source and Compose files establish current implementation evidence; they do not override an accepted boundary without an explicit architecture decision.

## 23. Architecture Validation Checklist

Before approving a future feature that crosses a repository or service boundary, verify:

- The owning repository and runtime container are named separately.
- PostgreSQL is treated as the durable system of record.
- Schema meaning and authoritative calculations have one owner.
- The browser calls `training-web` only and receives no internal secrets.
- Ordinary product reads use bounded server-side queries where appropriate.
- `training-api` use satisfies a documented decision criterion.
- Long-running ETL work is queued or otherwise bounded.
- Web-owned CRUD is explicitly identified.
- No route exposes arbitrary SQL or unrestricted export.
- Current deployed behavior is separated from future or proposed behavior.
- Affected detailed contracts, tests, and operational runbooks are identified.
- The independent consistency questions below have clear answers.

Ask:

1. Could a future engineer conclude that every `training-web` database read must traverse `training-api`?
2. Could a future engineer put ETL calculations or Strava access into `training-web` because it owns browser-facing routes?
3. Could a future engineer expose an internal `training-api` endpoint directly to browser JavaScript?

If any answer is yes, correct the documentation or architecture decision before implementation.
