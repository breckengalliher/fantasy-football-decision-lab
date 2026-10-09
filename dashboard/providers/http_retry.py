"""Bounded retries for idempotent source reads, never database mutations."""
import time
import requests


def get_with_retry(url, *, attempts=3, timeout=20, **kwargs):
    if not 1 <= attempts <= 3:
        raise ValueError("Source retry limit must be between one and three")
    for attempt in range(attempts):
        try:
            response = requests.get(url, timeout=timeout, **kwargs)
            response.raise_for_status()
            return response
        except requests.RequestException as error:
            status = getattr(error.response, "status_code", None)
            transient = isinstance(error, (requests.Timeout, requests.ConnectionError)) or status in {429, 500, 502, 503, 504}
            if not transient or attempt + 1 == attempts:
                raise
            time.sleep(.5 * 2 ** attempt)
