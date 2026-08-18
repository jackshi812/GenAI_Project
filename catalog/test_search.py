"""Unit checks for grounded feature excerpts and attribute-aware reranking."""

from __future__ import annotations

import unittest

from catalog.search import _feature_evidence, _rank_score


class CatalogSearchTests(unittest.TestCase):
    def test_feature_evidence_copies_only_relevant_source_segments(self) -> None:
        title = "Blue Walking Shoes"
        document = (
            f"{title}\n\nMake sure this fits by entering your model number. | "
            "Cushioned footbed provides comfortable support all day | "
            "Waterproof rubber outsole"
        )

        evidence = _feature_evidence(
            "comfortable cushioned walking shoes",
            document,
            title,
        )

        self.assertEqual(
            evidence,
            ["Cushioned footbed provides comfortable support all day"],
        )
        self.assertNotIn("Make sure this fits", " ".join(evidence))

    def test_feature_coverage_can_outrank_title_only_similarity(self) -> None:
        query = "comfortable cushioned walking shoes"
        detailed = _rank_score(
            query,
            "Walking Shoes",
            "Walking Shoes\n\nComfortable cushioned footbed",
            0.55,
        )
        generic = _rank_score(
            query,
            "Walking Shoes",
            "Walking Shoes\n\nBasic upper",
            0.65,
        )

        self.assertGreater(detailed, generic)


if __name__ == "__main__":
    unittest.main()
