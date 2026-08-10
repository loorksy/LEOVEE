from __future__ import annotations

import threading
from collections import defaultdict

_lock = threading.Lock()
_request_total: dict[tuple[str, str, str], int] = defaultdict(int)
_request_duration_sum: dict[tuple[str, str], float] = defaultdict(float)


def record_http_request(
    *,
    method: str,
    path: str,
    status_code: int,
    duration_seconds: float,
) -> None:
    key = (method.upper(), _normalize_path(path))
    status_bucket = _status_bucket(status_code)
    with _lock:
        _request_total[(key[0], key[1], status_bucket)] += 1
        _request_duration_sum[key] += duration_seconds


def _status_bucket(status_code: int) -> str:
    if status_code < 400:
        return "2xx"
    if status_code < 500:
        return "4xx"
    return "5xx"


def _normalize_path(path: str) -> str:
    parts = [p for p in path.split("/") if p]
    normalized: list[str] = []
    for part in parts:
        if len(part) == 36 and part.count("-") == 4:
            normalized.append("{id}")
        else:
            normalized.append(part)
    return "/" + "/".join(normalized) if normalized else "/"


def prometheus_text() -> str:
    lines = [
        "# HELP http_requests_total Total HTTP requests",
        "# TYPE http_requests_total counter",
        "# HELP http_request_duration_seconds_sum HTTP request duration sum",
        "# TYPE http_request_duration_seconds_sum counter",
    ]
    with _lock:
        for (method, path, bucket), count in sorted(_request_total.items()):
            lines.append(
                f'http_requests_total{{method="{method}",path="{path}",status="{bucket}"}} {count}'
            )
        for (method, path), total in sorted(_request_duration_sum.items()):
            lines.append(
                f'http_request_duration_seconds_sum{{method="{method}",path="{path}"}} {total:.6f}'
            )
    lines.append("# HELP leovee_up Leovee API process is running")
    lines.append("# TYPE leovee_up gauge")
    lines.append("leovee_up 1")
    return "\n".join(lines) + "\n"
