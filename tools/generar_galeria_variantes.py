"""
Generador de visualizador HTML comparativo Antes / Después para la carpeta pruebas_variantes.
Crea un archivo visual interactivo para abrir en el navegador y auditar cada foto.
"""

from pathlib import Path
import json
import base64

def generate_comparison_gallery():
    base_dir = Path("pruebas_variantes")
    antes_dir = base_dir / "antes"
    despues_dir = base_dir / "despues"
    quarantine_dir = despues_dir / "quarantine"

    antes_files = sorted(antes_dir.glob("*.jpg"))
    cards = []

    for af in antes_files:
        stem = af.stem
        # Buscar resultado en despues directo o en quarantine
        df = despues_dir / f"{stem}.jpg"
        jf = despues_dir / f"{stem}.json"
        is_quarantine = False

        if not df.exists():
            df = quarantine_dir / f"{stem}.jpg"
            jf = quarantine_dir / f"{stem}.json"
            is_quarantine = True

        status = "desconocido"
        sides = []
        crop_box = []
        method = "n/a"
        quarantine_reason = ""

        if jf.exists():
            try:
                with open(jf, "r", encoding="utf-8") as fp:
                    data = json.load(fp)
                    status = data.get("status", "ok")
                    sides = data.get("sides", [])
                    crop_box = data.get("crop_box_xywh", [])
                    method = data.get("method", "")
                    quarantine_reason = data.get("quarantine_reason", "")
            except Exception:
                pass

        if is_quarantine:
            status = "quarantine"

        # Rutas relativas para que cargue en el navegador sin problemas
        rel_antes = f"antes/{af.name}"
        rel_despues = f"despues/quarantine/{df.name}" if is_quarantine else f"despues/{df.name}"

        cards.append({
            "name": stem,
            "status": status,
            "sides": ", ".join(sides) if sides else "ninguno (limpia)",
            "crop_box": str(crop_box) if crop_box else "n/a",
            "method": method,
            "reason": quarantine_reason,
            "antes_path": rel_antes,
            "despues_path": rel_despues,
        })

    html_content = f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <title>Auditoría de Variantes de Estrés - Padrón Crop</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
            background: #0f172a;
            color: #f8fafc;
            margin: 0;
            padding: 20px;
        }}
        .header {{
            background: #1e293b;
            padding: 24px;
            border-radius: 12px;
            margin-bottom: 24px;
            border: 1px solid #334155;
        }}
        h1 {{ margin: 0 0 8px 0; font-size: 24px; color: #38bdf8; }}
        p {{ margin: 0 0 16px 0; color: #94a3b8; font-size: 14px; }}
        .stats-bar {{
            display: flex;
            gap: 16px;
            flex-wrap: wrap;
        }}
        .badge {{
            padding: 6px 14px;
            border-radius: 20px;
            font-size: 13px;
            font-weight: 600;
        }}
        .badge-ok {{ background: #065f46; color: #34d399; }}
        .badge-quarantine {{ background: #854d0e; color: #facc15; }}
        .badge-noop {{ background: #1e3a8a; color: #60a5fa; }}
        
        .grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(580px, 1fr));
            gap: 20px;
        }}
        .card {{
            background: #1e293b;
            border-radius: 10px;
            border: 1px solid #334155;
            padding: 16px;
            display: flex;
            flex-direction: column;
            gap: 12px;
        }}
        .card-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid #334155;
            padding-bottom: 8px;
        }}
        .card-title {{
            font-weight: bold;
            font-size: 14px;
            color: #e2e8f0;
            word-break: break-all;
        }}
        .comparison-view {{
            display: flex;
            gap: 12px;
            justify-content: space-around;
        }}
        .img-box {{
            flex: 1;
            text-align: center;
            background: #0b0f19;
            padding: 8px;
            border-radius: 8px;
            border: 1px solid #1e293b;
        }}
        .img-box img {{
            max-width: 100%;
            height: 240px;
            object-fit: contain;
            border-radius: 4px;
        }}
        .img-label {{
            font-size: 12px;
            margin-top: 6px;
            font-weight: bold;
        }}
        .label-antes {{ color: #f87171; }}
        .label-despues {{ color: #4ade80; }}
        .meta {{
            font-size: 12px;
            color: #94a3b8;
            line-height: 1.5;
            background: #0f172a;
            padding: 10px;
            border-radius: 6px;
        }}
        .meta-quarantine {{
            border-left: 3px solid #facc15;
            color: #fef08a;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>📊 Auditoría Comparativa de Variantes de Estrés (Padrón PRM)</h1>
        <p>Prueba de estrés generada a partir de la foto real del padrón (0aaa2b82-4607-4f53-8a28-ccafa017104d.jpg). Moviendo la barra y logo PRM arriba, abajo, izquierda, derecha y marcos completos.</p>
        <div class="stats-bar">
            <span class="badge badge-ok">✅ Recortadas con Éxito: {sum(1 for c in cards if c['status'] == 'ok')}</span>
            <span class="badge badge-quarantine">⚠️ Protegidas por Face Safety Gate (Cuarentena): {sum(1 for c in cards if c['status'] == 'quarantine')}</span>
            <span class="badge badge-noop">ℹ️ Ya Limpias (Noop): {sum(1 for c in cards if c['status'] == 'noop')}</span>
            <span class="badge" style="background: #334155; color: #e2e8f0;">Total Pruebas: {len(cards)}</span>
        </div>
    </div>

    <div class="grid">
"""

    for c in cards:
        status_badge = ""
        if c["status"] == "ok":
            status_badge = '<span class="badge badge-ok">OK (Recortada)</span>'
        elif c["status"] == "quarantine":
            status_badge = '<span class="badge badge-quarantine">CUARENTENA (Protegida)</span>'
        else:
            status_badge = '<span class="badge badge-noop">NOOP (Limpia)</span>'

        reason_block = ""
        if c["reason"]:
            reason_block = f'<div class="meta meta-quarantine"><strong>🛡️ Razón de Protección:</strong> {c["reason"]}</div>'

        html_content += f"""
        <div class="card">
            <div class="card-header">
                <span class="card-title">{c['name']}</span>
                {status_badge}
            </div>
            <div class="comparison-view">
                <div class="img-box">
                    <img src="{c['antes_path']}" alt="Antes">
                    <div class="img-label label-antes">ANTES (Con PRM)</div>
                </div>
                <div class="img-box">
                    <img src="{c['despues_path']}" alt="Después">
                    <div class="img-label label-despues">DESPUÉS (Resultado)</div>
                </div>
            </div>
            <div class="meta">
                <div><strong>Lados Recortados:</strong> {c['sides']}</div>
                <div><strong>Caja Recorte (xywh):</strong> {c['crop_box']}</div>
                <div><strong>Método:</strong> {c['method']}</div>
            </div>
            {reason_block}
        </div>
        """

    html_content += """
    </div>
</body>
</html>
"""

    out_file = base_dir / "00_visualizador_antes_despues.html"
    with open(out_file, "w", encoding="utf-8") as fp:
        fp.write(html_content)

    print(f"[OK] Visualizador generado en: {out_file.resolve()}")
    return out_file

if __name__ == "__main__":
    generate_comparison_gallery()
