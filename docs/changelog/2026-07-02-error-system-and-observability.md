# 2026-07-02 Error System and Observability

## Summary

This change upgrades the WebUI error path from ad-hoc responses to a structured
application error system, then adds the first production-oriented observability
layer around it.

The work is intentionally split into small boundaries:

- HTTP error contracts live in `webui_new/core/errors.py`.
- Logging setup lives in `utils/structured_logging.py`.
- Metrics, upstream classification, and alert signals live in
  `utils/observability.py`.
- Readiness checks live in `utils/preflight.py`.
- Public error-code documentation lives in `docs/error-codes.md`.

## Phase 1 Hardening

- Added request-id middleware for WebUI requests.
- Echoes `X-Request-ID` on API responses.
- Replaced raw `str(e)` API responses with user-safe messages.
- Added frontend `ApiError` handling around API status, code, message, and
  request id.
- Truncated and sanitized JSON-parser logging so full model/provider payloads
  are not dumped into logs.
- Added contract tests for 400/500 and stream error behavior.

## Phase 2 Error Contract

- Added `AppError` as the base application error type with:
  - `code`
  - `message`
  - `status_code`
  - `details`
  - `retryable`
  - `log_level`
  - `component`
  - `debug_message`
- Added semantic error subclasses:
  - `ValidationError`
  - `ConfigError`
  - `UpstreamError`
  - `StorageError`
  - `BusinessError`
  - `InternalError`
- Unified FastAPI error responses to:

```json
{
  "success": false,
  "error": {
    "code": "ERROR_CODE",
    "message": "用户可见文案",
    "details": {},
    "request_id": "request-id"
  }
}
```

- Updated route handlers to raise semantic errors instead of returning scattered
  `{"error": ...}` payloads.
- Updated streaming errors to:

```json
{
  "type": "error",
  "code": "STREAM_FAILED",
  "message": "处理失败，请稍后重试",
  "request_id": "request-id",
  "retryable": true
}
```

- Updated the frontend to read both the new nested error contract and the older
  flat Phase 1 shape for safer rollout.
- Added a guard that converts internal agent error results, such as
  `status=error` with `data.error="Error in input stream"`, into
  `AGENT_EXECUTION_FAILED` instead of streaming the raw agent error as normal
  assistant text.
- Added explicit `asyncio.CancelledError` handling for streaming client
  disconnects. These are logged and counted as `STREAM_CANCELLED` with a
  synthetic 499 status; no error event is yielded because the client socket is
  already closed.

## Phase 3 Observability

- Added `JsonFormatter` and `configure_logging()` in
  `utils/structured_logging.py`.
- Added `HOMMEY_LOG_FORMAT=json|text`; text remains the default for local
  development.
- Structured error logs now include:
  - `request_id`
  - `user_id`
  - `route`
  - `method`
  - `status_code`
  - `error_code`
  - `component`
  - `duration_ms`
  - `debug_message`
- `debug_message` is sanitized and only written to logs; it is never included
  in API responses.
- Added a dependency-free metrics abstraction in `utils/observability.py`:
  - `MetricsSink`
  - `InMemoryMetricsSink`
  - Prometheus-style text rendering
- Added upstream error classification for:
  - `timeout`
  - `rate_limited`
  - `auth_failed`
  - `connection_failed`
  - `bad_response`
  - `circuit_open`
  - `dependency_missing`
  - `storage_unavailable`
  - `unknown`
- Added alert signals as metrics plus structured logs:
  - `http_5xx`
  - `upstream_timeout`
  - `circuit_open`
  - `db_connect_failure`
- Added WebUI runtime endpoints:
  - `/healthz`
  - `/readyz`
  - `/metrics`

## Preflight Checks

`utils/preflight.py` adds componentized readiness checks for:

- API key presence.
- Optional model-service probe.
- Redis ping when short-term memory backend is `redis`.
- Postgres `SELECT 1` when long-term memory backend is `postgres`.
- RAG embedding model path readability.
- Milvus data directory read/write permission.
- MCP enabled-server configuration.

The model-service probe is disabled by default to keep local development fast
and network-independent. Set `HOMMEY_PREFLIGHT_INCLUDE_NETWORK=true` to include
it in `/readyz`.

## Documentation

- Added `docs/error-codes.md`.
- Documented public error codes, HTTP status, component ownership, retryability,
  user-visible messages, and internal meanings.
- Documented observability fields, runtime endpoints, and alert signals.

## Tests

- Added/updated tests for:
  - WebUI error response contract.
  - Stream error contract.
  - Internal agent error results normalized into stream error events.
  - Raw exception hiding.
  - JSON logging sanitization.
  - Metrics rendering.
  - Alert signal metrics.
  - Preflight component checks.
  - `/healthz`, `/readyz`, and `/metrics`.
  - Required structured error-log fields.

Validation performed:

```bash
PYTHONPATH=. pytest -q tests/test_observability.py tests/test_webui_error_responses.py tests/test_logging_safety.py
PYTHONPATH=. python -m compileall -q utils webui_new tests/test_observability.py
PYTHONPATH=. pytest -q
```

The focused observability/error tests pass. The full suite currently has one
pre-existing RAG/Windows-path compatibility failure in
`tests/test_rag_pipeline.py::test_rebuild_collection_prepares_windows_manifest_before_drop`,
where monkeypatching `os.name="nt"` causes `pathlib` to instantiate
`WindowsPath` on a non-Windows system.
