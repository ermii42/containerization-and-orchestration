from prometheus_client import Counter, Histogram, Gauge

REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status_code"]
)

REQUEST_DURATION = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)

REQUESTS_IN_PROGRESS = Gauge(
    "http_requests_in_progress",
    "Requests currently in progress",
    ["method", "endpoint"]
)

FAIL_COUNTER = Counter(
    "provoked_failures_total",
    "Number of provoked 5xx errors via /fail"
)