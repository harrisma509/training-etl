# Training API Architecture and Operations

## Overview

The Training API is the controlled application boundary between Training Intelligence data and consuming applications. It exposes narrow, purpose-built HTTP endpoints over authoritative data produced by the Training ETL pipeline and stored in PostgreSQL.

The API exists to prevent consumers from coupling directly to ETL-owned tables, calculations, and internal schemas. Consumers request stable application-level resources while the ETL and database remain free to evolve behind those contracts.

The current primary consumers are:

- The Training Intelligence web application
- The Embedded AI Coach orchestration layer in `training-web`
- Internal operational and diagnostic workflows

The central architectural rule is:

> Training ETL owns ingestion, normalization, derived metrics, Weekly Audit calculations, and authoritative training state. Training API exposes bounded read and write contracts. Consumers interpret the returned data but do not reimplement the calculations.

---

## Goals

The Training API should:

- Expose authoritative Training Intelligence data through stable contracts
- Keep PostgreSQL credentials and internal schemas away from browser code
- Prevent `training-web` and AI-provider adapters from querying ETL tables directly
- Provide narrow endpoints tailored to product workflows
- Validate request parameters and response shapes
- Use parameterized SQL
- Return JSON-safe values
- Fail with sanitized, actionable errors
- Support internal authentication for sensitive server-to-server endpoints
- Bound response size and query cost
- Preserve data ownership boundaries
- Remain testable without production services

The Training API should not:

- Duplicate ETL calculations
- Recalculate Weekly Audit, Load, TID, Fitness, Fatigue, Form, or recovery scoring in route handlers
- Expose arbitrary SQL access
- Expose database credentials or internal tokens
- Return raw database driver objects
- Send data directly to an AI provider
- Store AI-provider conversation state
- Become the durable store for Coach sessions and messages
- Allow browser clients to access internal Coach context endpoints directly

---

## High-Level Architecture

```text
External data sources
    |
    v
Training ETL
    |
    |-- ingest
    |-- normalize
    |-- calculate derived metrics
    |-- produce Weekly Audit and training state
    v
PostgreSQL
    |
    v
Training API
    |
    |-- public/browser-facing resources
    |-- internal server-to-server resources
    |-- request validation
    |-- response shaping
    |-- bounded queries
    |-- sanitized errors
    v
Consumers
    |
    |-- training-web dashboard
    |-- AI Coach orchestration
    |-- operational tools
```

### Service ownership

| Concern | Owner |
|---|---|
| Source ingestion | Training ETL |
| Data normalization | Training ETL |
| Derived training metrics | Training ETL |
| Weekly Audit calculation | Training ETL |
| Authoritative PostgreSQL state | Training ETL / PostgreSQL |
| API contracts and query boundaries | Training API |
| Dashboard presentation | training-web |
| Coach sessions and messages | training-web / PostgreSQL |
| AI-provider calls | training-web |
| Model-facing coaching policy | training-web |
| Provider usage and cost accounting | training-web |

---

## Repository Placement

The exact repository layout should remain the source of truth. A typical organization is:

```text
training-etl/
├── docs/
│   └── TRAINING_API.md
├── api/
│   ├── application entrypoint
│   ├── route modules
│   ├── authentication
│   ├── database helpers
│   └── schemas or serializers
├── sql/
│   └── authoritative database schema
├── tests/
├── Dockerfile
└── docker-compose.yml or deployment configuration
```

Do not reorganize the repository solely to match this example. Document the actual module paths in this file when they are confirmed from source.

---

## API Boundary

The Training API has two conceptual surfaces.

### Browser-facing API

Browser-facing endpoints support the Training Intelligence application. These endpoints should expose only the data needed by the UI and should never disclose:

- Database credentials
- Internal API tokens
- Provider API keys
- Raw SQL
- Internal stack traces
- Arbitrary health or training records outside the endpoint's documented scope

Browser-facing endpoint authentication and authorization should follow the deployment's security model. The current trusted-LAN deployment is not a substitute for authentication if the application later becomes externally accessible.

### Internal API

Internal endpoints support trusted service-to-service workflows. The AI Coach context endpoint is the primary example:

```text
GET /internal/coach/context/current
```

Internal endpoints:

- Must require the configured internal token
- Must not be called directly from browser JavaScript
- Must return only the bounded contract needed by the consuming service
- Must not expose arbitrary query controls
- Must not log sensitive response bodies
- Must return sanitized errors

---

## Internal Authentication

The current internal authentication convention uses:

```http
X-Internal-Token: <server-side secret>
```

The consuming `training-web` service reads the token from:

```env
TRAINING_API_TOKEN=<secret>
```

The API service must validate the request header against its configured token using the repository's established secure comparison behavior.

### Requirements

- The secret is configured through the runtime environment.
- The secret is never committed to source control.
- The secret is never returned in an API response.
- The secret is never printed in logs.
- Browser code never receives the token.
- Missing or invalid tokens return a sanitized authorization response.
- Token comparison should avoid unnecessary timing leakage where the current framework supports constant-time comparison.
- Token rotation should require only environment updates and service recreation, not source edits.

### Trusted network is defense in depth

Container-network isolation and LAN-only access reduce exposure, but internal authentication remains necessary. Before external or multi-user access, add a complete authorization model rather than relying on the internal token for browser users.

---

## AI Coach Context Endpoint

### Endpoint

```text
GET /internal/coach/context/current
```

### Purpose

Return a single time-aligned, authoritative, model-facing context package for the Embedded AI Coach.

The endpoint allows `training-web` to fetch a complete current coaching snapshot without:

- Querying ETL-owned tables directly
- Reimplementing training calculations
- Making multiple loosely synchronized API calls
- Guessing which current and historical records belong together

### Consumer

The endpoint is called by `training-web` immediately before each real Coach-provider request.

```text
User presses Send
    |
    v
training-web creates durable user message and started turn
    |
    v
training-web calls /internal/coach/context/current
    |
    v
Training API authenticates and assembles authoritative context
    |
    v
training-web adds bounded recent conversation and Coach policy
    |
    v
training-web calls configured AI provider
```

### Required top-level sections

The current `training-web` client requires these sections:

```text
as_of
week_progress
current_weekly_audit
latest_completed_weekly_audit
weekly_load_history
weekly_tid_history
recent_days
fitness_fatigue_form
recovery_history
athlete_narrative
coverage
missing_subjective_context
```

The API contract may include additional documented sections, but these required sections must remain stable or be versioned deliberately.

### Section responsibilities

#### `as_of`

Provides time alignment for the context, such as:

- Current date
- Context generation timestamp
- Current week boundary
- Time-zone assumptions

All date interpretations should use the application's documented local time zone when calendar-day or training-week semantics depend on local time.

#### `week_progress`

Describes how much of the current week has elapsed. This allows consumers to distinguish a partial week from a completed week.

Potential fields include:

- Week start
- Week end
- Current day number
- Days elapsed
- Days remaining
- Partial-week or completed-week state

#### `current_weekly_audit`

Returns the current week's authoritative audit state.

The current week may be provisional. The endpoint should preserve fields such as:

```text
is_provisional = true
evaluation_state = partial_week
```

The API must not convert provisional findings into completed-week failures.

#### `latest_completed_weekly_audit`

Returns the most recent fully completed Weekly Audit. This is the stable comparison anchor for Coach interpretation.

#### `weekly_load_history`

Returns bounded weekly Load history needed for recent trend interpretation.

The endpoint should return persisted ETL results rather than recalculate Load in API code.
The `weekly_rows` query parameter controls this bound. Rows are ordered by
`week_start DESC`, and fewer available rows are returned without synthesis.

#### `weekly_tid_history`

Returns bounded weekly TID history.

The API must preserve the ETL definition and should not silently change units, rounding, or derivation.
The same `weekly_rows` bound applies, with deterministic newest-first ordering.

#### `audit_history` and weekly commentary

`audit_history` and the recent weekly commentary in `athlete_narrative` use the
same configured weekly bound. Commentary uses the corresponding calendar
lookback of `7 * weekly_rows` days. Current and latest-completed audit snapshots
remain separate single-week anchors and are not expanded by this setting.

#### `recent_days`

Returns sparse `daily_training` rows in an inclusive calendar-day window ending on the Training API's current `America/Denver` date. The internal endpoint accepts the bounded server-to-server query parameter:

```text
GET /internal/coach/context/current?daily_days=28
```

`daily_days` defaults to `28` when omitted for trusted legacy callers and must be an integer from `7` through `365` when supplied. Invalid values are rejected before database access. Existing rows are returned only; rest days are not synthesized. Rows are ordered newest first. Depending on the authoritative schema, each row may include:

The endpoint also accepts:

```text
GET /internal/coach/context/current?daily_days=28&weekly_rows=26
```

`weekly_rows` defaults to `26` when omitted for trusted legacy callers and must
be an integer from `4` through `104` when supplied. Blank, malformed, float-like,
duplicate, boolean, and out-of-range values are rejected before database access.
The value bounds `weekly_load_history`, `weekly_tid_history`, `audit_history`,
and recent weekly commentary consistently; coverage reports actual returned
weekly rows rather than the configured maximum. Authentication remains required
through `X-Internal-Token`.

- Activity date
- Activity type
- Duration
- Load
- Intensity or zone exposure
- Elevation
- Distance
- Strength or prehab activity
- Relevant commentary

The endpoint should avoid returning unbounded raw activity history. The parameter is server-to-server only and still requires `X-Internal-Token`.

#### `fitness_fatigue_form`

Returns the persisted model values used by Training Intelligence.

The API returns these values as calculated. It does not reinterpret Form as complete readiness.

#### `recovery_history`

Returns bounded sleep and recovery information, which may include:

- Sleep duration
- HRV
- Resting heart rate
- Recovery state or score
- Coverage indicators

Missing data must remain missing rather than being converted to zero or normal.

#### `athlete_narrative`

Returns athlete-entered or application-maintained narrative relevant to coaching, such as:

- Weekly commentary
- Risk notes
- Injury-week flags
- Travel notes
- Planned events
- Subjective context

Narrative must remain distinguishable from measured data.

#### `coverage`

Describes data availability and completeness. Coverage allows consumers to reason about uncertainty without inferring that absent values are normal.

#### `missing_subjective_context`

Lists questions or subjective dimensions that are not currently known and could materially affect a recommendation, such as:

- Pain
- Freshness
- Soreness
- Illness
- Coordination
- Schedule constraints

The Coach may use this section to ask one concise follow-up question.

---

## Context Contract Principles

### Authoritative values

The context endpoint returns source-of-truth application values. Consumers must not replace or independently recalculate:

- Load
- TID
- Fitness
- Fatigue
- Form
- Weekly Audit status
- Recovery scoring

### Time alignment

All context sections should describe a coherent as-of state. Avoid combining:

- A new current-day activity set
- An older audit snapshot
- A recovery record from a future or mismatched reporting window

If some sections update on different schedules, document timestamps or as-of fields clearly.

### Bounded output

Every historical array must have an intentional bound.

Current observed Coach context includes approximately:

```text
Recent days: 10
Weekly Load rows: 12
```

These values are runtime observations and should not replace explicit code-level constants or contract tests.

### Stable null semantics

Use:

- `null` for an unavailable scalar
- `[]` for a known empty collection
- explicit coverage fields for unavailable source data

Do not use zero to represent missing values.

### Deterministic ordering

Historical arrays should have documented ordering, preferably chronological or reverse chronological according to the consuming use case. Tests should enforce that order.

### JSON safety

Database-specific values must be converted into JSON-compatible representations, including:

- Date and timestamp values
- Decimal values
- Interval-like values
- Database JSON types

Do not expose raw driver objects.

---

## Data Flow for an AI Coach Turn

The Training API participates in only one part of the complete Coach turn.

```text
1. Browser submits message to training-web
2. training-web persists user message and started turn
3. training-web calls Training API context endpoint
4. Training API reads authoritative state from PostgreSQL
5. Training API returns bounded JSON context
6. training-web joins context with recent local conversation
7. training-web calls OpenAI or another configured provider
8. training-web persists assistant response and usage
9. Browser receives persisted result
```

The Training API does not:

- Receive the user's Coach session history
- Call OpenAI
- Store the assistant answer
- Calculate provider cost
- Manage provider response IDs
- Render Markdown

---

## What the Training API Sends and Does Not Send

### Returned to `training-web`

The internal Coach context response can include sensitive information required for approved coaching use, such as:

- Sleep and recovery
- Recent rides and training activities
- Weight-related trends or flags
- Injury notes
- Weekly risk commentary
- Athlete narrative
- Training history

### Not sent directly to OpenAI by Training API

The Training API returns context only to the authenticated internal consumer. `training-web` decides how to assemble the provider request.

This separation matters:

```text
Training API owns authoritative context contract
training-web owns provider disclosure and AI orchestration
AI provider owns bounded inference only
```

### Not stored in Coach tables by Training API

The Training API does not persist the complete model-facing context into Coach session tables. Coach persistence remains owned by `training-web`.

---

## Database Access

### Query rules

- Use parameterized SQL.
- Do not interpolate user input into SQL strings.
- Select only required columns.
- Bound arrays and result sets.
- Avoid N+1 query patterns.
- Use read-only queries for read endpoints.
- Use transactions for related writes.
- Do not hold transactions open across external network calls.

### Schema ownership

The authoritative schema belongs to the ETL repository. API queries may depend on documented views, tables, or functions, but the API contract should shield consumers from unnecessary schema details.

When a schema change affects an endpoint:

1. Update ETL/schema logic.
2. Update API query and response shaping.
3. Update contract tests.
4. Update this documentation if the public or internal contract changes.
5. Deploy in an order that preserves compatibility.

### Views versus route calculations

Prefer performing authoritative calculations in ETL-owned SQL, materialized views, or ETL processing rather than in route code.

Route code should primarily:

- Validate
- Query
- Shape
- Serialize
- Authorize
- Return

---

## Error Handling

The API should return sanitized errors that describe the category of failure without exposing implementation details.

### Typical status behavior

```text
400 Invalid request or parameter
401/403 Missing or invalid authorization
404 Resource not found
409 Conflicting state
429 Rate or capacity limit, where applicable
500 Unexpected internal failure
502 Invalid upstream response, where applicable
503 Required service or configuration unavailable
504 Upstream timeout
```

### Logging

Server logs may include:

- Safe endpoint name
- Safe request identifier
- Safe internal category
- Stack trace for operational diagnosis under the existing logging policy

Server logs must not include:

- Internal token values
- Database passwords
- OpenAI keys
- Complete health or training context payloads
- Athlete narrative bodies
- Raw provider requests or responses

---

## Endpoint Inventory

The exact endpoint inventory must be generated from the repository's actual route modules. Do not rely on this document as the only source of truth.

### Confirmed internal endpoint

```text
GET /internal/coach/context/current
```

### Inventory template

Add each confirmed endpoint using this format:

```markdown
### `GET /path`

**Purpose**

Describe the bounded workflow supported by the endpoint.

**Authentication**

- Browser-facing authentication, internal token, or trusted-network-only legacy behavior

**Parameters**

- Name, type, valid range, and default

**Response**

- Stable top-level fields
- Ordering and bounds
- Null semantics

**Errors**

- Expected HTTP statuses and sanitized detail

**Data owner**

- ETL table/view/function or application domain, without exposing credentials
```

### Recommended inventory generation

As a maintenance task, inspect route decorators and produce a reviewed endpoint list. Do not generate or publish database internals automatically without review.

---

## Deployment Configuration

The exact Compose service names and ports must be verified from the repository deployment files.

### Known consumer configuration

`training-web` uses:

```env
TRAINING_API_BASE_URL=http://training-api:8090
TRAINING_API_TOKEN=<secret>
```

The internal Docker network resolves `training-api` by service/container name.

Do not use `127.0.0.1` from inside `training-web` to reach a different container. In a container, `127.0.0.1` refers to that same container.

### Environment-change rule

Environment changes require container recreation:

```bash
docker compose up -d --force-recreate <service-name>
```

Dependency changes require an image rebuild:

```bash
docker compose up -d --build --force-recreate <service-name>
```

Source-only behavior depends on the runtime configuration. Development auto-reload should not be assumed in production.

---

## Safe Operational Checks

### Verify consumer configuration without printing secrets

From the `training-web` container:

```bash
docker exec training-web python -c 'import os; print("Training API:", os.getenv("TRAINING_API_BASE_URL") or "missing"); print("Training API token:", "configured" if os.getenv("TRAINING_API_TOKEN") else "missing")'
```

### Verify Coach context retrieval without an AI call

```bash
docker exec -i training-web python - <<'PY'
from context_client import fetch_current_context

context = fetch_current_context()
print("Context fetch: success")
print("Current date:", context["as_of"]["current_date"])
print("Current audit:", "available" if context["current_weekly_audit"] else "missing")
print("Completed audit:", "available" if context["latest_completed_weekly_audit"] else "missing")
print("Recent days:", len(context["recent_days"]))
print("Weekly load rows:", len(context["weekly_load_history"]))
PY
```

This check validates:

- Container DNS
- Base URL
- Internal-token authentication
- Required response contract
- JSON serialization

It does not call the AI provider and does not incur provider cost.

### Logs

```bash
docker logs --tail 100 training-api
```

Avoid printing the complete process environment or secret-bearing environment files.

---

## Testing Strategy

### Unit tests

Use deterministic synthetic data and mocked database access to test:

- Parameter validation
- Authentication behavior
- Response shaping
- Required context sections
- JSON conversion
- Bounds
- Ordering
- Null handling
- Error mapping
- Token rejection

### Query contract tests

Use fake cursors or an isolated test database to verify:

- Parameterized SQL
- Expected query count
- No N+1 behavior
- Correct ordering
- Session or resource filtering
- Correct limits
- No write query in read endpoints

### Integration tests

Use a non-production PostgreSQL database or controlled fixture environment to validate:

- Actual SQL compatibility
- Data-type serialization
- View/table availability
- Time-zone behavior
- Empty/missing data
- Partial-week and completed-week transitions

### Consumer contract tests

`training-web` and Training API should share agreement on required Coach context sections.

At minimum, test the presence and type of:

```text
as_of
week_progress
current_weekly_audit
latest_completed_weekly_audit
weekly_load_history
weekly_tid_history
recent_days
fitness_fatigue_form
recovery_history
athlete_narrative
coverage
missing_subjective_context
```

Avoid independent duplicated contract definitions drifting silently. A versioned schema or shared test fixture may be appropriate in V2.

### Production smoke test

A production smoke test should:

1. Call the internal endpoint from `training-web`.
2. Print only non-sensitive coverage metadata.
3. Confirm required sections.
4. Avoid printing narrative, sleep, weight, injury, or complete context payloads.
5. Avoid calling OpenAI.

---

## Observability

The API should record or expose safe operational metrics such as:

- Request count by endpoint
- Status code count
- Latency
- Database query latency
- Response size
- Authentication failures
- Context contract failures
- Context generation timestamp or age

Do not attach sensitive payload contents to metrics or logs.

### Coach context observability roadmap

Useful future measurements include:

- Serialized characters by context section
- Row count by bounded history section
- Contract version
- Source freshness by section
- Missing-section count
- Response generation latency
- Total serialized response size

These measurements can help reduce redundant model context without removing safety-critical data.

---

## Performance and Bounds

### General rules

- Every list endpoint has a default and maximum limit.
- Every historical context array has a fixed bound.
- Query ordering is deterministic.
- Large text fields are returned only when the consumer needs them.
- Internal aggregate endpoints avoid repeated consumer round trips.
- Indexes should support filtering and ordering used by the API.

### AI Coach context

The current `training-web` guard rejects model-facing authoritative context above:

```text
240,000 serialized characters
A 240,000-character guard protects against runaway context, but it is not primarily a spending limit. It also protects latency, model focus, provider-window headroom, and accidental payload expansion. Your explicit per-turn and monthly spending limits remain the real cost controls.

```

The Training API should normally remain well below that ceiling. The ceiling is a consumer safety guard, not a target response size.

Do not add more context simply because the provider supports a large context window. Add a field only when it improves a documented coaching decision.

---

## Privacy and Sensitive Data

The API may return health-adjacent and personal training information to approved consumers, including:

- Sleep
- HRV
- Resting heart rate
- Weight trends
- Injury notes
- Activity patterns
- Weekly commentary
- Athlete narrative

### Requirements

- Minimize each endpoint to its intended purpose.
- Keep internal endpoints off the public browser surface.
- Do not log complete payloads.
- Do not expose secrets.
- Document downstream provider disclosure separately.
- Apply authentication and ownership checks before multi-user access.
- Preserve the difference between measured data and athlete-reported narrative.

The Training API itself does not opt data into AI-provider training. Provider data controls belong to the consuming AI orchestration service.

---

## Versioning and Compatibility

The current internal context endpoint is unversioned. As the contract grows, use deliberate compatibility practices:

- Add optional fields without removing existing fields.
- Avoid changing field meaning in place.
- Preserve null and ordering semantics.
- Coordinate required-field changes with `training-web`.
- Add a contract version when incompatible evolution becomes likely.

Potential future response metadata:

```json
{
  "contract_version": "coach-context-v1",
  "generated_at": "...",
  "as_of": {},
  "coverage": {}
}
```

Do not add versioning merely for appearance. Add it when it will be enforced and tested.

---

## API Layer Roadmap

### 1. Complete endpoint inventory

Generate and review a complete route inventory from the actual source. Document purpose, authentication, bounds, response shape, and ownership.

### 2. Formal Coach context schema

Add a machine-validated schema for `/internal/coach/context/current`.

Goals:

- Type validation
- Clear optional versus required fields
- Contract-version support
- Better consumer tests
- Safer refactoring

### 3. Context-section freshness

Add section-level timestamps or freshness metadata when source schedules differ.

Example:

```json
{
  "coverage": {
    "weekly_audit_as_of": "...",
    "recovery_as_of": "...",
    "recent_days_as_of": "..."
  }
}
```

### 4. Context observability

Measure response size and section contribution without logging content.

### 5. Shared authentication improvements

Before broader deployment:

- Rotate internal tokens cleanly
- Consider service identity or short-lived credentials
- Add browser-user authentication and authorization separately
- Enforce per-user resource ownership

### 6. Rate limiting

Add appropriate rate limits for expensive or sensitive endpoints when the trusted-LAN assumption changes.

### 7. Health and readiness endpoints

Separate:

- Process liveness
- Database readiness
- Required-schema readiness
- Optional source freshness

Do not expose secrets or detailed schema information publicly.

### 8. OpenAPI and generated documentation

If the framework supports OpenAPI, keep generated schemas accurate and add concise endpoint descriptions. Generated API documentation should supplement, not replace, architectural documentation.

### 9. Consumer contract fixtures

Maintain synthetic Coach context fixtures that represent:

- Normal complete week
- Partial week
- Injury week
- Missing recovery data
- No recent rides
- Travel week
- High-load week
- Strength/prehab missing during partial week

Use these fixtures for both API and Coach orchestration tests where practical.

### 10. Query-performance review

Profile critical endpoints and add indexes only from observed query plans and runtime evidence.

---

## Known Limitations

- The exact complete endpoint inventory is not documented in this file until generated from actual route modules.
- The internal Coach context endpoint is currently unversioned.
- Internal authentication uses a shared token rather than workload identity.
- Trusted-LAN deployment is not sufficient for future multi-user external access.
- Context sections may update on different source schedules unless explicitly timestamped.
- Consumer cost and provider behavior are outside the Training API boundary.
- The Training API depends on authoritative ETL schema availability.

---

## Change Checklist

When adding or changing an API endpoint:

- [ ] Confirm the data owner.
- [ ] Avoid duplicating ETL calculations.
- [ ] Define authentication requirements.
- [ ] Validate every external parameter.
- [ ] Use parameterized SQL.
- [ ] Select only needed columns.
- [ ] Add explicit bounds and ordering.
- [ ] Preserve null semantics.
- [ ] Shape JSON-safe responses.
- [ ] Return sanitized errors.
- [ ] Avoid logging sensitive payloads.
- [ ] Add unit and contract tests.
- [ ] Add integration coverage when SQL changes.
- [ ] Update consumer tests.
- [ ] Update this document if the contract changes.
- [ ] Verify no secrets were committed.

---

## Recommended Next Documentation Step

Inspect the repository's actual route modules and append a complete reviewed endpoint inventory to this document.

For each route, capture:

1. Method and path
2. Purpose
3. Caller
4. Authentication
5. Parameters
6. Response contract
7. Bounds and ordering
8. Data owner
9. Error behavior
10. Tests

Avoid guessing endpoint names or schemas. The implementation remains the source of truth.
