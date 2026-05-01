import re
from decimal import Decimal
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from mtg_price_checker.domain.enums import CardCondition, Finish
from mtg_price_checker.domain.requested_card import RequestedCard
from mtg_price_checker.domain.store_quote import StoreQuote
from mtg_price_checker.infra.http_client import HttpClient
from mtg_price_checker.stores.base import StoreAdapter

_DANIREON_BASE_URL = "https://www.danireon.com"

_CONDITION_LABELS = {
    "Near Mint": CardCondition.NEAR_MINT,
    "Lightly Played": CardCondition.LIGHTLY_PLAYED,
    "Moderately Played": CardCondition.MODERATELY_PLAYED,
    "Heavily Played": CardCondition.HEAVILY_PLAYED,
    "Damaged": CardCondition.DAMAGED,
}

_CONDITION_PATTERN = re.compile(
    r"(?P<condition>Near Mint|Lightly Played|Moderately Played|Heavily Played|Damaged)"
    r"\s*-\s*"
    r"(?:(?P<sold_out_without_price>Sold out)|"
    r"\$(?P<price>\d+(?:\.\d{2})?)\s*CAD"
    r"(?P<sold_out_with_price>\s*-\s*sold out!?)?)",
    re.IGNORECASE,
)

_SET_AND_COLLECTOR_PATTERN = re.compile(
    r"\((?P<set_code>[A-Z0-9]{2,5})-(?P<collector_number>[A-Z0-9]+)\)"
)


class DanireonStoreAdapter(StoreAdapter):
    def __init__(
        self,
        http_client: HttpClient | None = None,
        max_products_to_check: int = 2,
    ) -> None:
        self._http_client = http_client or HttpClient()
        self._max_products_to_check = max_products_to_check

    @property
    def store_id(self) -> str:
        return "danireon"

    @property
    def display_name(self) -> str:
        return "Danireon"

    def search_card(self, requested_card: RequestedCard) -> list[StoreQuote]:
        search_html = self._http_client.get_text(
            f"{_DANIREON_BASE_URL}/search",
            params={
                "q": requested_card.normalized_name,
                "type": "product",
            },
        )

        product_urls = _extract_product_urls(search_html)

        quotes: list[StoreQuote] = []

        for product_url in product_urls[: self._max_products_to_check]:
            product_html = self._http_client.get_text(product_url)
            quotes.extend(
                parse_danireon_product_page(
                    html=product_html,
                    product_url=product_url,
                    requested_card=requested_card,
                )
            )

        return quotes


def parse_danireon_product_page(
    html: str,
    product_url: str,
    requested_card: RequestedCard,
) -> list[StoreQuote]:
    soup = BeautifulSoup(html, "html.parser")
    title = _extract_title(soup)

    if title is None:
        return []

    matched_card_name = _extract_card_name_from_title(title)

    if not _card_names_match(requested_card.normalized_name, matched_card_name):
        return []

    page_text = soup.get_text(" ", strip=True)
    finish = _extract_finish(title)
    set_code, collector_number = _extract_set_and_collector_number(title)

    quotes: list[StoreQuote] = []
    seen: set[tuple[CardCondition, Decimal | None, bool]] = set()

    for match in _CONDITION_PATTERN.finditer(page_text):
        condition_label = _normalize_condition_label(match.group("condition"))
        condition = _CONDITION_LABELS[condition_label]

        price_text = match.group("price")
        price = Decimal(price_text) if price_text is not None else None

        sold_out = bool(match.group("sold_out_without_price")) or bool(
            match.group("sold_out_with_price")
        )
        in_stock = not sold_out and price is not None

        dedupe_key = (condition, price, in_stock)
        if dedupe_key in seen:
            continue

        seen.add(dedupe_key)

        quotes.append(
            StoreQuote(
                store_id="danireon",
                requested_card_name=requested_card.normalized_name,
                matched_card_name=matched_card_name,
                condition=condition,
                finish=finish,
                price_cad=price,
                in_stock=in_stock,
                product_url=product_url,
                set_code=set_code,
                collector_number=collector_number,
                raw_title=title,
                confidence_score=1.0,
            )
        )

    return quotes


def _extract_product_urls(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    urls: list[str] = []

    for link in soup.find_all("a", href=True):
        href_value = link.get("href")

        if not isinstance(href_value, str):
            continue

        if not _looks_like_danireon_product_url(href_value):
            continue

        absolute_url = urljoin(_DANIREON_BASE_URL, href_value).split("?")[0]

        if absolute_url not in urls:
            urls.append(absolute_url)

    return urls


def _looks_like_danireon_product_url(href: str) -> bool:
    return "/products/" in href


def _extract_title(soup: BeautifulSoup) -> str | None:
    for selector in ["h1", "h2"]:
        heading = soup.find(selector)

        if heading is None:
            continue

        title = heading.get_text(" ", strip=True)

        if title:
            return title

    meta_title = soup.find("meta", property="og:title")

    if meta_title is not None:
        content = meta_title.get("content")

        if isinstance(content, str) and content.strip():
            return content.strip()

    return None


def _extract_card_name_from_title(title: str) -> str:
    before_set_info = title.split("(", maxsplit=1)[0]
    return before_set_info.strip()


def _card_names_match(requested_name: str, matched_name: str) -> bool:
    return _simple_normalize(requested_name) == _simple_normalize(matched_name)


def _simple_normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def _extract_finish(title: str) -> Finish:
    if " foil" in title.lower():
        return Finish.FOIL

    return Finish.NONFOIL


def _extract_set_and_collector_number(title: str) -> tuple[str | None, str | None]:
    matches = list(_SET_AND_COLLECTOR_PATTERN.finditer(title))

    if not matches:
        return None, None

    match = matches[-1]
    return match.group("set_code"), match.group("collector_number")


def _normalize_condition_label(label: str) -> str:
    normalized = _simple_normalize(label)

    for known_label in _CONDITION_LABELS:
        if _simple_normalize(known_label) == normalized:
            return known_label

    raise ValueError(f"Unknown Danireon condition label: {label}")
