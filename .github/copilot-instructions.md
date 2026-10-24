## Required Engineering Grounding

Before planning, investigating, or changing code, read:

1. `docs/ENGINEERING_CONSTITUTION.md`
2. The relevant architecture or feature document
3. `docs/TESTING_GUIDE.md`

The Engineering Constitution defines cross-repository principles.
This file defines repository-specific mandatory instructions.
Feature documents define detailed contracts and current behavior.

# GitHub Copilot Instructions for training-etl

## Mandatory fresh-session Git gate

Before any mutating work, every new or resumed session MUST run the
[Fresh-Session Git Synchronization Gate](../docs/ENGINEERING_CONSTITUTION.md#fresh-session-git-synchronization-gate)
in this repository and every affected sibling repository. Run `git fetch
origin` as part of the preflight; stale remote-tracking refs are not proof of
current state. A dirty, divergent, active-operation, cross-repository mismatch,
or unverifiable remote state is a hard STOP, not a warning. Do not
automatically pull, rebase, merge, reset, clean, stash, overwrite, or
force-push unpreserved work.

Before deployment, the tested commit MUST be on the intended release branch,
the worktree MUST be clean, no Git operation may be active, and local `HEAD`
MUST equal freshly fetched `origin/main` exactly. Record the preflight and
release hashes.

## Session-Aware Documentation Policy

Determine whether the current work is occurring in a fresh GHC session or a continuing GHC session.

### Fresh session

Before editing:

1. Read this repository instruction file.
2. Read only the directly relevant sections of the Engineering Constitution, Frontend Architecture, Testing Guide, and applicable ADRs.
3. Run the required fresh-session Git synchronization gate.
4. Do not broadly read unrelated documentation or source modules.

A fresh session must establish enough authoritative context to work safely, but it must use targeted section reads rather than automatic whole-document reads.

### Continuing session

If the relevant governance documents were already read during the current GHC session and have not changed:

- Reuse the established session context.
- Do not reread unchanged governance documents.
- Do not repeat the fresh-session architecture inventory.
- Do not repeat broad source or documentation searches.
- Do not reread documents merely because a new prompt was pasted into the same session.

Reread a document only when:

1. Git shows that the document changed since it was last read;
2. the task reaches an unclear ownership, architecture, testing, security, data, or deployment boundary; or
3. a test or live validation exposes an assumption that requires authoritative verification.

When rereading is necessary, read only the relevant section rather than the complete document.

### Session determination

Use available conversation and tool history to determine whether the current GHC session already read the relevant documents.

- If the current session history clearly shows that the documents were read, treat the session as continuing.
- If the session is new, history is unavailable, or prior reads cannot be established confidently, treat the session as fresh.
- Never rely on a persistent repository marker claiming that a prior session read the documents. Such a marker could become stale and cause a fresh session to skip required guidance.

### Change detection

When useful, check whether governance documents changed since the current session's starting commit with a narrow command equivalent to:

```bash
git diff --name-only <session-start-commit>..HEAD -- \
  .github/copilot-instructions.md \
  docs/ENGINEERING_CONSTITUTION.md \
  docs/FRONTEND_ARCHITECTURE.md \
  docs/TESTING_GUIDE.md \
  docs/ARD
```

Adapt paths to the repository's actual structure. Do not run this command repeatedly when no relevant commit or document change occurred.

### Prohibited context waste

- No repeated whole-document reads in the same session.
- No repeated whole-module reads after editing begins.
- No broad architecture discovery after the implementation boundary is known.
- No broad searches after editing begins unless a test exposes an unknown.
- No rereading deployment documentation immediately before deployment when the current session already established the applicable process and the document has not changed.
- No repeated full-suite execution unless source changed or repository policy explicitly requires another run.

### Targeted-read rule

When a document must be consulted:

- search for the relevant heading or term first;
- read the smallest useful line range;
- expand once only if the first range is insufficient;
- avoid reading an entire long document when one section answers the boundary question.

## GHC Autonomy and Server-Safety Guardrails

GHC should move approved work forward autonomously inside a clearly bounded scope. GHC must not turn a narrow defect, test failure, deployment issue, or server observation into an unapproved cleanup or redesign project.

### Autonomy allowed without additional approval

GHC may make a discovered fix without stopping for approval only when all of the following are true:

1. The issue is concrete and directly blocks or invalidates the currently approved task.
2. The fix is narrow, reversible, and within the same ownership boundary.
3. The behavior can be proven with a deterministic test, parity check, syntax check, or read-only validation.
4. The fix does not change production data, schema, security boundaries, lifecycle semantics, public API contracts, or product architecture.
5. The fix does not create a new user-visible capability beyond the approved slice.
6. The exact tested commit can be deployed and rolled back through the documented process.
7. The change avoids unrelated cleanup and formatter churn.

Examples of acceptable autonomous fixes:

- excluding `.pytest_cache`, coverage files, or equivalent local test residue from deployment packaging when those files are clearly non-runtime artifacts;
- correcting deployment-script parity when both documented deployment paths must package the same application content;
- fixing a directly related stale asset-version check;
- correcting a typo, selector, test fixture, or narrow lifecycle hook that directly prevents the approved feature from working;
- adding a focused regression test for the discovered blocking defect.

### Approval required before proceeding

Stop and request a Product Owner decision when any of the following is true:

1. Scope crosses into another repository unexpectedly.
2. A schema, migration, SQL execution, or production-data mutation is required.
3. A security, authentication, authorization, secret-management, or network boundary would change.
4. A public API, persistence contract, lifecycle model, or architecture decision would change.
5. Multiple materially different fixes are plausible and product behavior would differ.
6. The proposed change adds, removes, or substantially alters user-visible behavior outside the approved slice.
7. A deployment or rollback process requires redesign rather than repair.
8. The proposed cleanup is useful but unrelated to the blocking issue.
9. Production state is unknown, ambiguous, or cannot be verified safely.
10. The change would cancel, delete, rewrite, backfill, or bulk-modify production records.
11. Validation would require more production writes than the prompt explicitly authorized.
12. The implementation would exceed the approved file, module, service, or repository boundary.

### Mandatory stop conditions

Stop immediately and report the evidence when:

- the worktree is dirty, unexpectedly diverged, or an active Git operation exists;
- the live or database state is unclear;
- a test exposes a real unrelated defect;
- two narrow patch attempts fail at the same ownership boundary;
- formatter, generated-file, or dependency churn begins;
- implementation would require architecture discovery after the approved boundary is already known;
- repeated browser or test-harness retries are not producing new evidence;
- the exact tested commit cannot be proven equal to the deployed commit;
- a rollback point cannot be preserved;
- actual, derived, financial, health, security, or other protected data could be changed unexpectedly.

### Narrow-fix execution rule

When an autonomous fix is allowed:

1. State the concrete defect and why it blocks the approved task.
2. Identify the smallest ownership boundary and exact files involved.
3. Make no more than two narrow patch attempts at that boundary.
4. Add or update the smallest deterministic regression test.
5. Run focused validation first.
6. Run complete required suites only after the final source change.
7. Review the bounded diff and confirm no unrelated files changed.
8. Include the discovered fix in the final Changed Files and deviation report.
9. Do not use the fix as permission for adjacent cleanup.

### Server and deployment guardrails

GHC may inspect and validate server state through documented read-only commands, health checks, logs, asset metadata, container status, and documented deployment scripts.

GHC may perform a documented, scoped application deployment or restart only when the prompt authorizes deployment and the exact tested commit is known.

GHC must not, without explicit approval:

- run ad hoc server cleanup commands;
- delete caches, files, containers, images, volumes, or logs merely to make a symptom disappear;
- change ownership, permissions, firewall rules, ports, secrets, environment variables, mounts, or service definitions;
- use `sudo`, destructive shell commands, recursive deletion, force flags, or broad wildcard cleanup;
- restart unrelated services;
- deploy ETL, API, database, or other services outside the approved slice;
- execute SQL, migrations, backfills, or data repair;
- perform manual production edits that bypass the application's service boundary;
- replace a documented deployment process with an improvised one.

A scoped restart is allowed only when:

- the documented application deployment requires it;
- startup-derived asset or revision metadata is proven stale;
- only the approved service is restarted;
- health is verified afterward;
- the restart and reason are documented in the completion report.

### Production-write budget

Production writes are prohibited unless the prompt explicitly authorizes them.

When writes are authorized:

- state the exact maximum number and type of writes before execution;
- perform a read-before-write check;
- use stable IDs, not weak title/date/content matching;
- never exceed the authorized count;
- verify the authoritative response;
- perform a read-after-write check;
- never use SQL cleanup to hide validation data unless explicitly approved;
- keep application rollback separate from data rollback.

### Test and browser retry budget

- Prefer deterministic unit, contract, integration, and parity tests over repeated browser automation.
- Use fresh, small browser scenarios.
- Maximum two harness retries for the same browser interaction.
- Do not change product code solely to satisfy a flaky synthetic browser gesture when manual behavior and deterministic contracts prove the product path.
- Manual product behavior remains the acceptance gate for native drag, touch, browser, or device interactions that automation cannot reproduce reliably.
- Do not rerun a complete suite when no source changed.

### Unrelated improvement handling

If GHC discovers a nonblocking improvement:

1. Do not implement it during the current slice.
2. Record it concisely in Risks, Deviations, or Follow-ups.
3. Include the evidence, likely ownership, and recommended future slice or backlog location.
4. Continue the approved task unless the finding creates a safety or correctness stop condition.

### Completion-report requirement

Every completion report involving an autonomous discovered fix must include:

- the discovered issue;
- why autonomous action was permitted;
- the exact files changed;
- the regression proof;
- whether server, deployment, restart, or production actions occurred;
- the tested commit and deployed commit;
- any remaining risk or deferred cleanup.

## Project Overview

This repo contains the ETL, data builders, database writers, schema SQL, Strava sync logic, weekly audit computation, and future service-log import work for the Training Dashboard.

Before any Strava-related work, read `docs/STRAVA_ARCHITECTURE.md` and verify the latest official Strava developer documentation and API reference. Record relevant contract findings before changing Strava code, schema, OAuth, endpoints, fields, webhooks, rate handling, retention, or integrations.

The separate `training-web` repo owns the FastAPI web app, dashboard routes, browser UI, static frontend files, and HarrisServer web deployment.

## Repo Boundary

This repo owns:
- External-source ingestion, including Strava
- OAuth and provider credentials for ETL-owned sources
- Normalization and authoritative field semantics
- ETL-managed writes
- Schema SQL, migrations, and schema evolution
- Daily, Weekly, Load, TID, Fitness, Fatigue, Form, Weekly Audit, and other authoritative calculations
- Historical imports, backfills, rebuilds, reconciliation, and repair logic
- Queue processing and operational ETL scripts
- Implementation and deployment artifacts for `training-runner` and `training-api`

The separate `training-web` repo owns:
- The browser-facing FastAPI application and browser-facing routes
- Dashboard, Search, reporting, narrative, export, and presentation workflows
- Bounded server-side read-only PostgreSQL queries over processed data
- Web-owned application records
- Coach persistence, orchestration, settings, memories, receipts, and AI-provider integration

Do not modify `training-web` files from this repo unless explicitly requested.

The accepted cross-repository and runtime boundary is documented in `docs/ARD/TRAINING_SYSTEM_SERVICE_BOUNDARIES.md`. Read it for work involving database access, internal APIs, Search/reporting, service placement, or cross-service orchestration.

`training-runner` is the asynchronous and scheduled ETL service. It executes scheduled sync, queue-driven work, background ETL, and explicitly invoked backfills or rebuilds. `training-api` is the narrow authenticated synchronous facade over approved ETL functions and coordinated ETL-owned contracts; it is not a universal query layer or the mandatory path for ordinary `training-web` reads.
## Runtime

- ETL runs separately from the web app.
- Database-backed data is consumed by the `training-web` dashboard.
- Schema or ETL changes can break web routes, so validate affected web endpoints after database changes.
- Local `.venv` may differ from the HarrisServer/container runtime.
- Local syntax checks are useful but are not sufficient by themselves.

## Safety Rules

- Keep changes scoped and commit-friendly.
- Do not refactor unrelated ETL modules.
- Do not change database schema unless explicitly requested.
- Do not change weekly audit scoring unless explicitly requested.
- Do not change load/ramp rules unless explicitly requested.
- Do not expose or log tokens, secrets, `.env` values, refresh tokens, access tokens, database passwords, or raw credential-like values.
- Do not commit `.env`, `.venv`, `__pycache__`, `.DS_Store`, generated secrets, or local runtime artifacts.
- Prefer deterministic ETL logic over runtime AI.
- Prefer read-only/planning work before write/import functionality.

## Existing Design Principles

- `gear` is the canonical gear registry.
- `strava_activities` is the source for activity-level gear usage.
- `gear_id` is the stable join key.
- `gear_name` is display text.
- Service components such as Chain, Tires, Brake Pads, Rotors, Fork, Shock, Cassette, and Battery are not gear rows.
- Future service tracking should use dedicated service tables or clean derived views, not overload the `gear` table.
- Service status should be derived from service events plus activity usage.

## Database and Schema Rules

- Treat schema changes as high-risk.
- If schema changes are requested, provide:
  - exact SQL changes
  - affected tables
  - affected ETL modules
  - affected web routes
  - validation queries
  - rollback notes if practical
- Do not silently rename columns or change table semantics.
- Do not make web-facing breaking changes without identifying the matching `training-web` route/UI impact.
- Prefer additive schema changes over destructive changes.

## Weekly Audit Rules

- Weekly Audit V1 exists and writes to `weekly_audit` and `weekly_audit_item`.
- Do not change audit scoring, thresholds, weights, gate-item behavior, or item semantics unless explicitly requested.
- If touching weekly audit code, validate:
  - `compute_weekly_audit.py`
  - `weekly_audit_config.py`
  - `weekly_audit_rules.py`
  - `weekly_audit_scoring.py`
  - `weekly_audit_queries.py`
  - `audit_utils.py`

## Service / Gear Future Work Rules

For future Service_Log work:

- Inspect current workbook mapping before implementation.
- Do not import workbook Service_Dashboard as source of truth.
- Treat Service_Log as maintenance event history.
- Normalize bike/component/action names during import.
- Map bike names to `gear.gear_id` during controlled import.
- Preserve notes and costs.
- Preserve carry-over miles, hours, rides, and elevation where needed.
- Keep service status derived from service events plus `strava_activities`.

Suggested future model:

- `gear` = gear registry
- `service_component` = trackable component per gear item
- `service_event` = maintenance event history
- service status = computed or view-derived result

Do not create service tables unless explicitly requested.

## Validation Required

For Python changes:

1. Run syntax checks on touched Python files.

```bash
./.venv/bin/python -m py_compile src/changed_file.py
```

On Windows, use `.\.venv\Scripts\python.exe -m py_compile src\changed_file.py`.

## Deployment tooling

Use `.\deploy_training_etl.ps1` on Windows or
`./deploy_to_server_from_mac.sh` on macOS/Linux. Both require a clean worktree
whose `HEAD` equals its configured upstream revision and package the same four
members: `src`, `Dockerfile`, `requirements.txt`, and
`docker-compose.server.yml`. Use `-DryRun` or `--dry-run` to inspect the local
archive without upload.

The scripts only stage files and do not rebuild or restart containers. After a
source change, restart the affected ETL service. A Dockerfile or requirements
change requires an image rebuild and recreation; a Compose command, port,
volume, or health-check change requires service/project recreation. Routine
source deployment does not use `--force-recreate`.

## Permanent architecture and execution budget

For frontend ownership and cross-repository boundaries, use
`training-web/docs/FRONTEND_ARCHITECTURE.md` together with this repository's
constitution and the accepted service-boundary ARD. Permanent instructions
and architecture documents are authoritative, followed by executable
contracts, current source, runbooks, and Git history. Temporary prompts and
chat transcripts are not sources of truth.

Apply single-pass rigor: discover once, patch narrowly, validate in order, and
stop when evidence is green.

- One ownership inventory per slice and one focused follow-up search for an
  unclear boundary.
- At most two narrow patch attempts per boundary.
- Restore formatter or line-ending churn immediately; do not rebuild whole
  source files through broad replacement.
- Stop and report when a bounded change requires a broad rewrite.
- Validate in order: focused contract, changed-file syntax, adjacent contracts,
  complete relevant suite, `git diff --check`, and scope review.
- Trust an unchanged green baseline and do not rerun complete suites after they
  are green unless source or test code changes again.
- After commit, push normally and report the final clean status; do not amend,
  force-push, or perform speculative cleanup.

## Automated Testing

- Read [docs/TESTING_GUIDE.md](../docs/TESTING_GUIDE.md) before changing Python behavior.
- Every new or changed Python behavior and every bug fix should add or update focused deterministic tests unless the completion report documents a concrete exception.
- When Mike says he is done with manual edits and asks GHC to update tests, inspect and preserve his uncommitted diff, add the smallest tests that prove the intended behavior, and do not merely update expectations to force green.
- Run focused tests first, then the full suite using the platform-native repository-local interpreter documented in `docs/TESTING_GUIDE.md`.
- Default tests must not access paid providers, external services, production data, Docker, SSH, or deployment.
- `rg` is available on Mike's Mac for focused repository searches. Use it when helpful, but fall back to `grep` or `find` rather than treating it as a required dependency.
- Report exact commands and results.
## SQL Change Lifecycle

All new database changes must follow this lifecycle.

### 1. Create pending SQL

Create the new SQL change script in:

`sql/`

Do not create a new change directly in `sql/Applied/`.

Do not modify an existing script in `sql/Applied/` to implement new behavior.

The pending script must contain:

- the smallest additive database change;
- transaction boundaries where appropriate;
- safe preconditions or idempotency only when justified;
- column and object comments;
- read-only verification queries at the end;
- no unrelated schema cleanup.

### 2. Validate before application

Before asking the Product Owner to apply the script:

- run focused static/schema tests;
- compare the script with the authoritative schema artifact;
- run `git diff --check`;
- prove that only the intended pending SQL, schema artifact, and directly related tests changed;
- do not claim that the migration is applied;
- do not deploy application code that requires the new schema.

### 3. Product Owner applies in DBeaver

The Product Owner applies the pending script manually through DBeaver.

GHC must provide a short operator handoff containing:

- exact script path;
- intended database;
- expected changed object;
- verification queries;
- expected verification results;
- rollback considerations.

GHC must then stop and wait for the Product Owner to report the result.

### 4. Verify the live schema

After the Product Owner reports successful application:

- use the supplied live DDL or approved read-only verification;
- compare only the affected database object;
- confirm that the live object matches the pending script;
- do not inspect the full live schema unless the affected ownership boundary is unclear.

### 5. Move the exact script to Applied

Only after successful live verification:

`sql/<change>.sql`
→
`sql/Applied/<change>.sql`

The move must preserve the script contents exactly. Do not rewrite, expand, or combine the script while moving it.

Update test paths if required so tests reference the script’s final governed location.

### 6. Commit the applied state

The final schema commit may include only:

- the rename/move into `sql/Applied/`;
- the authoritative schema artifact;
- directly related schema tests;
- necessary documentation of the verified live state.

The completion report must distinguish:

- pending script created;
- Product Owner applied it;
- live DDL verified;
- exact script moved to Applied;
- final commit and push completed.

### Applied-script rule

Files in `sql/Applied/` represent changes already applied to the live database.

They may be disposable as execution artifacts, but their location is authoritative migration-state evidence.

Never:

- put an unapplied change directly in `sql/Applied/`;
- assume a script was applied because it is located there;
- modify an applied script to deliver a new schema change;
- deploy schema-dependent application code before live verification;
- recreate an old root-level script because a test points to its prior location.