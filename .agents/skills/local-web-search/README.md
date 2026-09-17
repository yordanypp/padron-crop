# local-web-search

[中文](README.md) · [English](README.en.md)

零依赖的本地网页搜索，基于 **Bing** 实现 —— 无需 API key、无需注册、无需云代理，完全在你自己的机器上运行。

在 Bing 可达的任何环境都能用，尤其是那些 keyless 云搜索（firecrawl / tavily / exa）被 403 或限流的场景。

## 为什么

- API 搜索需要 key，而且可能被 403 限流（提示「你的 IP 可疑」）；
- DuckDuckGo 在部分网络环境下被墙；
- Bing 的 HTML 端点无需 key 即可访问，且返回可解析的结果。

## 安装（作为技能）

```bash
npx skills add fangqian616/agent-local-web-search
```

或手动：把本目录复制到你的智能体技能目录，例如 `~/.agents/skills/local-web-search/`。

## 用法

```bash
node scripts/bing-search.mjs "你的查询词" --limit 10
node scripts/bing-search.mjs "你的查询词" --limit 5 --json
```

输出：

- 文本（默认）：编号的 `[标题 / 链接 / 摘要]` 块；
- JSON（`--json`）：`{ "query", "results": [{ "title", "url", "snippet" }] }`。

## 环境要求

- Node.js 18+（使用全局 `fetch`，零 npm 依赖）。

## 注意事项

- 解析基于正则，若 Bing 改版或返回验证码 / 同意页（此时脚本以非零码退出）可能失效；
- 摘要为尽力提取，完整内容请打开 `url`。

## License

MIT
