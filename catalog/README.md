# Private catalog and hybrid retrieval

This folder is Austin's data-layer contribution. It normalizes the tracked
Amazon Product Dataset 2020 CSV, writes the assignment's `products.parquet`,
builds a persistent Chroma collection, and exposes semantic retrieval with
numeric/category/brand metadata filters.

## Data behavior

- All 10,002 products are indexed because the suggested household-cleaning
  slice is not meaningfully represented in this copy of the dataset.
- `Selling Price` is retained as `price_raw` and parsed into numeric
  `price_low`/`price_high` bounds when possible. Unparseable rows are never
  converted to zero and remain searchable without numeric filters.
- `sku` comes from the complete unique `Uniq Id`; citations use the shorter
  `AMZ-XXXXXXXX` `doc_id`.
- The source has no ratings or ingredients. Both fields are returned as null.
- Embeddings use title plus `About Product` and bounded technical details.
  Spoken budget language must be separated by the planner: only the semantic
  product meaning goes into `query`; prices go into numeric filters.
- Search reranks a wider semantic pool using title and detail-term coverage.
  Each result may include up to three query-relevant `feature_evidence`
  excerpts copied from the real `About Product` / technical fields. Responses
  may use those excerpts but may not infer an unstated feature.

## Build and verify

Run these commands from the repository root after Jack's shared dependencies
are installed:

```bash
python -m catalog.normalize
python -m catalog.build_index
python -m catalog.smoke | tee catalog/sample_output.txt
```

The first Chroma build downloads the local `all-MiniLM-L6-v2` ONNX model and
may take several minutes on CPU. It requires no GPU, embedding API, or LLM key.
The generated `catalog/chroma/` directory is intentionally ignored by Git.
Rebuild it when the CSV, normalization, embedding implementation, or Chroma
version changes; otherwise reuse the existing local index.

## Python seam

```python
from catalog.search import search

results = search(
    "500 piece jigsaw puzzle",
    price_max=20.0,
    category="Toys & Games",
    k=5,
)
```

Each result contains the assignment's seven public fields plus display,
provenance, and grounded feature-evidence fields. Range prices whose low end
qualifies but high end exceeds a budget are labeled `budget_fit="partial"` and
sorted below full fits.
