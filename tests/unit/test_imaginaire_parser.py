from decimal import Decimal

from mtg_price_checker.domain.enums import CardCondition
from mtg_price_checker.domain.requested_card import RequestedCard
from mtg_price_checker.stores.imaginaire import (
    deck_items_api_to_ui,
    format_deck_items_for_api,
    format_deck_items_for_ui,
    parse_imaginaire_deck_builder_html,
)


def test_parse_imaginaire_filters_to_nm_in_stock_only() -> None:
    html = """
    <ul>
      <li class="card-listing">
        <div class="magic-card">
          <h3 class="magictitle">Sol Ring</h3>
        </div>
        <div class="price-listing">
          <a href="/fr/magic/some-set/sol-ring.html?magicsku=ABC123">Sol Ring</a>
          <span>Commander Legends</span>
          <table>
            <tr>
              <td>SP</td><td>4.04 $</td><td><span class="quantity">9</span></td>
            </tr>
            <tr>
              <td>NM</td><td>2.99 $</td><td><span class="quantity">3</span></td>
            </tr>
          </table>
        </div>
        <div class="price-listing">
          <span style="color:red">Rupture de stock</span>
          <table>
            <tr>
              <td>NM</td><td>1.99 $</td><td><span class="quantity">0</span></td>
            </tr>
          </table>
        </div>
      </li>
      <li class="card-listing">
        <div class="magic-card">
          <h3 class="magictitle">Arcane Signet</h3>
        </div>
        <div class="price-listing">
          <a href="/fr/magic/some-set/arcane-signet.html">Arcane Signet</a>
          <span>Commander Legends</span>
          <table>
            <tr>
              <td>NM</td><td>0.99 $</td><td><span class="quantity">11</span></td>
            </tr>
          </table>
        </div>
      </li>
    </ul>
    """

    requested = [
        RequestedCard(input_name="Sol Ring", normalized_name="sol ring"),
        RequestedCard(input_name="Arcane Signet", normalized_name="arcane signet"),
    ]
    parsed = parse_imaginaire_deck_builder_html(
        html=html,
        requested_cards=requested,
        max_products_to_check=10,
    )

    sol_ring_key = "sol ring"
    arcane_key = "arcane signet"

    sol_quotes = parsed.quotes_by_card_key[sol_ring_key]
    assert len(sol_quotes) == 1
    assert sol_quotes[0].matched_card_name == "Sol Ring"
    assert sol_quotes[0].price_cad == Decimal("2.99")
    assert sol_quotes[0].in_stock is True
    assert sol_quotes[0].quantity_available == 3
    assert sol_quotes[0].set_code == "ABC123"

    arcane_quotes = parsed.quotes_by_card_key[arcane_key]
    assert len(arcane_quotes) == 1
    assert arcane_quotes[0].price_cad == Decimal("0.99")
    assert arcane_quotes[0].in_stock is True


def test_parse_imaginaire_prefers_magicdecklist_summary_over_price_listings() -> None:
    html = """
    <ul>
      <li class="card-listing">
        <div class="magic-card">
          <h3 class="magictitle">Arcane Signet</h3>
          <div class="magicdecklist" position="22" id="list22">
            <div>
              <img src="/docs/neon-dynasty.jpg">
              <div class="listinfo">
                <span>1 x Neon Dynasty Commander (NM)</span>
                <span>0.99$</span>
              </div>
            </div>
          </div>
        </div>
        <div class="price-listing">
          <a href="/fr/magic/expensive-set/arcane-signet.html?magicsku=SLD1919">Arcane Signet</a>
          <span>Secret Lair Drop</span>
          <span style="color: #3333339c; display: block;">SLD1919</span>
          <table>
            <tr>
              <td>NM</td><td>72.99 $</td><td><span class="quantity">1</span></td>
            </tr>
          </table>
        </div>
      </li>
    </ul>
    """

    requested = [RequestedCard(input_name="Arcane Signet", normalized_name="arcane signet")]
    parsed = parse_imaginaire_deck_builder_html(
        html=html,
        requested_cards=requested,
        max_products_to_check=10,
    )

    quotes = parsed.quotes_by_card_key["arcane signet"]
    assert len(quotes) == 1
    assert quotes[0].price_cad == Decimal("0.99")
    assert quotes[0].set_name == "Neon Dynasty Commander"
    assert parsed.listings_checked_by_card_key["arcane signet"] == 1


def test_parse_imaginaire_magicdecklist_sol_ring_summary() -> None:
    html = """
    <ul>
      <li class="card-listing">
        <div class="magic-card">
          <h3 class="magictitle">Sol Ring</h3>
          <div class="magicdecklist" position="1" id="list1">
            <div>
              <img src="/docs/2024060949_19911e6e-7c35-4281-b31c-266382f052cc.jpg">
              <div class="listinfo">
                <span>1 x Modern Horizons 3 Commander (NM)</span>
                <span>2.49$</span>
              </div>
            </div>
          </div>
        </div>
        <div class="price-listing">
          <a href="/fr/magic/modern-horizons-3-commander/sol-ring.html?magicsku=M3C305">
            <img src="/docs/2024060949_19911e6e-7c35-4281-b31c-266382f052cc.jpg">
          </a>
          <span>Modern Horizons 3 Commander</span>
          <span style="color: #3333339c; display: block;">M3C305</span>
          <table>
            <tr><td>NM</td><td>2.49 $</td><td><span class="quantity">1</span></td></tr>
          </table>
        </div>
        <div class="price-listing">
          <a href="/fr/magic/secret-lair-drop/sol-ring.html?magicsku=SLD1988">Sol Ring</a>
          <span>Secret Lair Drop</span>
          <table>
            <tr><td>NM</td><td>19.99 $</td><td><span class="quantity">2</span></td></tr>
          </table>
        </div>
      </li>
    </ul>
    """

    requested = [RequestedCard(input_name="Sol Ring", normalized_name="sol ring")]
    parsed = parse_imaginaire_deck_builder_html(
        html=html,
        requested_cards=requested,
        max_products_to_check=10,
    )

    quotes = parsed.quotes_by_card_key["sol ring"]
    assert len(quotes) == 1
    assert quotes[0].price_cad == Decimal("2.49")
    assert quotes[0].set_code == "M3C305"
    assert quotes[0].set_name == "Modern Horizons 3 Commander"


def test_parse_imaginaire_sp_summary_used_when_min_condition_allows() -> None:
    html = """
    <ul>
      <li class="card-listing">
        <div class="magic-card">
          <h3 class="magictitle">Counterspell</h3>
          <div class="magicdecklist">
            <div>
              <img src="/docs/tempest.jpg">
              <div class="listinfo">
                <span>1 x Tempest (SP)</span>
                <span>4.49$</span>
              </div>
            </div>
          </div>
        </div>
        <div class="price-listing">
          <a href="/fr/magic/tempest/counterspell.html?magicsku=TMP57">
            <img src="/docs/tempest.jpg">
          </a>
          <span>Tempest</span>
          <table>
            <tr>
              <td><span>SP</span><span>TMP57SP</span></td>
              <td>4.49 $</td>
              <td><input price="4.49"><span class="quantity">1</span></td>
            </tr>
          </table>
        </div>
        <div class="price-listing">
          <a href="/fr/magic/ff/counterspell-foil.html?magicsku=FCA4F">Foil</a>
          <span>Final Fantasy: Through the Ages</span>
          <table>
            <tr>
              <td><span>NM</span><span>FCA4FNM</span></td>
              <td>8.99 $</td>
              <td><input price="8.99"><span class="quantity">1</span></td>
            </tr>
          </table>
        </div>
      </li>
    </ul>
    """
    requested = [
        RequestedCard(
            input_name="Counterspell",
            normalized_name="counterspell",
            min_condition=CardCondition.LIGHTLY_PLAYED,
        )
    ]
    parsed = parse_imaginaire_deck_builder_html(
        html=html,
        requested_cards=requested,
        max_products_to_check=10,
    )
    quotes = parsed.quotes_by_card_key["counterspell"]
    assert len(quotes) == 1
    assert quotes[0].price_cad == Decimal("4.49")
    assert quotes[0].condition == CardCondition.LIGHTLY_PLAYED


def test_parse_imaginaire_non_nm_summary_falls_back_to_price_listings() -> None:
    html = """
    <ul>
      <li class="card-listing">
        <div class="magic-card">
          <h3 class="magictitle">Counterspell</h3>
          <div class="magicdecklist" position="48" id="list48">
            <div>
              <img src="/docs/0c9a7cb0-5bff-48ff-b620-2838816ac9b5.jpg">
              <div class="listinfo">
                <span>1 x Eternal Masters (SP)</span>
                <span>4.04$</span>
              </div>
            </div>
          </div>
        </div>
        <div class="price-listing">
          <a href="/fr/magic/fourth-edition/counterspell.html?magicsku=4ED65">Counterspell</a>
          <span>Fourth Edition</span>
          <table>
            <tr><td>SP</td><td>4.04 $</td><td><span class="quantity">2</span></td></tr>
          </table>
        </div>
        <div class="price-listing">
          <a href="/fr/magic/modern-horizons-2/counterspell.html?magicsku=MH2267">Counterspell</a>
          <span>Modern Horizons 2</span>
          <table>
            <tr><td>NM</td><td>4.49 $</td><td><span class="quantity">1</span></td></tr>
          </table>
        </div>
        <div class="price-listing">
          <a href="/fr/magic/masters-25/counterspell.html?magicsku=A2550">Counterspell</a>
          <span>Masters 25</span>
          <table>
            <tr><td>NM</td><td>5.99 $</td><td><span class="quantity">2</span></td></tr>
          </table>
        </div>
      </li>
    </ul>
    """

    requested = [RequestedCard(input_name="Counterspell", normalized_name="counterspell")]
    parsed = parse_imaginaire_deck_builder_html(
        html=html,
        requested_cards=requested,
        max_products_to_check=10,
    )

    quotes = parsed.quotes_by_card_key["counterspell"]
    assert len(quotes) == 2
    assert min(quote.price_cad for quote in quotes) == Decimal("4.49")
    assert parsed.listings_checked_by_card_key["counterspell"] == 3


def test_parse_imaginaire_price_ignores_sku_digits_like_plgm1() -> None:
    """Regression: PLGM1NM used to yield $1.00 via first-digit price scrape."""
    html = """
    <ul>
      <li class="card-listing">
        <div class="magic-card">
          <h3 class="magictitle">Counterspell</h3>
          <div class="magicdecklist" position="1" id="list1">
            <div>
              <img src="/docs/tempest.jpg">
              <div class="listinfo">
                <span>1 x Tempest (SP)</span>
                <span>4.49$</span>
              </div>
            </div>
          </div>
        </div>
        <div class="price-listing">
          <a href="/fr/magic/tempest/counterspell.html?magicsku=TMP57">
            <img src="/docs/tempest.jpg">
          </a>
          <span style="display: block;">Tempest</span>
          <span style="color: #3333339c; display: block;">common</span>
          <span style="color: #3333339c; display: block;">TMP57</span>
          <table>
            <tr>
              <td style="background-color: lightgreen;">
                <span style="color: black; font-size: 16px;">SP</span>
                <span style="color: #3333339c; font-size: 12px;">TMP57SP</span>
              </td>
              <td>4.49 $ </td>
              <td>
                <input type="number" price="4.491" value="1" min="1">
                <span class="quantity">1 </span>
              </td>
            </tr>
          </table>
        </div>
        <div class="price-listing">
          <a href="/fr/magic/final-fantasy-through-the-ages/counterspell-foil.html?magicsku=FCA4F">
            <img class="foilcard" src="/docs/ff.jpg">
          </a>
          <span style="display: block;">Final Fantasy: Through the Ages</span>
          <span style="color: #3333339c; display: block;">uncommon</span>
          <span style="color: #3333339c; display: block;">FCA4F</span>
          <table>
            <tr>
              <td style="background-color: lightgreen;">
                <span style="color: black; font-size: 16px;">NM</span>
                <span style="color: #3333339c; font-size: 12px;">FCA4FNM</span>
              </td>
              <td>8.99 $ </td>
              <td>
                <input type="number" price="8.99" value="0" min="1">
                <span class="quantity">1 </span>
              </td>
            </tr>
          </table>
        </div>
        <div class="price-listing">
          <a href="/fr/magic/dci-legend-membership/counterspell.html?magicsku=PLGM1">
            <img src="/docs/plgm.jpg">
          </a>
          <span style="display: block;">DCI Legend Membership</span>
          <span style="color: #3333339c; display: block;">rare</span>
          <span style="color: #3333339c; display: block;">PLGM1</span>
          <table>
            <tr>
              <td style="background-color: lightgreen;">
                <span style="color: black; font-size: 16px;">NM</span>
                <span style="color: #3333339c; font-size: 12px;">PLGM1NM</span>
              </td>
              <td>69.99 $ </td>
              <td>
                <input type="number" price="69.99" value="0" min="1">
                <span class="quantity">2 </span>
              </td>
            </tr>
          </table>
        </div>
      </li>
    </ul>
    """

    requested = [RequestedCard(input_name="Counterspell", normalized_name="counterspell")]
    parsed = parse_imaginaire_deck_builder_html(
        html=html,
        requested_cards=requested,
        max_products_to_check=10,
    )

    quotes = parsed.quotes_by_card_key["counterspell"]
    assert len(quotes) == 2
    prices = {quote.price_cad for quote in quotes}
    assert Decimal("1.00") not in prices
    assert Decimal("1") not in prices
    assert prices == {Decimal("8.99"), Decimal("69.99")}
    assert min(prices) == Decimal("8.99")
    cheapest = min(quotes, key=lambda q: q.price_cad)
    assert cheapest.set_code == "FCA4F"
    assert cheapest.quantity_available == 1


def test_parse_imaginaire_falls_back_to_price_listings_without_magicdecklist() -> None:
    html = """
    <ul>
      <li class="card-listing">
        <div class="magic-card">
          <h3 class="magictitle">Sol Ring</h3>
        </div>
        <div class="price-listing">
          <a href="/fr/magic/set-a/sol-ring.html">Sol Ring</a>
          <span>Set A</span>
          <table>
            <tr><td>NM</td><td>4.50 $</td><td><span class="quantity">1</span></td></tr>
          </table>
        </div>
        <div class="price-listing">
          <a href="/fr/magic/set-b/sol-ring.html">Sol Ring</a>
          <span>Set B</span>
          <table>
            <tr><td>NM</td><td>2.99 $</td><td><span class="quantity">3</span></td></tr>
          </table>
        </div>
      </li>
    </ul>
    """

    requested = [RequestedCard(input_name="Sol Ring", normalized_name="sol ring")]
    parsed = parse_imaginaire_deck_builder_html(
        html=html,
        requested_cards=requested,
        max_products_to_check=10,
    )

    quotes = parsed.quotes_by_card_key["sol ring"]
    assert len(quotes) == 2
    assert min(quote.price_cad for quote in quotes) == Decimal("2.99")


def test_count_ready_magicdecklist_summaries() -> None:
    from mtg_price_checker.stores.imaginaire import count_ready_magicdecklist_summaries

    html = """
    <ul>
      <li class="card-listing">
        <div class="magicdecklist">
          <div class="listinfo">
            <span>1 x Neon Dynasty Commander (NM)</span>
            <span>0.99$</span>
          </div>
        </div>
      </li>
      <li class="card-listing">
        <div class="magicdecklist">
          <div class="listinfo">
            <span>1 x Eternal Masters (SP)</span>
            <span>4.04$</span>
          </div>
        </div>
      </li>
      <li class="card-listing">
        <div class="magicdecklist"></div>
      </li>
    </ul>
    """
    total, ready = count_ready_magicdecklist_summaries(html)
    assert total == 3
    assert ready == 2


def test_format_deck_items_for_api() -> None:
    assert format_deck_items_for_api(["Sol Ring", "Arcane Signet"]) == (
        "$sol ring | $arcane signet"
    )


def test_format_deck_items_for_ui() -> None:
    assert format_deck_items_for_ui(["Sol Ring", "Arcane Signet"]) == ("sol ring\narcane signet")


def test_deck_items_api_to_ui() -> None:
    assert deck_items_api_to_ui("$sol ring | $arcane signet | $counterspell") == (
        "sol ring\narcane signet\ncounterspell"
    )
