---
name: local-web-search
description: Zero-dependency local web search via Bing when the primary search tool fails (web_search 403 / firecrawl keyless rejected) or no search API key is configured. Use when you need to search the web and cloud/API search is unavailable, rate-limited, or blocked. Runs `scripts/bing-search.mjs` (Node 18+) or fetches bing.com/search directly and parses title/url/snippet results.
---

# Local Web Search (Bing, no API key)

Zero-dependency web search that hits Bing's HTML directly from the local machine — no firecrawl, no API key, no signup.

## When to use

- `web_search` fails with 403 ("firecrawl rejected the keyless request") or every engine failed.
- No search API key (firecrawl / tavily / exa) is configured.
- You want a quick search without cloud dependencies.

## How to search

Run the Python search engine (zero-dependency, robust):

```bash
python scripts/search.py "your query terms" 5
```

Or run via Bing parser if preferred:

```bash
node scripts/bing-search.mjs "your query terms" --limit 5
```

## Output

- Text (default): numbered `[title / url / snippet]` blocks.
- JSON (`--json`): `{ "query", "results": [{ "title", "url", "snippet" }] }`.

## Caveats

- Bing serves HTML; parsing is regex-based and can break if Bing changes markup or serves a consent/captcha page (the script exits non-zero in that case).
- DuckDuckGo is blocked in some regions, so Bing is used because it is reachable without a key.
- Snippets are best-effort; open `url` for full content.
