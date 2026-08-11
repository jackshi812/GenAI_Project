"""Deterministic unit checks that run with no API key, no contracts.py, and
no fixtures — pure logic only (matching, variant guards, conflict math,
currency-keyword escalation, fixture keys).

Run:  python -m graph.test_deterministic
"""

from graph.matching import (
    clean_filters,
    currency_keyword_hit,
    eight_word_key,
    match_band,
    price_conflict,
    title_similarity,
    variant_guard,
)

FAILS: list[str] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    print(("PASS " if cond else "FAIL ") + name + (f"  {extra}" if extra else ""))
    if not cond:
        FAILS.append(name)


def main() -> None:
    # GRAPH-03: deterministic currency escalation, word-boundary safe.
    check("q1 no escalation", not currency_keyword_hit(
        "Find me a 500 piece jigsaw puzzle under twenty dollars."))
    check("q2 escalates", currency_keyword_hit(
        "What is the current price and availability of the LEGO Classic Creative Suitcase 10713?"))
    check("'know'/'snow'/'nowhere' never fire", not any(
        currency_keyword_hit(t) for t in (
            "I know what I want, a chess set.",
            "A snowman plush toy please.",
            "There is nowhere to buy this locally.")))
    check("bare 'now' fires", currency_keyword_hit("Is it cheaper now?"))
    check("'in stock' fires", currency_keyword_hit("Is the red one in stock?"))

    # D-01 stage B: variant guards.
    check("pack conflict", variant_guard("Nerf blaster 2-pack", "Nerf blaster 4 pack") == "conflict")
    check("count conflict", variant_guard(
        "500 piece jigsaw puzzle", "1000 piece jigsaw puzzle") == "conflict")
    check("model conflict", variant_guard(
        "LEGO Classic Creative Suitcase 10713 Building Kit (213 Pieces)",
        "LEGO Classic World Fun 10403 Building Kit (295 Piece)") == "conflict")
    check("color conflict", variant_guard(
        "Huffy 12 inch bike pink", "Huffy 12 inch bike blue") == "conflict")
    check("one-sided goes to confirm", variant_guard(
        "Nerf Strongarm blaster with 6 darts", "Nerf Strongarm blaster") == "one_sided")

    # D-01 bands: canonical conflict pair must never be auto-rejected.
    cat = ("Nerf N Strike Elite Strongarm Toy Blaster with Rotating Barrel, Slam Fire, "
           "and 6 Official Nerf Elite Darts for Kids, Teens, & Adults(Amazon Exclusive)")
    live = "Nerf N-Strike Elite Strongarm Blaster"
    band = match_band(title_similarity(cat, live), variant_guard(cat, live))
    check("strongarm raw pair not auto-rejected", band in ("accept", "confirm"), f"band={band}")

    # D-02: price conflict thresholds (max of 10% of private value, $2).
    check("13.99 vs 24.99 conflict, up",
          (price_conflict(13.99, 24.99) or {}).get("direction") == "up")
    check("10.99 vs 11.50 within threshold", price_conflict(10.99, 11.50) is None)
    check("100 vs 109 within 10%", price_conflict(100.0, 109.0) is None)
    check("100 vs 111 conflict", price_conflict(100.0, 111.0) is not None)
    check("1.00 vs 2.50 within $2", price_conflict(1.00, 2.50) is None)

    # D-08: shared fixture key rule.
    check("eight-word key", eight_word_key(
        "  Nerf  N Strike Elite Strongarm Toy Blaster with Rotating Barrel ")
        == "nerf n strike elite strongarm toy blaster with")
    check("filters cleaned", clean_filters(
        {"price_max": 20.0, "bogus": 1, "brand": None, "k": 5}) == {"price_max": 20.0, "k": 5})

    print()
    print("FAILURES:", FAILS if FAILS else "none")
    raise SystemExit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
