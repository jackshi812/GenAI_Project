"""End-to-end smoke run: all three canonical queries through run_graph.

Usage:
    python -m graph.smoke
    python -m graph.smoke | tee graph/sample_output.txt

The captured output is the August 13 checkpoint deliverable — real output
produced by the real graph, never hand-written.
"""

import json
from pathlib import Path

from graph.build import run_graph

_REPO_ROOT = Path(__file__).resolve().parents[1]

# Fallbacks if catalog/canonical_queries.json is absent (D-16 queries).
_FALLBACK_TRANSCRIPTS = [
    "Find me a 500 piece jigsaw puzzle under twenty dollars.",
    "What is the current price and availability of the LEGO Classic Creative Suitcase 10713?",
    "Compare the current price of the Nerf N Strike Elite Strongarm blaster with the catalog price.",
]


def canonical_transcripts() -> list[str]:
    path = _REPO_ROOT / "catalog" / "canonical_queries.json"
    if path.exists():
        entries = json.loads(path.read_text(encoding="utf-8"))
        return [e["transcript"] for e in entries]
    return _FALLBACK_TRANSCRIPTS


def main() -> None:
    for i, transcript in enumerate(canonical_transcripts(), 1):
        print("=" * 78)
        print(f"CANONICAL QUERY {i}: {transcript}")
        print("=" * 78)
        result = run_graph(transcript)

        print(f"\nplan: {result.plan}")

        print("\nsteps:")
        for s in result.steps:
            print(
                f"  [{s.status:>9}] {s.node:<10} tool={s.tool or '-':<12} "
                f"{s.duration_ms}ms  {s.detail}"
            )

        print("\nproducts:")
        for p in result.products:
            r = p.private
            print(f"  PRIVATE {r.doc_id}: {r.title[:60]!r} price={r.price!r}")
            if p.live is not None:
                print(
                    f"     LIVE: {p.live.title[:60]!r} price={getattr(p.live, 'price', None)} "
                    f"rating={getattr(p.live, 'rating', None)}"
                )
            else:
                print("     LIVE: none")
            for c in p.conflicts:
                print(f"     CONFLICT {c.field}: {c.note}")
            if p.match is not None:
                print(
                    f"     MATCH: {p.match.verdict} similarity={p.match.similarity} "
                    f"({p.match.reason})"
                )

        wc = len(result.answer_text.split())
        print(f"\nanswer ({wc} words): {result.answer_text}")
        print("citations:")
        for c in result.citations:
            print(f"  [{c.kind}] {c.label}" + (f" {c.url}" if c.url else ""))
        print()


if __name__ == "__main__":
    main()
