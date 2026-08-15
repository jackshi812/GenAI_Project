"""Regression tests for Serper Shopping URL normalization."""

from __future__ import annotations

import json
import unittest
from urllib.parse import urlparse

from mcp_server.web_search import FIXTURE_PATH, normalize_response

GOOGLE_SHOPPING_URL = "https://www.google.com/search?ibp=oshop&q=Eco+Cleaner&udm=28"


def _shopping_result(
    source: str,
    link: str = GOOGLE_SHOPPING_URL,
    image_url: str = "https://images.example.com/cleaner.jpg",
) -> dict:
    return {
        "shopping": [
            {
                "title": "Eco Cleaner",
                "source": source,
                "link": link,
                "price": "$12.99",
                "imageUrl": image_url,
            }
        ]
    }


class NormalizeResponseTests(unittest.TestCase):
    def test_serper_image_url_is_preserved(self) -> None:
        result = normalize_response(_shopping_result("Walmart"), num=1)

        self.assertEqual(
            result[0]["image_url"], "https://images.example.com/cleaner.jpg"
        )

    def test_non_http_image_url_is_dropped(self) -> None:
        result = normalize_response(
            _shopping_result("Walmart", image_url="file:///tmp/product.jpg"),
            num=1,
        )

        self.assertIsNone(result[0]["image_url"])

    def test_google_shopping_links_fall_back_to_retailer_search(self) -> None:
        cases = {
            "Amazon.com": "https://www.amazon.com/s?k=Eco+Cleaner",
            "Walmart": "https://www.walmart.com/search?q=Eco+Cleaner",
            "Target": "https://www.target.com/s?searchTerm=Eco+Cleaner",
            "eBay - trusted_seller": (
                "https://www.ebay.com/sch/i.html?_nkw=Eco+Cleaner"
            ),
        }

        for source, expected_url in cases.items():
            with self.subTest(source=source):
                result = normalize_response(_shopping_result(source), num=1)
                self.assertEqual(result[0]["url"], expected_url)
                self.assertIn("retailer search", result[0]["snippet"].lower())

    def test_recorded_fixtures_resolve_to_expected_retailers(self) -> None:
        fixtures = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        expected_hosts = {
            "lego classic creative suitcase 10713 building kit (213": {
                "www.ebay.com",
                "www.target.com",
                "www.walmart.com",
            },
            "nerf n strike elite strongarm toy blaster with": {"www.ebay.com"},
        }

        for fixture_id, hosts in expected_hosts.items():
            with self.subTest(fixture_id=fixture_id):
                results = normalize_response(fixtures[fixture_id], num=20)
                actual_hosts = {urlparse(item["url"]).hostname for item in results}
                self.assertEqual(actual_hosts, hosts)
                self.assertGreater(len(results), 0)

    def test_direct_allowed_retailer_link_is_preserved(self) -> None:
        direct_url = "https://www.walmart.com/ip/example/123"
        result = normalize_response(_shopping_result("Walmart", direct_url), num=1)

        self.assertEqual(result[0]["url"], direct_url)
        self.assertNotIn("retailer search", result[0]["snippet"].lower())

    def test_unknown_source_on_google_is_dropped(self) -> None:
        self.assertEqual(
            normalize_response(_shopping_result("Unknown Shop"), num=1), []
        )

    def test_source_cannot_bypass_allowlist_for_untrusted_host(self) -> None:
        malicious_links = (
            "https://malicious.example/product",
            "https://walmart.com.malicious.example/product",
            "https://notwalmart.com/product",
            "ftp://walmart.com/product",
        )

        for link in malicious_links:
            with self.subTest(link=link):
                self.assertEqual(
                    normalize_response(_shopping_result("Walmart", link), num=1),
                    [],
                )


if __name__ == "__main__":
    unittest.main()
