# Training Intelligence Engineering Constitution

> **Purpose:** Define the stable engineering principles, authority hierarchy, and cross-repository rules for Training Intelligence.
>
> **Audience:** Human developers, product planners, coding agents, planning agents, reviewers, and deployment operators.
>
> **Scope:** This document governs decisions that cross features or repositories. It intentionally references detailed repository documents instead of duplicating their commands, contracts, route inventories, limits, or runbooks.

---

## 1. Authority and Required Reading

Before planning, investigating, editing, testing, or deploying a change, read the applicable documents in this order:

1. This constitution.
2. The repository-local `.github/copilot-instructions.md`.
3. The relevant architecture or feature contract.
4. The repository-local `docs/TESTING_GUIDE.md`.
5. The current schema, API contract, or operational runbook when the task touches those areas.

### Canonical repository documents

#### `training-etl`

- `training-etl/.github/copilot-instructions.md`: repository ownership, schema safety, ETL rules, and coding-agent constraints.
- `training-etl/docs/TESTING_GUIDE.md`: exact test workflow, isolation requirements, and completion reporting.
- `training-etl/docs/TRAINING_API.md`: Training API architecture, authentication, context contract, deployment behavior, and API operations.
- `training-etl/docs/targeted_activity_resync.md`: single-activity correction workflow and affected-date rebuild behavior.
- `training-etl/docs/logging_and_logrotate.md`: persistent-log ownership, rotation, validation, and append checks.
- `training-etl/README.md`: current runtime, operations, monitoring, backup, restore, and service deployment model.
- `training-etl/sql/training_postgress_db_schema.sql`: authoritative monolithic schema artifact.

#### `training-web`

- `training-web/.github/copilot-instructions.md`: web ownership, frontend rules, safety, deployment, and validation expectations.
- `training-web/docs/TESTING_GUIDE.md`: exact web test workflow, JavaScript boundary, isolation, and completion reporting.
- `training-web/docs/AI_DEV_GUIDE.md`: web-layer development workflow, database policy, error handling, and deployment principles.
- `training-web/docs/AI_COACH.md`: authoritative AI Coach architecture, request lifecycle, policy, limits, privacy, and roadmap.
- `training-web/docs/AI_COACH_CONTEXT_RECEIPT_DESIGN.md`: receipt purpose, schema, immutability, allowlist, and excluded content.
- `training-web/docs/AI_COACH_CUSTOM_INSTRUCTIONS_DESIGN.md`: Custom Instructions ownership, validation, compilation, and authority limits.
- `training-web/docs/AI_COACH_DURABLE_MEMORIES_DESIGN.md`: Durable Memory schema, eligibility, routing, limits, and precedence.
- `training-web/docs/AI_COACH_SETTINGS_DESIGN.md`: persisted Coach settings, validation, and orchestration integration.
- `training-web/docs/COMPONENTS_SERVICE_API.md`: service-event contracts, historical snapshots, two-clock semantics, and Components UI adoption.
- `training-web/docs/FRONTEND_REFACTOR_HANDOFF.md`: current vanilla-JavaScript ownership model and safe refactor sequence.
- `training-web/README.md`: web-layer purpose, runtime, deployment, and repository boundary.

### Conflict handling

Use this precedence when instructions conflict:

1. Data integrity, user safety, and explicit current product decisions.
2. This constitution.
3. Repository-local Copilot instructions.
4. Current feature architecture and API contracts.
5. Testing and operational runbooks.
6. Existing implementation details.

Existing code is evidence of current behavior, not automatic proof that the behavior is correct.

If a lower-level document intentionally differs from this constitution, document the exception and obtain explicit approval rather than silently overriding the constitution.

---

## 2. Required Agent Behavior

Planning and coding agents must:

- Investigate before coding.
- Confirm the repository root, branch, current commit, and working-tree state.
- Identify the authoritative owner of the requested behavior.
- Distinguish durable facts, derived values, transient data, and presentation state.
- State the expected files and validation plan before editing.
- Prefer one coherent increment over a broad implementation.
- Preserve and distinguish Mike's existing manual edits.
- Run focused tests before complete affected suites.
- Report only validation that actually occurred.
- Stop when ownership, authority, or safety cannot be established confidently.

Agents must not:

- Guess schema, ownership, routes, contracts, date semantics, or deployment behavior.
- Create a giant implementation prompt spanning multiple independent increments.
- Hide defects with larger fetch windows, broader rebuilds, retries, buffers, or CSS clipping when the root cause is discoverable.
- Expand into an adjacent feature, framework, migration, or refactor without approval.
- Commit, push, deploy, use SSH or Docker, access production data, mutate production state, or make paid-provider calls unless explicitly authorized.

When asked to create a GitHub Copilot coding-agent prompt, save the final prompt as a downloadable `.txt` file rather than printing the full prompt in chat.

---

## 3. Core Engineering Principles

### 3.1 Truth over convenience

Prefer **unknown** over **incorrect**.

- Missing data stays missing.
- Null does not silently become zero.
- Absence does not silently become normal, healthy, or recovered.
- Review, partial, provisional, and unclassified states are valid product outcomes.

### 3.2 Authoritative ownership must be obvious

Every important fact and calculation must have one clearly identified owner. Consumers may interpret authoritative values, but must not independently recreate them.

### 3.3 User-entered facts are durable

Synchronization, ingestion, model inference, and aggregate rebuilding must not overwrite user-authored information.

Examples include Daily Check-ins, Weekly Commentary, service history, Durable Memories, Custom Instructions, and Coach conversations.

### 3.4 Derived data is rebuildable

Daily, Weekly, Load, TID, Fitness, Fatigue, Form, Weekly Audit, and yearly rollups are derived artifacts. Their formulas and rebuild behavior remain owned by the documented authoritative layer.

A rebuildable table must never become the durable home of user-authored facts.

### 3.5 Expose uncertainty

Do not manufacture confidence for a cleaner interface. Show missing, partial, review, provisional, or unclassified states when the available evidence requires them.

### 3.6 Trust is a product feature

Correctness, provenance, explainability, bounded behavior, safe correction, and honest validation are visible product qualities, not merely implementation concerns.

### 3.7 Process is part of the goal

Training Intelligence should improve through sustainable practice:

1. Build the smallest useful capability.
2. Use it in normal life.
3. Observe defects and friction.
4. Improve from evidence.

Maximum feature count is not the objective.

---

## 4. Repository and Service Boundaries

### 4.1 `training-etl`

`training-etl` owns ingestion, normalization, authoritative training calculations, database writes for ETL-managed data, schema artifacts, Daily and Weekly builders, Weekly Audit, and the implementation of `training-api`.

The exact boundary is defined in `training-etl/.github/copilot-instructions.md`, `training-etl/README.md`, and `training-etl/docs/TRAINING_API.md`.

### 4.2 `training-api`

`training-api` is the narrow authenticated boundary over authoritative Training Intelligence data and approved ETL operations.

It validates, queries, shapes, serializes, bounds, and authorizes. It must not become an arbitrary SQL surface, AI-provider client, or duplicate calculation engine.

Use `training-etl/docs/TRAINING_API.md` for the current endpoint, authentication, response, deployment, and operational contracts.

### 4.3 `training-web`

`training-web` owns the FastAPI browser application, dashboard presentation, static frontend, application-managed CRUD where assigned, Coach persistence and orchestration, settings, memories, receipts, and provider integration.

It must not duplicate ETL calculations or silently redefine schema semantics.

Use `training-web/.github/copilot-instructions.md`, `training-web/docs/AI_DEV_GUIDE.md`, and `training-web/README.md` for current rules.

### 4.4 PostgreSQL and AI providers

PostgreSQL is the durable system of record.

AI providers perform bounded inference only. AI providers do not own authoritative data, durable conversation history, product policy, or user-managed memory.

---

## 5. Data Classification and Ownership

### 5.1 Persisted activity facts

`strava_activities` is the authoritative persisted activity-level source for Training Intelligence.

A bounded external response may identify changes, but does not replace persisted history or prove deletion.

### 5.2 Rebuildable training aggregates

`daily_training`, `weekly_training`, `daily_fitness_fatigue`, Weekly Audit, and annual rollups are derived data.

They must be rebuilt from documented authoritative inputs and must never overwrite their source facts.

### 5.3 Athlete-reported subjective facts

`daily_checkin` contains durable, date-specific athlete reports. It remains independent from activity presence and calculated training values.

Daily Check-ins do not automatically alter Load, TID, Fitness, Fatigue, Form, recovery scoring, Weekly Audit, Weekly Commentary, or Durable Memories.

### 5.4 Curated interpretation

`weekly_commentary` contains curated week-level interpretation. Daily flags may inform a weekly decision, but must not silently rewrite weekly classifications.

### 5.5 Components and service history

Physical component life and maintenance recency are separate clocks. Maintenance does not reset physical component life unless the event represents a qualifying installation or replacement.

Use `training-web/docs/COMPONENTS_SERVICE_API.md` as the authoritative detailed contract for actions, snapshots, clock states, compatibility behavior, and UI adoption.

### 5.6 Coach personalization

- Custom Instructions define stable coaching and communication preferences.
- Durable Memories contain intentionally curated long-term facts.
- Conversation history supplies bounded continuity.
- Daily Check-ins and current narrative represent current direct reports.
- Training Intelligence remains authoritative for measured and calculated facts.

Use the dedicated AI Coach design documents for exact schemas, limits, routing, and compilation order.

---

## 6. ETL and Synchronization Invariants

### 6.1 Persisted facts drive aggregates

Build affected aggregates from the complete persisted authoritative set, not solely from transient or bounded fetch results.

This invariant comes directly from the September 2026 disappearing-activity incident.

### 6.2 Bounded fetches identify change, not complete truth

A bounded fetch may identify changed records, affected dates, or deletion candidates. It must not be assumed to represent every fact for every local date included in the response.

### 6.3 Rebuild scope is explicit

Every rebuild must identify:

- The authoritative records that changed
- Old and new affected dates
- Aggregates that require rebuilding
- Empty affected rows that should be removed
- Downstream calculations that must be refreshed

### 6.4 Date and timezone semantics are explicit

Use documented America/Denver semantics where local days or weeks matter. Test lower boundaries, upper boundaries, current-day behavior, UTC conversion, and daylight-saving transitions.

### 6.5 Deletion requires affirmative evidence

Absence from a bounded list is not proof of deletion. Ambiguous source errors preserve data.

Detailed targeted repair behavior is documented in `training-etl/docs/targeted_activity_resync.md`. Any future deletion-reconciliation feature requires its own approved contract and regression coverage.

### 6.6 Related mutations are atomic

Related authoritative and aggregate mutations should commit or roll back together when consistency requires it.

Do not hold database write transactions open across external network calls unless an explicitly reviewed design proves that no safer boundary exists.

### 6.7 Repeated execution is idempotent

Repeating the same sync, rebuild, resync, or reconciliation against unchanged facts must not create duplicates, drift, repeated deletion, or changed aggregates.

### 6.8 Validate relationships, not only process success

A process can complete successfully while producing plausible but incomplete data. Where consequences justify it, reconcile source IDs, aggregate IDs, counts, categories, chronology, and lifecycle baselines.

---

## 7. AI Coach Constitutional Rules

The detailed implementation contract lives in `training-web/docs/AI_COACH.md` and its supporting design documents. The following rules are cross-cutting and stable.

### 7.1 The current question is primary

Memories, conversation, and authoritative context support the current request. They do not replace it.

### 7.2 Authority and conflict order remain explicit

Current clinician guidance and direct user corrections outrank stored background. Training Intelligence owns current measured and calculated facts. Product policy controls safety. Custom Instructions define stable preferences. Durable Memories personalize but yield to newer authoritative facts.

### 7.3 Direct athlete reports remain distinct

Current athlete reports may outweigh optimistic modeled readiness for an immediate decision. Measured, modeled, remembered, conversational, and athlete-reported information must remain distinguishable.

### 7.4 Missing data remains unknown

No report of pain, injury, stress, sleep, readiness, or equipment state does not imply a favorable condition.

### 7.5 Context is bounded and explainable

Add context only when it improves a documented coaching decision. Standard context ceilings are safety guards, not targets.

Context Receipts are immutable, bounded, and allowlisted. Use `training-web/docs/AI_COACH_CONTEXT_RECEIPT_DESIGN.md` for the exact receipt contract.

### 7.6 Safety outranks optimization

Clinician guidance, current injury, poor sleep, travel recovery, and meaningful safety concerns outrank goals, catch-up behavior, and routine progression.

Coach may interpret data and recommend conservative action, but must not diagnose or replace medical care.

### 7.7 Provider calls are explicit

Saving, viewing, editing, deleting, searching, exporting, syncing, or managing settings must not trigger a provider call unless that workflow has been explicitly approved as AI-powered.

Provider requests remain subject to the controls documented in `training-web/docs/AI_COACH.md` and `training-web/docs/AI_COACH_SETTINGS_DESIGN.md`.

### 7.8 Conversation modes change lens, not truth

Future conversation templates may alter framing, response strategy, context emphasis, or memory weighting. They must not change authoritative data, safety policy, cost controls, privacy boundaries, or clinician-priority rules.

### 7.9 Coaching supports practice, not only milestones

Riding, strength, prehab, recovery, maintenance, and restraint are repeated practices. Coach should support long-term consistency, reflection, learning, and readiness for the next meaningful session, not merely weekly or monthly target completion.

---

## 8. User Experience Principles

### 8.1 Compact, useful, expandable

Prefer concise summaries and direct actions, with detail available on demand. Avoid duplicate information, giant controls, excessive whitespace, and repeated labels.

### 8.2 One obvious home per task

A capability should have one natural management surface. Avoid multiple editors for the same data or actions whose object ownership is unclear.

### 8.3 Labels identify the object

Prefer explicit labels such as `Edit Component`, `Edit Service Event`, and `Delete Check-in` when multiple record types exist.

### 8.4 Phone and tablet are first-class

Every user-facing change must consider phone, tablet portrait, tablet landscape, and desktop behavior. Exact validation expectations live in the relevant feature handoff and `training-web` instructions.

### 8.5 Accessibility is required

Preserve native semantics, keyboard access, visible focus, labels, described errors, appropriate ARIA relationships, non-color cues, and usable touch targets.

### 8.6 Fix layout root causes

Do not use global overflow clipping, arbitrary width reduction, or hidden content as the first response to layout defects. Identify the controlling element and ownership rule.

### 8.7 Preserve the current frontend architecture

The frontend is intentionally vanilla JavaScript with shared state, API, and feature modules. Use `training-web/docs/FRONTEND_REFACTOR_HANDOFF.md` for current ownership and safe refactor guidance. Do not introduce a framework or broad rewrite without an approved architecture decision.

---

## 9. Development and GHC Workflow

### 9.1 Investigate ownership first

Before editing, determine:

- Which repository owns the behavior
- Which source owns the truth
- Whether the data is durable, derived, or transient
- Which consumers depend on the contract
- What must remain unchanged

### 9.2 Use bounded implementation slices

Separate investigation, contract design, schema/backend, frontend, AI context, migration, and production validation when they carry different risks.

### 9.3 One objective per coding-agent prompt

A coding-agent prompt should specify:

- One coherent objective
- Required grounding documents
- Locked product decisions
- Expected files
- Preserve-unchanged behavior
- Early-exit conditions
- Focused and complete validation
- Explicit prohibitions
- Completion-report format

### 9.4 Fix root causes before mitigations

Recovery actions may be necessary, but must not be mislabeled as permanent fixes.

### 9.5 Wait and See is valid

Do not add persistent fields, settings, frameworks, agents, or automation until normal use proves the simpler design insufficient.

### 9.6 Preserve manual edits

When Mike has edited code manually, inspect the current diff, preserve and distinguish the edits, and add the smallest tests that prove the intended behavior. Do not weaken assertions to force green results.

The exact reusable workflow is documented in each repository's `docs/TESTING_GUIDE.md`.

### 9.7 Protect attention and opportunity cost

Evaluate work using user value, safety, review time, GHC credits, provider cost, testing burden, and the opportunity cost of displacing riding, recovery, work, or family priorities.

---

## 10. Testing and Validation Governance

Do not duplicate the detailed test commands or completion checklists here. Use:

- `training-etl/docs/TESTING_GUIDE.md`
- `training-web/docs/TESTING_GUIDE.md`

The stable constitutional rules are:

1. Reproduce or define the intended behavior.
2. Add the smallest deterministic regression test for changed behavior.
3. Run the focused test first.
4. Run the complete affected repository suite.
5. Run the required syntax and diff checks.
6. Perform separate browser, database, runtime, API, or provider validation when the change requires it.
7. Report what was and was not validated.

Default automated tests must remain isolated from paid providers, Strava, production PostgreSQL, production services, Docker, SSH, deployment, backup, restore, and production credentials.

Architecture invariants deserve tests. Examples include aggregate ownership, user-data durability, service-clock separation, provider-call prevention, receipt privacy, settings validation, and verified deletion behavior.

A green unit suite does not by itself prove schema compatibility, deployment correctness, browser behavior, or production integration.

---

## 11. Deployment, Operations, and Logging Governance

Use the exact deployment and operational procedures documented in each repository's instructions and README.

Stable constitutional rules:

- Git is the source of truth.
- Confirm repository, branch, commit, and working-tree state before deployment.
- Deploy or restart the service that owns the changed contract.
- Validate expected behavior after deployment.
- Treat schema changes as high risk and review backup/restore impact.
- Never expose secrets or sensitive payloads.

For persistent operational logs, follow `training-etl/docs/logging_and_logrotate.md`. Do not duplicate or improvise a separate rotation policy.

For Training API environment, service-recreation, and operational checks, follow `training-etl/docs/TRAINING_API.md` and `training-etl/README.md`.

For web deployment and live validation, follow `training-web/.github/copilot-instructions.md`, `training-web/docs/AI_DEV_GUIDE.md`, and `training-web/README.md`.

---

## 12. Documentation Governance

### 12.1 Architecture documents own detail

This constitution defines stable principles. Feature documents own exact routes, fields, limits, commands, UI behavior, and current implementation status.

Do not copy detailed contracts into this file when an authoritative repository document already exists.

### 12.2 Incidents become durable lessons

A meaningful production incident should record impact, root cause, why detection was difficult, correction, validation, and prevention.

If the incident establishes a cross-cutting invariant, update this constitution. Otherwise, update the owning architecture or runbook document.

### 12.3 Product decisions become repository assets

Move important decisions from chat into the appropriate architecture document, contract, test, or backlog record.

### 12.4 Documentation must match production

Do not describe planned behavior as complete. Distinguish current implementation, deployed validation, future roadmap, and Wait-and-See work.

### 12.5 Closeout separates deferred work from incomplete work

Sprint and incident closeout must distinguish delivered behavior, administrative closeout, known limitations, deferred backlog, and evidence-triggered future items.

---

## 13. Backlog and Architecture Governance

### 13.1 Evidence drives complexity

Preferred sequence:

1. Build
2. Use
3. Observe
4. Improve

### 13.2 Reliability before convenience

Data integrity and trust outrank speed, polish, and feature breadth.

### 13.3 Static AI context is not the answer to every question

Expand routine context only when evidence shows value. Prefer typed, allowlisted, bounded retrieval for specialized or longer historical questions.

### 13.4 Search and export are integration capabilities

Search, filter, preview, and documented CSV export can enable Excel, Copilot, Coach, and other trusted analysis without creating a custom integration for every question.

Sensitive fields remain excluded by default, and exports must preserve units, provenance, bounds, and timezone semantics.

### 13.5 Alerts require trustworthy semantics

Do not build proactive maintenance, battery, training, recovery, or sync alerts on uncertain source logic. Deduplication, resolution, snooze, and state transitions are product behavior, not cosmetic implementation details.

### 13.6 Multi-agent complexity requires evidence

Do not introduce agent swarms or generic orchestration frameworks merely to enforce process. Prefer this constitution, repository instructions, architecture documents, prompt templates, tests, and focused review.

---

## 14. Required Completion Report

Every agent implementation report should include:

1. Objective
2. Authoritative ownership found
3. Files changed by repository
4. Contracts or schema changed
5. Data, null, date, and transaction semantics
6. Tests added or updated
7. Focused and complete suite results
8. Syntax and diff checks
9. Browser, database, runtime, API, and provider validation actually performed
10. Validation not performed
11. Privacy, logging, deployment, and backup impact where relevant
12. Final `git status --short`
13. Unresolved risks or blockers
14. Whether anything was committed, pushed, deployed, restarted, or mutated

Never claim validation that did not occur.

---

## 15. Constitutional Review Checklist

Before approving a feature or fix, ask:

### Data

- What is authoritative?
- What is derived?
- What is user entered?
- What can be rebuilt?
- What must never be overwritten?
- Are null, zero, missing, and unknown distinct?

### Architecture

- Which repository and service own the behavior?
- Is logic duplicated?
- Are boundaries authenticated and bounded?
- Are network calls outside write transactions?
- Which authoritative document defines the detailed contract?

### AI

- Is the context necessary and explainable?
- Are direct reports distinct from modeled data?
- Does the workflow require a paid call?
- Are receipts safe and useful?
- Does missing data remain unknown?

### UX

- Is there one obvious home?
- Is the affected object clear?
- Does it work across supported screen sizes?
- Is it accessible?
- Does it expose uncertainty honestly?

### Testing

- Is there a focused deterministic regression?
- Did the complete affected suite run?
- Were production services excluded from automated tests?
- What validation remains manual?

### Operations

- Which service must be deployed, recreated, or restarted?
- Does the migration affect backups or restores?
- Does logging follow the existing runbook?
- Is rollback or recovery defined?

### Product

- Is this solving observed friction?
- Can the simpler model work?
- Is Wait and See more appropriate?
- Is the result worth the review time and opportunity cost?

---

## 16. Constitutional Statement

Training Intelligence exists to help a real athlete make better long-term decisions using trustworthy data, durable context, safe correction, and explainable coaching.

When a future decision conflicts with this constitution, prefer the outcome that best preserves:

1. Truth
2. Data integrity
3. Safety
4. Human trust
5. Clear ownership
6. Simplicity
7. Long-term maintainability
8. Sustainable incremental improvement

**Trust is a feature. The process is part of the goal.**
