"""Synchronous HTTP boundary for ETL-owned operations.

This module is intentionally thin. It owns request validation, internal token
authentication, and the translation between HTTP failures and sanitized JSON
responses. All training-data work remains in the authoritative ETL code.

training-api owns only:
- HTTP request validation
- internal token authentication
- calling existing ETL functions
- returning sanitized results
- mapping failures to HTTP responses

training-api does not own:
- Strava normalization
- direct activity-field patching
- Daily calculations
- Weekly calculations
- training-load calculations
- gear or service-event logic
- background job processing
- queue or polling behavior

Handlers must call existing ETL functions instead of reproducing ETL business
logic. The current activity resync handler calls resync_activity(CFG,
activity_id) directly.

The internal API token is loaded through the existing configuration mechanism,
must not be logged, and must not be returned to browser JavaScript. Token
comparisons use hmac.compare_digest.
"""

import hmac

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from resync_activity import resync_activity
from settings import get_config

app = FastAPI(title="Training API")
CFG = get_config()

training_api_token = CFG.get("TRAINING_API_TOKEN")
if not training_api_token or not str(training_api_token).strip():
    raise RuntimeError("Missing TRAINING_API_TOKEN configuration")


@app.get("/health")
def health():
    """Return a minimal health response for container checks.

    Purpose: confirm Uvicorn is serving the FastAPI app.
    Authentication: none.
    Inputs: none.
    Success result: {"status": "ok", "service": "training-api"}
    Error behavior: this endpoint does not validate ETL credentials or DB health.
    Side effects: none.
    """
    return {"status": "ok", "service": "training-api"}


@app.post("/internal/activities/{activity_id}/resync")
def resync_activity_endpoint(activity_id: str, request: Request):
    """Synchronously resync a single Strava activity through the ETL function.

    Purpose: call the existing resync_activity(CFG, activity_id) implementation.
    Authentication: requires X-Internal-Token header and a valid configured token.
    Inputs: positive decimal activity_id in the URL path.
    Success result: the sanitized JSON dictionary returned by the ETL resync.
    Error behavior: invalid IDs return HTTP 400; missing or invalid tokens return
    HTTP 401; ETL failures return a generic sanitized HTTP 500 with the activity id.
    Side effects: refreshes the target Strava activity, updates DB state, and may
    rebuild affected Daily rows and selective Weekly aggregates.
    """
    try:
        activity_id_int = int(activity_id)
    except (TypeError, ValueError):
        return JSONResponse(status_code=400, content={"status": "error", "error": "Invalid activity id"})

    if activity_id_int <= 0 or str(activity_id).strip() == "" or not str(activity_id).strip().isdigit():
        return JSONResponse(status_code=400, content={"status": "error", "error": "Invalid activity id"})

    provided_token = request.headers.get("X-Internal-Token")
    expected_token = training_api_token

    if not provided_token or not hmac.compare_digest(provided_token, expected_token):
        return JSONResponse(status_code=401, content={"status": "error", "error": "Unauthorized"})

    try:
        result = resync_activity(CFG, activity_id_int)
    except Exception:
        return JSONResponse(
            status_code=500,
            content={"status": "error", "error": "Resync failed", "activity_id": activity_id_int},
        )

    return result
