import hashlib
import hmac
import os
import time
from typing import Any
from urllib.parse import quote

import requests
from dotenv import load_dotenv
from loguru import logger

load_dotenv()


class StatizAPIError(RuntimeError):
    """HTTP error from the Statiz API with response content preserved."""

    def __init__(self, method: str, endpoint: str, status_code: int, body: str) -> None:
        self.method = method
        self.endpoint = endpoint
        self.status_code = status_code
        self.body = body
        super().__init__(
            f"{method} {endpoint} failed with status={status_code} body={body}"
        )


class StatizAPIClient:
    """Statiz Baseball API Client with HMAC-SHA256 authentication"""

    def __init__(self, base_url: str = "https://api.statiz.co.kr/baseballApi"):
        self.base_url = base_url.rstrip("/")
        api_key = os.getenv("API_KEY")
        api_secret = os.getenv("API_SECRET")

        if api_key is None or api_secret is None:
            raise ValueError("API_KEY and API_SECRET must be set in .env file")

        self.api_key: str = api_key
        self.api_secret: str = api_secret
        self.request_delay_seconds = float(
            os.getenv("STATIZ_REQUEST_DELAY_SECONDS", "5.0")
        )
        self.rate_limit_cooldown_seconds = float(
            os.getenv("STATIZ_RATE_LIMIT_COOLDOWN_SECONDS", "300.0")
        )
        self.request_timeout_seconds = float(
            os.getenv("STATIZ_REQUEST_TIMEOUT_SECONDS", "60.0")
        )
        self.network_error_cooldown_seconds = float(
            os.getenv("STATIZ_NETWORK_ERROR_COOLDOWN_SECONDS", "60.0")
        )
        self._last_request_at = 0.0

    def _wait_for_rate_limit(self) -> None:
        """Throttle all API calls to avoid provider-side blocking."""
        elapsed = time.monotonic() - self._last_request_at
        remaining = self.request_delay_seconds - elapsed
        if remaining > 0:
            time.sleep(remaining)

    def _normalize_query(self, params: dict[str, Any]) -> str:
        """Normalize query parameters with official encodeURIComponent semantics."""
        if not params:
            return ""
        safe = "-_.!~*'()"
        return "&".join(
            f"{quote(str(key), safe=safe)}={quote(str(params[key]), safe=safe)}"
            for key in sorted(params.keys())
        )

    def _generate_signature(
        self, method: str, path: str, query: str, timestamp: str
    ) -> str:
        """Generate HMAC-SHA256 signature"""
        payload = f"{method}|{path}|{query}|{timestamp}"
        secret_bytes = self.api_secret.encode("utf-8")
        payload_bytes = payload.encode("utf-8")
        signature = hmac.new(secret_bytes, payload_bytes, hashlib.sha256)
        return signature.hexdigest()

    def _get_headers(
        self, method: str, path: str, params: dict[str, Any] | None = None
    ) -> dict[str, str]:
        """Generate authentication headers"""
        # Normalize path (remove /baseballApi prefix)
        clean_path = path.replace("/baseballApi", "").lstrip("/")

        # Normalize query
        query = self._normalize_query(params or {})

        # Timestamp
        timestamp = str(int(time.time()))

        # Signature
        signature = self._generate_signature(method, clean_path, query, timestamp)

        return {
            "X-API-KEY": self.api_key,
            "X-TIMESTAMP": timestamp,
            "X-SIGNATURE": signature,
            "Content-Type": "application/json",
        }

    def get(
        self, endpoint: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Make GET request to API with conservative retry handling."""
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        last_error: Exception | None = None

        for attempt in range(5):
            self._wait_for_rate_limit()
            headers = self._get_headers("GET", endpoint, params)
            self._last_request_at = time.monotonic()
            try:
                response = requests.get(
                    url,
                    headers=headers,
                    params=params,
                    timeout=self.request_timeout_seconds,
                )
            except requests.Timeout as exc:
                last_error = exc
                wait = min(self.request_delay_seconds * (attempt + 1), 60.0)
                logger.warning(
                    "Request timed out after {}s - retrying in {}s (attempt {})",
                    self.request_timeout_seconds,
                    wait,
                    attempt + 1,
                )
                time.sleep(wait)
                continue
            except requests.RequestException as exc:
                last_error = exc
                wait = min(
                    self.network_error_cooldown_seconds * (attempt + 1),
                    300.0,
                )
                logger.warning(
                    "Request failed with {} - retrying in {}s (attempt {})",
                    type(exc).__name__,
                    wait,
                    attempt + 1,
                )
                time.sleep(wait)
                continue

            if response.status_code == 429:
                wait = min(self.rate_limit_cooldown_seconds * (attempt + 1), 600.0)
                logger.warning(
                    "429 Too Many Requests - retrying in {}s (attempt {})",
                    wait,
                    attempt + 1,
                )
                time.sleep(wait)
                continue

            response.raise_for_status()
            return dict(response.json())

        raise RuntimeError(
            f"GET {endpoint} failed after retry attempts"
        ) from last_error

    def post(
        self,
        endpoint: str,
        data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make POST request to API"""
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        headers = self._get_headers("POST", endpoint, params)

        self._wait_for_rate_limit()
        self._last_request_at = time.monotonic()
        response = requests.post(
            url,
            headers=headers,
            json=data,
            params=params,
            timeout=self.request_timeout_seconds,
        )
        if response.status_code >= 400:
            body = _response_body(response)
            logger.warning(
                "POST {} failed status={} body={}",
                endpoint,
                response.status_code,
                body,
            )
            raise StatizAPIError("POST", endpoint, response.status_code, body)

        return dict(response.json())

    def post_form_data(
        self,
        endpoint: str,
        data: dict[str, Any],
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make POST request with multipart/form-data text fields."""
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        headers = self._get_headers("POST", endpoint, params)
        headers.pop("Content-Type", None)
        files = {key: (None, str(value)) for key, value in data.items()}

        self._wait_for_rate_limit()
        self._last_request_at = time.monotonic()
        response = requests.post(
            url,
            headers=headers,
            files=files,
            params=params,
            timeout=self.request_timeout_seconds,
        )
        if response.status_code >= 400:
            body = _response_body(response)
            logger.warning(
                "POST {} failed status={} body={}",
                endpoint,
                response.status_code,
                body,
            )
            raise StatizAPIError("POST", endpoint, response.status_code, body)

        return dict(response.json())

    def save_prediction(self, s_no: int, percent: float) -> dict[str, Any]:
        """Submit prediction result to Statiz API"""
        payload = {"s_no": s_no, "percent": round(percent, 2)}
        return self.post_form_data("prediction/savePrediction", data=payload)


def _response_body(response: requests.Response) -> str:
    """Return a compact response body for failure logging."""
    try:
        parsed = response.json()
    except ValueError:
        text = response.text.strip()
    else:
        text = str(parsed)
    return text[:1000]
