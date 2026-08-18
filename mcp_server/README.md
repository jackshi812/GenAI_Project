# Product-search MCP server

This folder is Austin's tool-layer contribution. One low-level MCP server runs
over stdio and advertises exactly two tools: `rag.search` and `web.search`.
Ginger's graph owns reconciliation; it is deliberately not a third tool.

## Tools

`rag.search` accepts required `query` plus optional `price_max`, `price_min`,
`category`, `brand`, and `k`. It calls `catalog.search.search` and returns
private Amazon 2020 evidence with null private ratings and ingredients. The
graph normally requests 12 candidates, reranks against stated preferences,
and returns at most six products to the interface.

`web.search` accepts required `query` plus optional `num`. With
`SERPER_API_KEY`, it calls Serper's Shopping endpoint. Without a key, it looks
for Jack's root-level `serper_fixtures.json`, whose exact shape is:

```json
{
  "first eight title words lowercased": {
    "shopping": [
      {
        "title": "Recorded Serper title",
        "link": "https://www.allowed-retailer.example/product",
        "source": "Retailer",
        "delivery": "In stock",
        "price": "$12.99",
        "rating": 4.6
      }
    ]
  }
}
```

The fixture must contain unmodified, real Serper response objects—not invented
evidence. Keys match exactly after taking the first eight whitespace-delimited
query words and lowercasing them. A miss honestly returns an empty list.

Live and replayed responses pass through one normalizer and a retailer-domain
allowlist. Direct allowlisted retailer links are preserved. Some Serper
Shopping responses instead contain a Google Shopping `/search` URL and put the
retailer in `source`. For known sources (`Amazon`, `Walmart`, `Target`, and
`eBay`, including `eBay - seller`), the normalizer returns an official retailer
search URL for the result title and marks the snippet `Retailer search
fallback`. It does not pretend that this fallback is a direct product page.
Unknown sources and non-Google untrusted URLs remain filtered.

The implementation never scrapes retailer pages; it calls Serper's API only.
A process-local TTL cache defaults to 180 seconds, outbound live calls are
spaced by one second, and a 50-call process cap protects API quota.

## Environment

```text
SERPER_API_KEY                 optional; enables live shopping results
WEB_SEARCH_CACHE_TTL           optional; clamped to 60-300, default 180
WEB_SEARCH_MIN_INTERVAL_S      optional; default 1.0
WEB_SEARCH_MAX_CALLS           optional; default 50
CHROMA_PATH                    optional; default catalog/chroma
```

Start the protocol server or run the end-to-end protocol smoke check from the
repository root:

```bash
python -m mcp_server.server
env -u SERPER_API_KEY python -m mcp_server.smoke
python -m mcp_server.smoke
python -m unittest mcp_server.test_web_search -v
```

The first command correctly prints nothing and waits for an MCP client on
stdin. JSONL audit logs are written under ignored `mcp_server/logs/`; request
arguments are recursively stripped of keys containing `key`, `token`, or
`secret`, and environment values are never logged.
