"""Interactive, offline-capable HTML Visual QA Gallery generator.

Reads JSON sidecar files in an output directory and builds a standalone
interactive HTML report with filters, stats, and side-by-side card views.
"""
from __future__ import annotations

import html
import json
from pathlib import Path


def generate_gallery_html(records: list[dict], out_dir: Path) -> str:
    """Render a standalone, modern HTML visual report for quality audits."""
    total = len(records)
    ok_count = sum(1 for r in records if r.get("status") == "ok")
    quarantine_count = sum(1 for r in records if r.get("status") == "quarantine")
    failed_count = sum(1 for r in records if r.get("status") == "failed")
    noop_count = sum(1 for r in records if r.get("status") == "noop")

    cards_html = []
    for r in records:
        st = r.get("status", "unknown")
        src = r.get("source", "")
        stem = Path(src).stem if src else "sample"
        out_path = r.get("out_path", "")
        # Compute relative path to display image in HTML if it lives inside out_dir
        img_rel = ""
        if out_path:
            try:
                img_rel = str(Path(out_path).relative_to(out_dir)).replace("\\", "/")
            except ValueError:
                img_rel = str(out_path)

        method = r.get("method", "none")
        conf = r.get("confidence", 0.0)
        ms = r.get("elapsed_ms", 0)
        face = "Yes" if r.get("face_detected") else "No"
        face_safe = "Safe" if r.get("face_safety_ok", True) else "VIOLATION"
        skew = r.get("skew_angle", 0.0)
        wh = r.get("orig_wh") or ["-", "-"]
        crop_box = r.get("crop_box_xywh") or ["-", "-", "-", "-"]
        q_reason = r.get("quarantine_reason") or r.get("error") or ""

        badge_class = {
            "ok": "badge-ok",
            "quarantine": "badge-warn",
            "failed": "badge-fail",
            "noop": "badge-noop",
        }.get(st, "badge-noop")

        img_tag = f'<img src="{html.escape(img_rel)}" loading="lazy" alt="Cropped preview" />' if img_rel else '<div class="no-img">No Image Available</div>'

        card = f"""
        <div class="card" data-status="{st}">
            <div class="card-header">
                <span class="badge {badge_class}">{st.upper()}</span>
                <span class="card-title" title="{html.escape(src)}">{html.escape(stem)}</span>
            </div>
            <div class="img-container">
                {img_tag}
            </div>
            <div class="card-body">
                <div class="row"><span>Method:</span><b>{html.escape(str(method))}</b></div>
                <div class="row"><span>Confidence:</span><b>{conf:.2f}</b></div>
                <div class="row"><span>Original:</span><b>{wh[0]}x{wh[1]}</b></div>
                <div class="row"><span>Crop Box:</span><b>{crop_box[0]},{crop_box[1]},{crop_box[2]},{crop_box[3]}</b></div>
                <div class="row"><span>Face / Chin:</span><b>{face} / {face_safe}</b></div>
                <div class="row"><span>Skew:</span><b>{skew}&deg;</b></div>
                <div class="row"><span>Time:</span><b>{ms} ms</b></div>
                {f'<div class="reason"><b>Notice:</b> {html.escape(q_reason)}</div>' if q_reason else ''}
            </div>
        </div>
        """
        cards_html.append(card)

    cards_joined = "\n".join(cards_html)

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Padrón Crop - Visual QA Gallery</title>
<style>
  :root {{
    --bg: #0f172a;
    --card-bg: #1e293b;
    --text: #f8fafc;
    --text-muted: #94a3b8;
    --ok: #22c55e;
    --warn: #eab308;
    --fail: #ef4444;
    --noop: #38bdf8;
    --border: #334155;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background-color: var(--bg);
    color: var(--text);
    padding: 24px;
  }}
  header {{
    margin-bottom: 24px;
    padding-bottom: 16px;
    border-bottom: 1px solid var(--border);
  }}
  h1 {{ font-size: 1.6rem; margin-bottom: 8px; font-weight: 700; }}
  .stats-bar {{
    display: flex;
    gap: 16px;
    flex-wrap: wrap;
    margin: 16px 0;
  }}
  .stat-pill {{
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 8px 16px;
    font-size: 0.9rem;
  }}
  .stat-pill b {{ font-size: 1.1rem; }}
  .filters {{
    display: flex;
    gap: 8px;
    margin-top: 16px;
  }}
  .filter-btn {{
    background: var(--card-bg);
    color: var(--text);
    border: 1px solid var(--border);
    padding: 8px 16px;
    border-radius: 6px;
    cursor: pointer;
    font-weight: 600;
    transition: all 0.2s;
  }}
  .filter-btn:hover, .filter-btn.active {{
    background: #3b82f6;
    border-color: #3b82f6;
  }}
  .grid {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 20px;
    margin-top: 24px;
  }}
  .card {{
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 10px;
    overflow: hidden;
    display: flex;
    flex-direction: column;
  }}
  .card-header {{
    padding: 12px;
    display: flex;
    align-items: center;
    gap: 8px;
    border-bottom: 1px solid var(--border);
  }}
  .badge {{
    font-size: 0.75rem;
    font-weight: 800;
    padding: 3px 8px;
    border-radius: 4px;
    text-transform: uppercase;
  }}
  .badge-ok {{ background: rgba(34,197,94,0.2); color: var(--ok); border: 1px solid var(--ok); }}
  .badge-warn {{ background: rgba(234,179,8,0.2); color: var(--warn); border: 1px solid var(--warn); }}
  .badge-fail {{ background: rgba(239,68,68,0.2); color: var(--fail); border: 1px solid var(--fail); }}
  .badge-noop {{ background: rgba(56,189,248,0.2); color: var(--noop); border: 1px solid var(--noop); }}
  .card-title {{
    font-size: 0.85rem;
    font-weight: 600;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }}
  .img-container {{
    height: 260px;
    background: #020617;
    display: flex;
    align-items: center;
    justify-content: center;
    overflow: hidden;
  }}
  .img-container img {{
    max-height: 100%;
    max-width: 100%;
    object-fit: contain;
  }}
  .no-img {{
    color: var(--text-muted);
    font-size: 0.85rem;
  }}
  .card-body {{
    padding: 12px;
    font-size: 0.8rem;
    display: flex;
    flex-direction: column;
    gap: 4px;
    background: #182234;
  }}
  .card-body .row {{
    display: flex;
    justify-content: space-between;
    color: var(--text-muted);
  }}
  .card-body .row b {{
    color: var(--text);
  }}
  .reason {{
    margin-top: 8px;
    padding: 6px;
    background: rgba(239,68,68,0.15);
    border-left: 3px solid var(--fail);
    border-radius: 4px;
    color: #fca5a5;
    font-size: 0.75rem;
  }}
</style>
</head>
<body>
<header>
  <h1>Padr\u00f3n Crop &mdash; Visual QA Gallery</h1>
  <div class="stats-bar">
    <div class="stat-pill">Total: <b>{total}</b></div>
    <div class="stat-pill" style="color:var(--ok)">Ok: <b>{ok_count}</b></div>
    <div class="stat-pill" style="color:var(--warn)">Quarantine: <b>{quarantine_count}</b></div>
    <div class="stat-pill" style="color:var(--fail)">Failed: <b>{failed_count}</b></div>
    <div class="stat-pill" style="color:var(--noop)">Noop: <b>{noop_count}</b></div>
  </div>
  <div class="filters">
    <button class="filter-btn active" onclick="setFilter('all')">Todos ({total})</button>
    <button class="filter-btn" onclick="setFilter('ok')">Ok ({ok_count})</button>
    <button class="filter-btn" onclick="setFilter('quarantine')">Quarantine ({quarantine_count})</button>
    <button class="filter-btn" onclick="setFilter('failed')">Failed ({failed_count})</button>
  </div>
</header>

<div class="grid" id="cardGrid">
{cards_joined}
</div>

<script>
function setFilter(st) {{
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
  event.target.classList.add('active');
  document.querySelectorAll('.card').forEach(c => {{
    if (st === 'all' || c.getAttribute('data-status') === st) {{
      c.style.display = 'flex';
    }} else {{
      c.style.display = 'none';
    }}
  }});
}}
</script>
</body>
</html>
"""


def build_gallery(out_dir: Path, html_path: Path | None = None, limit: int | None = None) -> Path:
    """Scan out_dir for JSON sidecars and write the HTML gallery file."""
    out_dir = Path(out_dir)
    target = Path(html_path) if html_path else out_dir / "gallery.html"

    records = []
    for p in sorted(out_dir.rglob("*.json")):
        if p.name.startswith("."):
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "status" in data:
                records.append(data)
                if limit and len(records) >= limit:
                    break
        except Exception:
            continue

    content = generate_gallery_html(records, out_dir)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return target
