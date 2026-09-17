# sample-geometry.md — Geometría medida de la JPEG ancla

Fecha de medición: 2026-09-17. Herramienta: `tools/inspect_sample.py` + `tools/row_probe.py` (numpy + Pillow puro, sin OpenCV). Evidencia cruda en `out/sample-0/inspect.json`, `out/sample-0/row_probe.json`, `out/sample-0/profiles.png`.

## Archivo ancla

| Propiedad | Valor medido |
|---|---|
| Archivo | `0aaa2b82-4607-4f53-8a28-ccafa017104d.jpg` |
| SHA-256 | `c6c151cb6dc94bf895872ae67ac8708e324f498f08d1be2d8eaf60735e2ae613` |
| Bytes | 87,882 |
| Dimensiones (tras EXIF) | 960 × 1280 (W×H) |
| EXIF orientation | 1 (no rotada) |
| Modo | RGB |

## Hallazgo principal (corrección al brief)

El bloque negro/PRM **no es una "barra fina en un borde"**: es un **apéndice oscuro en la mitad inferior derecha** que arranca *dentro* de la foto (y≈860) y crece hacia abajo, no una banda separada del contenido. La foto útil (persona, fondo brillante) llega hasta **y≈860**.

## Números medidos

### Estructura vertical (bandas de 10 filas, full width)

| Rango y | mean_luma | % estricto oscuro (<16/255) | % brillante (>0.6) | Lectura |
|---|---|---|---|---|
| 0–860 | alto (0.27–0.38 en 760–830) | ~0 | >0.09 | contenido de la foto |
| 860–990 | 0.20–0.28 | 0.05→0.30 | 0.0195→0 | **transición: hombro/fondo oscureciéndose** — zona ambigua, NO recortar a ciegas aquí |
| 990–1085 | 0.12–0.22 | 0.30→0.40 | 0 (salvo glifos) | zona oscura con texto |
| 1085–1280 | 0.03–0.06 | **0.64→0.95** | 0 | bloque negro casi sólido |

- Fila exacta donde el negro sólido (>70% de la fila < 16/255) empieza: **y = 1088**.
- Glifos blancos ("PRM" u otras siglas, 3 letras): **y 1009–1081, x 352–509** (medición fina por píxel).

### Glifos "PRM" (regiones conectadas de luma>0.6)

| bbox (x,y,w,h) | bright_frac |
|---|---|
| 355, 1010, 40, 60 | 0.3496 |
| 410, 1015, 45, 60 | 0.3726 |
| 465, 1020, 35, 65 | 0.3736 |

Ancho total del texto: **x 352–509 (157 px)**, centrado-ish horizontal (centro 430 vs 480).

### Componentes oscuras grandes (luma<16/255)

1. `[x=0, y=830, w=960, h=450]` fill 0.845 — bbox que envuelve bloque+borde inferior (incluye píxeles no oscuros del hombro).
2. `[x=664, y=744, w=296, h=536]` fill **0.934** — **el bloque oscuro real**, arranca en y≈744 junto al borde derecho, bajo el brazo.

### Por lado (perfil de proyección, escaneo hasta 480 px)

| Lado | % oscuro estricto del margen (H/20) | mean_luma | Interpretación |
|---|---|---|---|
| top | 0.0013 | 0.273 | limpio |
| left | 0.1221 (84% gris <48/255) | 0.114 | **sombra/ropa oscura del sujeto**, NO barra; el perfil por columna es plano ~0.135 en todo el rango |
| right | 0.2893 | 0.171 | mezcla de contenido oscuro y borde del bloque; sin banda sólida de ancho completo |
| bottom | **0.9243** | 0.036 | casi todo negro; contiene el bloque y las esquinas |

## Decisión de recorte para la ancla (verificada contra cara)

- **Línea de recorte: `crop_box = (0, 0, 960, 1004)`** — deja 5 px de margen sobre el tope del texto (1009) y 84 px sobre el negro sólido.
- Descarta: el bloque negro (fill 0.934), la zona casi-negra (1085–1280) y el texto PRM (1009–1081).
- La cara está en la **mitad superior** (regiones brillantes grandes `[160,65,715,795]`); queda **intacta**.
- Se conserva el hombro/lateral oscuro 860–1004 que es contenido legítimo. En la vista previa `out/sample-0/preview_crop_y1004.png` se aprecia: persona completa, sin PRM, sin negro sólido.
- Elimina 276 filas = **21.6% de la altura**.

## Implicaciones de diseño (insumo para la spec)

1. **Un umbral global sobre filas completas NO basta** (el bloque no cruza el ancho completo en y 830–1088). El detector debe usar **proyección por fila/columna + componentes conexas** ancladas al borde y combinar ambas evidencias.
2. **"Primer gran salto de oscuridad desde abajo" ≠ línea de recorte segura** (y=830 invadiría contenido). La línea correcta es *el tope del contenido no-deseado menos margen*: bounding del texto + negro sólido.
3. El texto puede estar **por encima del negro sólido sobre fondo intermedio**: el detector de texto claro (luma>0.6, área 35–65 px de alto) dentro de zonas oscuras es un ancla fuerte del tope del bloque.
4. El lado "left" demuestra el riesgo de falso positivo de "lado oscuro": ~84% gris oscuro pero es ropa/sombra. Regla: solo recortar franjas que tocan el borde, con alto fill oscuro, sin píxeles brillantes significativos, y con continuidad de líneas consecutivas.
5. La cara nunca debe invadirse: QA visual y regla de "no hay píxeles de piel/brillo en la zona a recortar".

## Incertidumbres

- El texto de los glifos no se leyó con OCR (tesseract no instalado); la hipótesis "PRM" viene del brief del usuario + geometría compatible (3 glifos). Marcado [uncertain] el contenido exacto del texto.
- No se verificó aún si el patrón (posición/tamaño del bloque) es constante en el lote; el fast-path D0 lo decidirá con N≥5 muestras reales.
- La banda 860–1004 se conservó por seguridad (hombro/ropa). Si el usuario confirma que esa zona gris también es "relleno no deseado", la línea podría subir, pero la evidencia de píxeles no permite afirmarlo.
