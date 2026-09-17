#!/usr/bin/env node
/**
 * bing-search.mjs — zero-dependency local web search via Bing (no API key).
 *
 * Usage:
 *   node bing-search.mjs "query terms" [--limit N] [--json]
 *
 * Output:
 *   text (default): numbered [title / url / snippet] blocks
 *   json (--json) : { query, results: [{ title, url, snippet }] }
 */
import { fileURLToPath } from "node:url";

const args = process.argv.slice(2);
let limit = 10;
let asJson = false;
const queryParts = [];

for (let i = 0; i < args.length; i++) {
  const a = args[i];
  if (a === "--json") asJson = true;
  else if (a === "--limit") { limit = parseInt(args[++i], 10) || 10; }
  else if (a.startsWith("--limit=")) { limit = parseInt(a.slice(8), 10) || 10; }
  else queryParts.push(a);
}

const query = queryParts.join(" ").trim();
if (!query) {
  console.error('Usage: node bing-search.mjs "query terms" [--limit N] [--json]');
  process.exit(1);
}
limit = Math.max(1, Math.min(50, limit));

const UA =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36";

function decodeEntities(s) {
  return String(s)
    .replace(/&#(\d+);/g, (_, n) => String.fromCodePoint(Number(n)))
    .replace(/&#x([0-9a-f]+);/gi, (_, n) => String.fromCodePoint(parseInt(n, 16)))
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&apos;|&#39;/g, "'")
    .replace(/&nbsp;|&ensp;|&emsp;/g, " ")
    .replace(/&middot;/g, "·")
    .replace(/&hellip;/g, "…");
}

function stripTags(s) {
  return decodeEntities(String(s).replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim());
}

function parseResults(html, max) {
  const out = [];
  const blocks = html.split(/<li class="b_algo"/i).slice(1);
  for (const block of blocks) {
    const link = /<h2[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*>([\s\S]*?)<\/a>/i.exec(block);
    if (!link) continue;
    const url = decodeEntities(link[1]);
    const title = stripTags(link[2]);
    if (!url || !title) continue;
    if (/bing\.com|microsoft\.com|msn\.com|go\.microsoft/i.test(url)) continue;
    const p = /<p[^>]*>([\s\S]*?)<\/p>/i.exec(block);
    const snippet = p ? stripTags(p[1]) : "";
    out.push({ title, url, snippet });
    if (out.length >= max) break;
  }
  return out;
}

const url =
  "https://www.bing.com/search?q=" +
  encodeURIComponent(query) +
  "&count=" +
  Math.min(limit + 5, 30);

try {
  const resp = await fetch(url, {
    headers: {
      "User-Agent": UA,
      "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
      "Accept-Language": "en-US,en;q=0.9,es;q=0.8",
      "Cookie": "SRCHHPGUSR=ADLT=OFF&NRSLT=20",
    },
    signal: AbortSignal.timeout(20000),
  });
  if (!resp.ok) {
    console.error("HTTP " + resp.status + " from Bing");
    process.exit(1);
  }
  const html = await resp.text();
  const results = parseResults(html, limit);
  if (results.length === 0) {
    console.error("No results parsed (Bing may have served a consent/captcha page).");
    process.exit(1);
  }
  if (asJson) {
    console.log(JSON.stringify({ query, results }, null, 2));
  } else {
    results.forEach((r, i) => {
      console.log(`[${i + 1}] ${r.title}`);
      console.log(`    ${r.url}`);
      if (r.snippet) console.log(`    ${r.snippet}`);
      console.log("");
    });
  }
} catch (e) {
  console.error("fetch failed: " + (e && e.message ? e.message : e));
  process.exit(1);
}
