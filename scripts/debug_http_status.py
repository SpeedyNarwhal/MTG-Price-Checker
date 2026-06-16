from __future__ import annotations

import re

import requests

URLS = [
    "https://www.danireon.com/search?q=Sol%20Ring&type=product",
    "https://silvergoblin.cards/search?q=Sol%20Ring&type=product",
    "https://silvergoblin.cards/products/sol-ring-223-commander-2017",
]

HEADER_SETS = {
    "current/simple app headers": {
        "User-Agent": "mtg-price-checker/0.1 personal-use price checker",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    },
    "browser-like headers": {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    },
}


def main() -> None:
    for header_name, headers in HEADER_SETS.items():
        for url in URLS:
            try:
                response = requests.get(url, headers=headers, timeout=20)
                body_preview = _collapse_whitespace(response.text)[:120]
                content_type = response.headers.get("Content-Type", "")
                status_code = str(response.status_code)
            except requests.RequestException as exc:
                body_preview = str(exc)
                content_type = ""
                status_code = "REQUEST_ERROR"

            print(f"headers: {header_name}")
            print(f"url: {url}")
            print(f"status: {status_code}")
            print(f"content-type: {content_type}")
            print(f"body: {body_preview}")
            print()


def _collapse_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


if __name__ == "__main__":
    main()
