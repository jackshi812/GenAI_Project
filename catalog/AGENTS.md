# Austin catalog ownership

- Austin owns every implementation file in this folder.
- This folder normalizes and retrieves the private Amazon 2020 catalog.
- Read `../Instructions.md` before changing public result shapes.
- The working CSV is `../dataset/amazon_product_data_cleaned.csv`.
- It omits thirteen source columns that were empty in all 10,002 rows.
- The private data has no ratings; private `rating` must always be null.
- The private data has no ingredients; do not infer them.
- Preserve malformed raw price text even when numeric parsing fails.
- Derive brands conservatively and return null instead of guessing.
- Embed title and actual feature text from `About Product`.
- Budget arithmetic belongs in Chroma metadata filters, never query text.
- Unparseable-price products remain available to semantic title search.
- Every result keeps its short catalog `doc_id` for citations.
- `catalog/chroma/` is generated locally and must not be committed.
- Keep `CLAUDE.md` and `AGENTS.md` byte-identical.
