from __future__ import annotations

import re
from decimal import Decimal
from typing import Iterable
from urllib.parse import parse_qs, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from mtg_price_checker.domain.enums import CardCondition, Finish
from mtg_price_checker.domain.requested_card import RequestedCard
from mtg_price_checker.domain.store_quote import StoreQuote
from mtg_price_checker.infra.http_client import HttpClient
from mtg_price_checker.stores.base import BatchStoreAdapter, StoreAdapter

_BASE_URL = "https://imaginaire.com"
_DECK_BUILDER_AJAX_URL = f"{_BASE_URL}/ajax/getDeckBuilder.asp"
_DEFAULT_REFERER = f"{_BASE_URL}/fr/magic/constructeur-de-deck.html"

_PRICE_PATTERN = re.compile(r"(?P<price>\d+(?:\.\d{1,2})?)")
_LISTINFO_LINE_PATTERN = re.compile(
    r"^(?P<qty>\d+)\s*x\s+(?P<set>.+?)\s*\((?P<condition>[^)]+)\)$",
    re.IGNORECASE,
)
_RARITY_LABELS = frozenset({"uncommon", "common", "rare", "mythic"})
_ROW_CONDITIONS = frozenset({"NM", "SP", "MP", "HP", "DM"})


class ImaginaireStoreAdapter(StoreAdapter, BatchStoreAdapter):
    def __init__(
        self,
        http_client: HttpClient | None = None,
        max_products_to_check: int = 10,
    ) -> None:
        self._http_client = http_client or HttpClient()
        self._max_products_to_check = max_products_to_check

        self._quotes_by_card_name: dict[str, list[StoreQuote]] = {}
        self._listings_checked_by_card_name: dict[str, int] = {}
        self._preloaded_card_names: set[str] = set()
        self._last_listings_checked = 0

    @property
    def store_id(self) -> str:
        return "imaginaire"

    @property
    def display_name(self) -> str:
        return "Imaginaire"

    @property
    def last_listings_checked(self) -> int:
        return self._last_listings_checked

    def preload_cards(self, requested_cards: list[RequestedCard]) -> None:
        unique_cards_by_key = {
            _card_cache_key(requested_card): requested_card for requested_card in requested_cards
        }

        if not unique_cards_by_key:
            return

        form = {
            "deckItems": _format_deck_items(
                [c.normalized_name for c in unique_cards_by_key.values()]
            ),
            "foil": "",
            "condition": "NM",
            "sitelist": "",
        }

        html = self._http_client.post_form(_DECK_BUILDER_AJAX_URL, form, referer=_DEFAULT_REFERER)

        parsed = parse_imaginaire_deck_builder_html(
            html=html,
            requested_cards=list(unique_cards_by_key.values()),
            max_products_to_check=self._max_products_to_check,
        )

        for normalized_key in unique_cards_by_key:
            self._quotes_by_card_name[normalized_key] = parsed.quotes_by_card_key.get(
                normalized_key, []
            )
            self._listings_checked_by_card_name[normalized_key] = (
                parsed.listings_checked_by_card_key.get(normalized_key, 0)
            )
            self._preloaded_card_names.add(normalized_key)

    def search_card(self, requested_card: RequestedCard) -> list[StoreQuote]:
        normalized_key = _card_cache_key(requested_card)

        if normalized_key not in self._preloaded_card_names:
            try:
                self.preload_cards([requested_card])
            except requests.HTTPError as exc:
                if exc.response is not None and exc.response.status_code == 429:
                    raise
            except Exception:
                pass

        self._last_listings_checked = self._listings_checked_by_card_name.get(normalized_key, 0)
        return self._quotes_by_card_name.get(normalized_key, [])


class ParsedImaginaireDeckBuilder:
    def __init__(
        self,
        *,
        quotes_by_card_key: dict[str, list[StoreQuote]],
        listings_checked_by_card_key: dict[str, int],
    ) -> None:
        self.quotes_by_card_key = quotes_by_card_key
        self.listings_checked_by_card_key = listings_checked_by_card_key


def parse_imaginaire_deck_builder_html(
    *,
    html: str,
    requested_cards: list[RequestedCard],
    max_products_to_check: int,
) -> ParsedImaginaireDeckBuilder:
    requested_by_key = {_card_cache_key(card): card for card in requested_cards}
    quotes_by_key: dict[str, list[StoreQuote]] = {key: [] for key in requested_by_key}
    listings_checked_by_key: dict[str, int] = {key: 0 for key in requested_by_key}

    soup = BeautifulSoup(html, "html.parser")

    for card_listing in soup.select("li.card-listing"):
        card_name = _extract_card_listing_name(card_listing)
        if card_name is None:
            continue

        matched_key = next(
            (
                key
                for key, req in requested_by_key.items()
                if _card_names_match(req.normalized_name, card_name)
            ),
            None,
        )
        if matched_key is None:
            continue

        requested_card = requested_by_key[matched_key]

        summary_block = card_listing.select_one("div.magicdecklist")
        if summary_block is not None:
            summary_quote = _parse_magicdecklist_summary(
                summary_block,
                card_listing=card_listing,
                requested_card=requested_card,
                matched_card_name=card_name,
            )
            if summary_quote is not None:
                quotes_by_key[matched_key] = [summary_quote]
                listings_checked_by_key[matched_key] = 1
                continue

        product_blocks = list(card_listing.select("div.price-listing"))
        listings_checked_by_key[matched_key] = min(len(product_blocks), max_products_to_check)

        for product_block in product_blocks[:max_products_to_check]:
            quote = _parse_product_block(
                product_block, requested_card=requested_card, matched_card_name=card_name
            )
            if quote is not None:
                quotes_by_key[matched_key].append(quote)

    return ParsedImaginaireDeckBuilder(
        quotes_by_card_key=quotes_by_key,
        listings_checked_by_card_key=listings_checked_by_key,
    )


def count_ready_magicdecklist_summaries(html: str) -> tuple[int, int]:
    soup = BeautifulSoup(html, "html.parser")
    listings = soup.select("li.card-listing")
    ready = sum(1 for listing in listings if _magicdecklist_summary_ready(listing))
    return len(listings), ready


def magicdecklist_has_nm_in_stock(card_listing) -> bool:
    summary_block = card_listing.select_one("div.magicdecklist")
    if summary_block is None:
        return False
    parsed = _parse_listinfo(summary_block)
    if parsed is None:
        return False
    quantity, _set_name, condition, price = parsed
    return condition.upper() == CardCondition.NEAR_MINT.value and quantity > 0 and price is not None


def _format_deck_items(card_names: Iterable[str]) -> str:
    return format_deck_items_for_api(card_names)


def format_deck_items_for_api(card_names: Iterable[str]) -> str:
    parts = []
    for name in card_names:
        cleaned = name.strip()
        if not cleaned:
            continue
        parts.append(f"${cleaned.lower()}")
    return " | ".join(parts)


def format_deck_items_for_ui(card_names: Iterable[str]) -> str:
    lines = []
    for name in card_names:
        cleaned = name.strip().lower()
        if cleaned:
            lines.append(cleaned)
    return "\n".join(lines)


def deck_items_api_to_ui(deck_items_api: str) -> str:
    names: list[str] = []
    for part in deck_items_api.split("|"):
        cleaned = part.strip().lstrip("$").strip().lower()
        if cleaned:
            names.append(cleaned)
    return "\n".join(names)


def _magicdecklist_summary_ready(card_listing) -> bool:
    summary_block = card_listing.select_one("div.magicdecklist")
    if summary_block is None:
        return False
    return _parse_listinfo(summary_block) is not None


def _parse_listinfo(summary_block) -> tuple[int, str, str, Decimal] | None:
    listinfo = summary_block.select_one("div.listinfo")
    if listinfo is None:
        return None

    spans = listinfo.select("span")
    if len(spans) < 2:
        return None

    line_text = spans[0].get_text(" ", strip=True)
    price_text = spans[1].get_text(" ", strip=True)
    if not line_text or not price_text:
        return None

    match = _LISTINFO_LINE_PATTERN.match(line_text)
    if match is None:
        return None

    try:
        quantity = int(match.group("qty"))
    except ValueError:
        return None

    set_name = match.group("set").strip()
    condition = match.group("condition").strip()
    price = _extract_price(price_text)
    if quantity <= 0 or price is None:
        return None

    return quantity, set_name, condition, price


def _parse_magicdecklist_summary(
    summary_block,
    *,
    card_listing,
    requested_card: RequestedCard,
    matched_card_name: str,
) -> StoreQuote | None:
    parsed = _parse_listinfo(summary_block)
    if parsed is None:
        return None

    quantity, set_name, condition, price = parsed
    if condition.upper() != CardCondition.NEAR_MINT.value:
        return None

    summary_img = summary_block.select_one("img[src]")
    summary_img_src = summary_img.get("src") if summary_img else None

    product_url, set_code, finish = _resolve_product_from_price_listings(
        card_listing,
        set_name=set_name,
        summary_img_src=summary_img_src,
    )

    return StoreQuote(
        store_id="imaginaire",
        requested_card_name=requested_card.normalized_name,
        matched_card_name=matched_card_name,
        condition=CardCondition.NEAR_MINT,
        finish=finish,
        price_cad=price,
        in_stock=True,
        product_url=product_url,
        quantity_available=quantity,
        set_name=set_name,
        set_code=set_code,
        raw_title=matched_card_name,
        confidence_score=1.0,
    )


def _resolve_product_from_price_listings(
    card_listing,
    *,
    set_name: str,
    summary_img_src: str | None,
) -> tuple[str | None, str | None, Finish]:
    summary_img_key = _image_src_key(summary_img_src)
    normalized_set = _simple_normalize(set_name)

    for product_block in card_listing.select("div.price-listing"):
        block_set = _extract_price_listing_set_name(product_block)
        if block_set is None:
            continue
        if _simple_normalize(block_set) != normalized_set:
            if summary_img_key is None or not _price_listing_matches_image(
                product_block, summary_img_key
            ):
                continue

        product_url = _extract_product_url(product_block)
        set_code = _extract_set_code(product_url) or _extract_sku_from_listing(product_block)
        finish = Finish.FOIL if product_block.select_one("img.foilcard") else Finish.NONFOIL
        return product_url, set_code, finish

    if summary_img_key is not None:
        for product_block in card_listing.select("div.price-listing"):
            if not _price_listing_matches_image(product_block, summary_img_key):
                continue
            product_url = _extract_product_url(product_block)
            set_code = _extract_set_code(product_url) or _extract_sku_from_listing(product_block)
            finish = Finish.FOIL if product_block.select_one("img.foilcard") else Finish.NONFOIL
            return product_url, set_code, finish

    return None, None, Finish.NONFOIL


def _extract_price_listing_set_name(product_block) -> str | None:
    for span in product_block.select("span"):
        text = span.get_text(" ", strip=True)
        if not text:
            continue
        if text.lower() in _RARITY_LABELS:
            continue
        if text.lower().startswith("rupture de stock"):
            continue
        return text
    return None


def _extract_sku_from_listing(product_block) -> str | None:
    for span in product_block.select("span"):
        style = span.get("style", "")
        if "3333339c" in style.replace(" ", ""):
            value = span.get_text(" ", strip=True)
            if value:
                return value
    return None


def _image_src_key(src: str | None) -> str | None:
    if not src:
        return None
    basename = src.rsplit("/", 1)[-1]
    if "?" in basename:
        basename = basename.split("?", 1)[0]
    return basename.lower() or None


def _price_listing_matches_image(product_block, summary_img_key: str) -> bool:
    img = product_block.select_one("img[src]")
    if img is None:
        return False
    listing_key = _image_src_key(img.get("src"))
    if listing_key is None:
        return False
    return (
        listing_key == summary_img_key
        or summary_img_key in listing_key
        or listing_key in summary_img_key
    )


def _parse_product_block(
    product_block,
    *,
    requested_card: RequestedCard,
    matched_card_name: str,
) -> StoreQuote | None:
    if not _block_has_nm_in_stock(product_block):
        return None

    product_url = _extract_product_url(product_block)
    set_name = _extract_set_name(product_block)
    set_code = _extract_set_code(product_url)
    finish = Finish.FOIL if product_block.select_one("img.foilcard") else Finish.NONFOIL

    nm_row = _find_nm_row(product_block)
    if nm_row is None:
        return None

    quantity = _extract_quantity(nm_row)
    price = _extract_row_price(nm_row)

    if quantity <= 0 or price is None:
        return None

    return StoreQuote(
        store_id="imaginaire",
        requested_card_name=requested_card.normalized_name,
        matched_card_name=matched_card_name,
        condition=CardCondition.NEAR_MINT,
        finish=finish,
        price_cad=price,
        in_stock=True,
        product_url=product_url,
        quantity_available=quantity,
        set_name=set_name,
        set_code=set_code,
        raw_title=matched_card_name,
        confidence_score=1.0,
    )


def _block_has_nm_in_stock(product_block) -> bool:
    text = product_block.get_text(" ", strip=True).lower()
    if "rupture de stock" in text:
        return False

    nm_row = _find_nm_row(product_block)
    if nm_row is None:
        return False

    quantity = _extract_quantity(nm_row)
    price = _extract_row_price(nm_row)
    return quantity > 0 and price is not None


def _extract_card_listing_name(card_listing) -> str | None:
    header = card_listing.select_one(":scope > div.magic-card h3.magictitle")
    if header is None:
        header = card_listing.select_one("h3.magictitle")
    if header is None:
        return None
    value = header.get_text(" ", strip=True)
    return value or None


def _find_nm_row(product_block):
    text = product_block.get_text(" ", strip=True).lower()
    if "rupture de stock" in text:
        return None

    for tr in product_block.select("tr"):
        if _extract_row_condition(tr) == CardCondition.NEAR_MINT.value:
            return tr

    return None


def _extract_row_condition(tr) -> str | None:
    first_td = tr.select_one("td")
    if first_td is None:
        return None

    for span in first_td.select("span"):
        text = span.get_text(" ", strip=True).upper()
        if text in _ROW_CONDITIONS:
            return text

    cell_text = first_td.get_text(" ", strip=True).upper()
    if cell_text in _ROW_CONDITIONS:
        return cell_text

    token = cell_text.split(None, 1)[0] if cell_text else ""
    if token in _ROW_CONDITIONS:
        return token

    return None


def _extract_quantity(tr) -> int:
    qty = tr.select_one("span.quantity")
    if qty is None:
        return 0
    value = qty.get_text(" ", strip=True)
    try:
        return int(value)
    except ValueError:
        return 0


def _extract_row_price(tr) -> Decimal | None:
    # Prefer the dedicated price attribute on the qty input (avoids SKU digits like PLGM1NM).
    price_input = tr.select_one("input[price]")
    if price_input is not None:
        attr_price = price_input.get("price")
        if attr_price:
            parsed = _extract_price(str(attr_price))
            if parsed is not None:
                return parsed

    # Fall back to the Prix column (second <td>).
    cells = tr.select("td")
    if len(cells) >= 2:
        parsed = _extract_price(cells[1].get_text(" ", strip=True))
        if parsed is not None:
            return parsed

    return None


def _extract_price(text: str) -> Decimal | None:
    # Typical: "2.99 $"
    match = _PRICE_PATTERN.search(text)
    if match is None:
        return None
    try:
        return Decimal(match.group("price"))
    except Exception:
        return None


def _extract_product_url(product_block) -> str | None:
    a = product_block.select_one("a[href]")
    if a is None:
        return None
    href = a.get("href")
    if not href:
        return None
    return urljoin(_BASE_URL, href)


def _extract_set_name(product_block) -> str | None:
    return _extract_price_listing_set_name(product_block)


def _extract_set_code(product_url: str | None) -> str | None:
    if not product_url:
        return None
    query = parse_qs(urlparse(product_url).query)
    values = query.get("magicsku")
    if not values:
        return None
    return values[0]


def _card_cache_key(requested_card: RequestedCard) -> str:
    return _simple_normalize(requested_card.normalized_name)


def _card_names_match(requested_name: str, matched_name: str) -> bool:
    return _simple_normalize(requested_name) == _simple_normalize(matched_name)


def _simple_normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())
