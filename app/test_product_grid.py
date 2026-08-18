"""Regression tests for the unified shopping-result cards."""

from __future__ import annotations

import unittest

from app.product_grid import comparison_rows, product_card_html, shopping_grid_html
from contracts import (
    ComparisonProduct,
    Conflict,
    MatchInfo,
    RagResult,
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
        self.assertEqual(row["Catalog (2020)"], "$13.99")
        self.assertEqual(row["Web rating"], "4.8")
        self.assertEqual(row["Ingredients"], "— (not in catalog)")


if __name__ == "__main__":
    unittest.main()
