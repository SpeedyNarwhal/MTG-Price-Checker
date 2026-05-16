import re
from decimal import Decimal
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from mtg_price_checker.domain.enums import CardCondition, Finish
from mtg_price_checker.domain.requested_card import RequestedCard
from mtg_price_checker.domain.store_quote import StoreQuote
from mtg_price_checker.infra.http_client import HttpClient
from mtg_price_checker.stores.base import StoreAdapter

_FACE_TO_FACE_BASE_URL = "https://facetofacegames.com"

_CONDITION_LABELS = {
    "NM": CardCondition.NEAR_MINT,
    "PL": CardCondition.LIGHTLY_PLAYED,
    "MP": CardCondition.MODERATELY_PLAYED,
    "HP": CardCondition.HEAVILY_PLAYED,
    "DMG": CardCondition.DAMAGED,
}

_CONDITION_PATTERN = re.compile(
    r"(?P<label>NM|PL|MP|HP|DMG)\s*"
    r"\((?P<quantity>\d+)\)"
    r"[\s\S]{0,300}?"
    r"Regular price\s+\$(?P<price>\d+(?:\.\d{2})?)",
    re.IGNORECASE,
)

_SET_PATTERN = re.compile(r"Set:\s*(?P<set_name>[\s\S]+?)\s+Type Line:", re.IGNORECASE)
_COLLECTOR_PATTERN = re.compile(r"Collector #:\s*(?P<collector_number>[A-Z0-9\-]+)", re.IGNORECASE)
_FINISH_PATTERN = re.compile(r"Finish:\s*(?P<finish>Non-Foil|Foil)", re.IGNORECASE)


class FaceToFaceStoreAdapter(StoreAdapter):
    def __init__(
        self,
        http_client: HttpClient | None = None,
        max_products_to_check: int = 5,
    ) -> None:
        self._http_client = http_client or HttpClient()
        self._max_products_to_check = max_products_to_check

    @property
    def store_id(self) -> str:
        return "facetoface"

    @property
    def display_name(self) -> str:
        return "Face to Face"

    def search_card(self, requested_card: RequestedCard) -> list[StoreQuote]:
        product_urls = self._search_product_urls(requested_card)
        quotes: list[StoreQuote] = []

        for product_url in product_urls[: self._max_products_to_check]:
            product_html = self._http_client.get_text(product_url)
            quotes.extend(
                parse_face_to_face_product_page(
                    html=product_html,
                    product_url=product_url,
                    requested_card=requested_card,
                )
            )

        return quotes

    def _search_product_urls(self, requested_card: RequestedCard) -> list[str]:
        try:
            suggest_json = self._http_client.get_json(
                f"{_FACE_TO_FACE_BASE_URL}/search/suggest.json",
                params={
                    "q": requested_card.normalized_name,
                    "resources[type]": "product",
                    "resources[limit]": "20",
                },
            )

            product_urls = _extract_product_urls_from_suggest_json(suggest_json)

            if product_urls:
                return product_urls

        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 429:
                raise

        except Exception:
            pass

        search_html = self._http_client.get_text(
            f"{_FACE_TO_FACE_BASE_URL}/search",
            params={
                "q": requested_card.normalized_name,
                "type": "product",
            },
        )

        return _extract_product_urls(search_html)


def parse_face_to_face_product_page(
    html: str,
    product_url: str,
    requested_card: RequestedCard,
) -> list[StoreQuote]:
    soup = BeautifulSoup(html, "html.parser")

    card_name = _extract_card_name(soup)
    raw_title = _extract_raw_title(soup) or card_name

    if card_name is None:
        return []

    if not _card_names_match(requested_card.normalized_name, card_name):
        return []

    page_text = soup.get_text(" ", strip=True)

    finish = _extract_finish(page_text, raw_title)
    set_name = _extract_set_name(page_text)
    collector_number = _extract_collector_number(page_text)

    quotes: list[StoreQuote] = []
    seen: set[tuple[CardCondition, Decimal, int]] = set()

    for match in _CONDITION_PATTERN.finditer(page_text):
        label = match.group("label").upper()
        quantity = int(match.group("quantity"))
        price = Decimal(match.group("price"))
        condition = _CONDITION_LABELS[label]

        dedupe_key = (condition, price, quantity)

        if dedupe_key in seen:
            continue

        seen.add(dedupe_key)

        quotes.append(
            StoreQuote(
                store_id="facetoface",
                requested_card_name=requested_card.normalized_name,
                matched_card_name=card_name,
                condition=condition,
                finish=finish,
                price_cad=price,
                in_stock=quantity > 0,
                product_url=product_url,
                quantity_available=quantity,
                set_name=set_name,
                collector_number=collector_number,
                raw_title=raw_title,
                confidence_score=1.0,
            )
        )

    return quotes


def _extract_product_urls_from_suggest_json(payload: Any) -> list[str]:
    urls: list[str] = []

    if not isinstance(payload, dict):
        return urls

    resources = payload.get("resources")

    if not isinstance(resources, dict):
        return urls

    results = resources.get("results")

    if not isinstance(results, dict):
        return urls

    products = results.get("products")

    if not isinstance(products, list):
        return urls

    for product in products:
        if not isinstance(product, dict):
            continue

        raw_url = product.get("url")

        if not isinstance(raw_url, str):
            continue

        absolute_url = urljoin(_FACE_TO_FACE_BASE_URL, raw_url).split("?")[0]

        if "/products/" not in absolute_url:
            continue

        if absolute_url not in urls:
            urls.append(absolute_url)

    return urls


def _extract_product_urls(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    urls: list[str] = []

    for link in soup.find_all("a", href=True):
        href_value = link.get("href")

        if not isinstance(href_value, str):
            continue

        if "/products/" not in href_value:
            continue

        absolute_url = urljoin(_FACE_TO_FACE_BASE_URL, href_value).split("?")[0]

        if absolute_url not in urls:
            urls.append(absolute_url)

    return urls


def _extract_card_name(soup: BeautifulSoup) -> str | None:
    heading = soup.find("h1")

    if heading is not None:
        card_name = heading.get_text(" ", strip=True)

        if card_name:
            return _strip_face_to_face_title_suffix(card_name)

    raw_title = _extract_raw_title(soup)

    if raw_title is not None:
        return _strip_face_to_face_title_suffix(raw_title)

    return None


def _extract_raw_title(soup: BeautifulSoup) -> str | None:
    meta_title = soup.find("meta", property="og:title")

    if meta_title is not None:
        content = meta_title.get("content")

        if isinstance(content, str) and content.strip():
            return content.strip()

    document_title = soup.find("title")

    if document_title is not None:
        title = document_title.get_text(" ", strip=True)

        if title:
            return title

    return None


def _strip_face_to_face_title_suffix(value: str) -> str:
    # Turns:
    # "Arcane Signet [237] [Commander 2020] [Non-Foil]"
    # into:
    # "Arcane Signet"
    before_bracket = value.split("[", maxsplit=1)[0]
    before_pipe = before_bracket.split("|", maxsplit=1)[0]
    return before_pipe.strip()


def _extract_finish(page_text: str, raw_title: str | None) -> Finish:
    match = _FINISH_PATTERN.search(page_text)

    if match is not None:
        return _finish_from_text(match.group("finish"))

    if raw_title is not None:
        return _finish_from_text(raw_title)

    return Finish.NONFOIL


def _finish_from_text(value: str) -> Finish:
    normalized = value.lower()

    if re.search(r"\bnon[-\s]?foil\b", normalized):
        return Finish.NONFOIL

    if re.search(r"\bfoil\b", normalized):
        return Finish.FOIL

    return Finish.NONFOIL


def _extract_set_name(page_text: str) -> str | None:
    match = _SET_PATTERN.search(page_text)

    if match is None:
        return None

    return match.group("set_name").strip()


def _extract_collector_number(page_text: str) -> str | None:
    match = _COLLECTOR_PATTERN.search(page_text)

    if match is None:
        return None

    return match.group("collector_number").strip()


def _card_names_match(requested_name: str, matched_name: str) -> bool:
    return _simple_normalize(requested_name) == _simple_normalize(matched_name)


def _simple_normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())
