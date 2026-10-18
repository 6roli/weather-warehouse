"""Tiny HTTP helper (standard library only) with retries for flaky public APIs."""

import json
import time
import urllib.error
import urllib.request

USER_AGENT = "weather-warehouse/0.1 (+https://github.com/6roli/weather-warehouse)"


class SourceError(RuntimeError):
    """A data source could not be read after retrying."""


def get_bytes(url: str, headers: dict[str, str] | None = None, attempts: int = 3, timeout: int = 60) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            last_error = error
            # 4xx (except 429) will not fix itself: a wrong key or parameter.
            if 400 <= error.code < 500 and error.code != 429:
                break
        except (urllib.error.URLError, TimeoutError) as error:
            last_error = error
        time.sleep(5 * attempt)
    raise SourceError(f"GET {redact(url)} failed: {last_error}")


def get_json(url: str, headers: dict[str, str] | None = None, encoding: str = "utf-8") -> object:
    return json.loads(get_bytes(url, headers).decode(encoding))


def redact(url: str) -> str:
    """Never let an API key end up in logs or bronze files."""
    if "api_key=" not in url:
        return url
    head, _, tail = url.partition("api_key=")
    rest = tail.split("&", 1)
    return head + "api_key=***" + ("&" + rest[1] if len(rest) > 1 else "")
