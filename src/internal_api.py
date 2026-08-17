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
    return {"status": "ok", "service": "training-api"}


@app.post("/internal/activities/{activity_id}/resync")
def resync_activity_endpoint(activity_id: str, request: Request):
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
