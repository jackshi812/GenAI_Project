"""Regression tests for the unified shopping-result cards."""

from __future__ import annotations

import unittest

from app.product_grid import (
    comparison_rows,
    prepare_product_cards,
    product_card_html,
    product_display,
    shopping_grid_html,
)
from contracts import (
    ComparisonProduct,
    Conflict,
    MatchInfo,
    RagResult,
    StepEvent,
    TopRecommendation,
    WebResult,
)


def _private_product() -> RagResult:
    return RagResult(
        sku="catalog-sku",
        title="Nerf N Strike Elite Strongarm Blaster",
        price=13.99,
        rating=None,
        brand="Nerf",
        ingredients=None,
        doc_id="AMZ-TEST",
        image_url="https://example.com/catalog.jpg",
        product_url="https://example.com/catalog-product",
        category="Toys & Games",
        price_low=13.99,
        price_high=13.99,
        similarity=0.91,
        budget_fit="unknown",
    )


def _live_product() -> WebResult:
    return WebResult(
        title="Nerf Strongarm Elite Toy Blaster",
        url="https://example.com/live-product",
        snippet="In stock from a current retailer.",
        price=21.95,
        availability="In stock",
        image_url="https://example.com/live.jpg",
        rating=4.8,
        origin="live_serper",
    )


def _ranked_products(count: int) -> list[ComparisonProduct]:
    return [
        ComparisonProduct(
            private=_private_product().model_copy(
                update={
                    "sku": f"ranked-{index:02d}",
                    "doc_id": f"AMZ-RANKED-{index:02d}",
                    "title": f"Ranked Product {index:02d}",
                }
            ),
            live=None,
            conflicts=[],
            match=None,
        )
        for index in range(count)
    ]


class ProductGridTests(unittest.TestCase):
    def test_display_metadata_matches_the_grounded_card_field_selection(self) -> None:
        product = ComparisonProduct(
            private=_private_product(),
            live=_live_product(),
            conflicts=[],
            match=None,
        )

        display = product_display(product)
        rendered = product_card_html(product)

        self.assertEqual(display.title, _live_product().title)
        self.assertEqual(display.primary_price, 21.95)
        self.assertEqual(display.formatted_price, "$21.95")
        self.assertEqual(display.price_label, "Current web price")
        self.assertEqual(display.source_labels, ("Catalog", "Web search"))
        self.assertEqual(display.link, "https://example.com/live-product")
        self.assertIn(display.title, rendered)
        self.assertIn('shopping-card__whole">21</span>', rendered)
        self.assertIn(display.price_label, rendered)

    def test_web_price_provenance_is_shared_by_cards_and_comparisons(self) -> None:
        expected_labels = {
            "live_serper": "Current web price",
            "recorded_fixture": "Recorded web price",
            "unknown": "Web price",
        }

        for origin, expected_label in expected_labels.items():
            with self.subTest(origin=origin):
                product = ComparisonProduct(
                    private=_private_product(),
                    live=_live_product().model_copy(update={"origin": origin}),
                    conflicts=[],
                    match=None,
                )

                display = product_display(product)
                rendered = product_card_html(product)
                row = comparison_rows([product])[0]

                self.assertEqual(display.price_label, expected_label)
                self.assertIn(expected_label, rendered)
                self.assertEqual(row["Price source"], expected_label)

    def test_display_metadata_preserves_raw_and_missing_prices_and_safe_links(self) -> None:
        raw_private = _private_product().model_copy(
            update={
                "price": "$12 - $18",
                "price_low": None,
                "price_high": None,
                "product_url": "javascript:alert(1)",
            }
        )
        raw_product = ComparisonProduct(
            private=raw_private,
            live=None,
            conflicts=[],
            match=None,
        )
        missing_product = ComparisonProduct(
            private=None,
            live=_live_product().model_copy(
                update={"price": None, "url": "data:text/html,bad"}
            ),
            conflicts=[],
            match=None,
        )

        raw_display = product_display(raw_product)
        missing_display = product_display(missing_product)

        self.assertEqual(raw_display.primary_price, "$12 - $18")
        self.assertEqual(raw_display.formatted_price, "$12 - $18")
        self.assertEqual(raw_display.price_label, "2020 catalog price")
        self.assertIsNone(raw_display.link)
        self.assertIsNone(missing_display.primary_price)
        self.assertEqual(missing_display.formatted_price, "—")
        self.assertEqual(missing_display.price_label, "Price")
        self.assertEqual(missing_display.source_labels, ("Web search",))
        self.assertIsNone(missing_display.link)

    def test_prepared_cards_cap_order_steps_and_canonical_top_treatment(self) -> None:
        products = _ranked_products(8)
        steps = [
            StepEvent(
                node="retriever",
                tool="web.search",
                started_at=f"2026-08-19T00:00:0{index}Z",
                duration_ms=index,
                status="completed",
                detail=f"Web step {index}",
            )
            for index in range(8)
        ]
        top = TopRecommendation(
            product_key="catalog:AMZ-RANKED-00",
            title="Ranked Product 00",
            reason="Graph-owned canonical recommendation.",
        )

        prepared = prepare_product_cards(products, steps, top)

        self.assertEqual(len(prepared), 6)
        self.assertEqual([item.index for item in prepared], list(range(6)))
        self.assertEqual(
            [item.display.title for item in prepared],
            [f"Ranked Product {index:02d}" for index in range(6)],
        )
        self.assertEqual(
            [item.web_step for item in prepared],
            steps[:6],
        )
        self.assertIs(prepared[0].top_recommendation, top)
        self.assertTrue(
            all(item.top_recommendation is None for item in prepared[1:])
        )

    def test_matched_product_is_one_card_with_both_source_badges(self) -> None:
        product = ComparisonProduct(
            private=_private_product(),
            live=_live_product(),
            conflicts=[
                Conflict(
                    field="price",
                    private_value=13.99,
                    live_value=21.95,
                    note="price rose",
                )
            ],
            match=MatchInfo(
                similarity=0.93,
                verdict="same",
                reason="Titles and model details match.",
            ),
        )

        rendered = product_card_html(product)

        self.assertEqual(rendered.count('<article class="shopping-card">'), 1)
        self.assertIn(">Catalog</span>", rendered)
        self.assertIn(">Web search</span>", rendered)
        self.assertIn(">Price changed</span>", rendered)
        self.assertIn('shopping-card__whole">21</span>', rendered)
        self.assertIn("2020 catalog: $13.99", rendered)
        self.assertIn("4.8 out of 5 stars", rendered)

    def test_card_escapes_content_and_rejects_unsafe_urls(self) -> None:
        live = _live_product().model_copy(
            update={
                "title": "Unsafe <script>alert(1)</script>",
                "url": "javascript:alert(1)",
                "image_url": "javascript:alert(2)",
                "snippet": "<b>untrusted</b>",
                "rating": None,
            }
        )
        product = ComparisonProduct(
            private=None,
            live=live,
            conflicts=[],
            match=None,
        )

        rendered = product_card_html(product)

        self.assertNotIn("javascript:", rendered)
        self.assertNotIn("<script>", rendered)
        self.assertIn("&lt;script&gt;", rendered)
        self.assertIn("&lt;b&gt;untrusted&lt;/b&gt;", rendered)
        self.assertIn("No rating reported", rendered)
        self.assertNotIn("★★★★★", rendered)

    def test_grid_and_comparison_cap_at_first_six_in_ranked_order(self) -> None:
        products = _ranked_products(10)

        rendered = shopping_grid_html(products)
        rows = comparison_rows(products)

        self.assertEqual(rendered.count('<article class="shopping-card">'), 6)
        self.assertEqual(len(rows), 6)
        self.assertEqual(
            [row["Product"] for row in rows],
            [f"Ranked Product {index:02d}" for index in range(6)],
        )
        self.assertNotIn("Ranked Product 06", rendered)
        positions = [
            rendered.index(f"Ranked Product {index:02d}")
            for index in range(6)
        ]
        self.assertEqual(positions, sorted(positions))

    def test_grid_and_comparison_render_every_product_below_cap_without_padding(self) -> None:
        products = _ranked_products(4)

        rendered = shopping_grid_html(products)
        rows = comparison_rows(products)

        self.assertEqual(rendered.count('<article class="shopping-card">'), 4)
        self.assertEqual(len(rows), 4)
        self.assertEqual(
            [row["Product"] for row in rows],
            [f"Ranked Product {index:02d}" for index in range(4)],
        )

    def test_grid_marks_only_the_canonical_first_card_without_a_reason_block(self) -> None:
        first = ComparisonProduct(
            private=_private_product().model_copy(
                update={"feature_evidence": ["Soft padded grip for comfortable play"]}
            ),
            live=None,
            conflicts=[],
            match=None,
        )
        second_private = _private_product().model_copy(
            update={
                "sku": "second-sku",
                "doc_id": "AMZ-SECOND",
                "title": "Second Toy Option",
            }
        )
        second = ComparisonProduct(
            private=second_private,
            live=None,
            conflicts=[],
            match=None,
        )
        top = TopRecommendation(
            product_key="catalog:AMZ-TEST",
            title=first.private.title,
            reason="Its $13.99 catalog price is within your $10–$20 range.",
        )

        rendered = shopping_grid_html(
            [first, second],
            top_recommendation=top,
        )

        self.assertEqual(rendered.count("Top recommendation"), 1)
        self.assertNotIn("Why it matches", rendered)
        self.assertNotIn(top.reason, rendered)
        self.assertIn("Matched detail", rendered)
        self.assertIn("Soft padded grip for comfortable play", rendered)
        cards = rendered.split('<article class="shopping-card">')[1:]
        self.assertIn("Top recommendation", cards[0])
        self.assertTrue(
            all("Top recommendation" not in card for card in cards[1:])
        )
        self.assertLess(
            rendered.index("Top recommendation"),
            rendered.index("Second Toy Option"),
        )

    def test_grounded_feature_evidence_is_visible_in_card_and_comparison(self) -> None:
        private = _private_product().model_copy(
            update={
                "feature_evidence": [
                    "Soft padded grip designed for comfortable play"
                ]
            }
        )
        product = ComparisonProduct(
            private=private,
            live=None,
            conflicts=[],
            match=None,
        )

        rendered = product_card_html(product)
        row = comparison_rows([product])[0]

        self.assertIn("Matched detail:", rendered)
        self.assertIn("Soft padded grip", rendered)
        self.assertIn("Soft padded grip", row["Matched details"])

    def test_comparison_table_keeps_missing_catalog_fields_explicit(self) -> None:
        product = ComparisonProduct(
            private=_private_product(),
            live=_live_product(),
            conflicts=[],
            match=None,
        )

        row = comparison_rows([product])[0]

        self.assertEqual(row["Sources"], "Catalog + Web search")
        self.assertEqual(row["Price shown"], "$21.95")
        self.assertEqual(row["Price source"], "Current web price")
        self.assertEqual(row["Catalog (2020)"], "$13.99")
        self.assertEqual(row["Web rating"], "4.8")
        self.assertEqual(row["Ingredients"], "— (not in catalog)")


if __name__ == "__main__":
    unittest.main()
