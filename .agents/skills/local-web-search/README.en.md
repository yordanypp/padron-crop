# local-web-search

[中文](README.md) · [English](README.en.md)

Zero-dependency local web search via **Bing** — no API key, no signup, no cloud proxy. Runs entirely on your own machine.

Works anywhere Bing is reachable, including environments where keyless cloud search (firecrawl/tavily/exa) is 403'd or rate-limited.

## Why

- API-based search needs a key and can 403 rate-limit ("your IP looks suspicious").
- DuckDuckGo is blocked in some regions.
- Bing's HTML endpoint is reachable without a key and returns parseable results.

## Install (as a skill)

```bash
npx skills add fangqian616/agent-local-web-search
```

Or manually: copy this folder into your agent's skills directory, e.g. `~/.agents/skills/local-web-search/`.

## Usage

```bash
node scripts/bing-search.mjs "your query terms" --limit 10
node scripts/bing-search.mjs "your query" --limit 5 --json
```

Output:

- Text (default): numbered `[title / url / snippet]` blocks.
- JSON (`--json`): `{ "query", "results": [{ "title", "url", "snippet" }] }`.

## Requirements

- Node.js 18+ (uses global `fetch`, zero npm dependencies).

## Caveats

- Parsing is regex-based; it can break if Bing changes markup or serves a consent/captcha page (the script exits non-zero in that case).
- Snippets are best-effort; open `url` for full content.

## License

MIT
