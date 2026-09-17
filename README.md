# Padrón Crop — Pipeline Masivo de Recorte Automático

Pipeline determinista de alta velocidad en Python para eliminar la franja inferior con la marca política **"PRM"** y barras negras de fotografías del padrón electoral mediante **recorte geométrico puro** (nunca inpainting, nunca alteración ni generación de píxeles). Diseñado para escalar a millones de fotos y gigabytes de datos con consumo de memoria acotado.

---

## ⚡ Guía Rápida: Cómo Usarlo en Corto

### Opción A: Con Doble Clic (Windows)
1. Haz doble clic en **`ejecutar_recorte.bat`** (o `run.bat`).
2. Se abrirá el menú interactivo:
   - Presiona `[1]` para procesar la imagen de muestra.
   - Presiona `[2]` para procesar una carpeta completa con miles de fotos.
   - Presiona `[3]` para abrir la **Galería Visual Interactiva** en tu navegador.
   - Presiona `[4]` para correr los **110 tests automatizados**.

### Opción B: Comando Manual Corto (1 sola línea)

**Procesar una sola foto:**
```bash
python -m padron_crop crop --in "0aaa2b82-4607-4f53-8a28-ccafa017104d.jpg" --out "out/foto_limpia.jpg" --deskew
```

**Procesar una carpeta completa con miles de fotos (4 núcleos, reanudable):**
```bash
python -m padron_crop batch --src "C:\fotos_padron" --out "out\fotos_limpias" --workers 4 --resume --deskew
```

**Ver el reporte visual de calidad:**
```bash
python -m padron_crop gallery --out "out\fotos_limpias"
# Abre out\fotos_limpias\gallery.html en Chrome/Edge
```

---

## 📂 Carpeta de Prototipos (Para mostrar a tu supervisor)

La carpeta **`prototipos/`** ya está lista con los resultados generados:
* `01_original_muestra.jpg` — Foto original con bloque PRM y barra inferior de Windows.
* `02_recorte_automatico_prm.jpg` — Foto recortada limpia por el algoritmo determinista.
* `03_recorte_formato_cedula_3x4.jpg` — Proporción estándar 3:4 para cédulas/carnets.
* `04_recorte_cuadrado_1x1.jpg` — Proporción 1:1 para sistemas web/avatares.
* **`05_visualizador_comparativo.html`** — **Doble clic para abrir en cualquier navegador.** Muestra la comparativa interactiva lado a lado, dimensiones, estados y certificación de barbilla protegida.

---

## 🗄️ ¿Cómo trabajar si la Base de Datos está en Navicat y NO tienes la contraseña?

Si Navicat tiene la conexión guardada pero no conoces la clave del servidor, tienes **4 métodos 100% funcionales y probados**:

### Método 1: Exportar a CSV desde Navicat y procesar con `tools/navicat_helper.py` (Recomendado)
Navicat puede exportar tablas a CSV sin pedir la contraseña:
1. En Navicat, haz clic derecho sobre la tabla del padrón &rarr; **Export Wizard (Asistente de Exportación)**.
2. Selecciona **CSV file (*.csv)**.
3. Elige los campos: `cedula` (o ID) y `foto` (BLOB, Base64 o ruta).
4. Guarda el archivo (ejemplo: `padron_export.csv`).
5. Corre nuestro procesador automático:
   ```bash
   python tools/navicat_helper.py csv --csv "padron_export.csv" --out "out/padron_limpio" --col "foto" --id-col "cedula" --deskew
   ```
   *Detecta automáticamente si la columna tiene Base64, Hex o rutas locales, procesa en streaming, limpia archivos temporales y genera la galería HTML.*

### Método 2: Exportar archivos BLOB directos en Navicat
1. En Navicat, abre la tabla.
2. Clic derecho en la columna BLOB &rarr; **Export Selected Blobs / Save Blobs to Files**.
3. Elige una carpeta de destino (ej: `D:\blobs_navicat`).
4. Procesa la carpeta en lote:
   ```bash
   python -m padron_crop batch --src "D:\blobs_navicat" --out "out/blobs_limpios" --workers 4 --resume
   ```

### Método 3: Transferir a SQLite Local dentro de Navicat
1. En Navicat, crea una conexión nueva a **SQLite** en un archivo de tu disco local (ej: `padron_local.db`).
2. En Navicat, usa **Data Transfer (Transferencia de Datos)** desde la conexión remota hacia tu conexión SQLite local. Como Navicat ya está conectado, no te pedirá la contraseña.
3. Luego corres el pipeline directo contra SQLite:
   ```bash
   set PADRON_DB_URL=sqlite:///padron_local.db
   python -m padron_crop sql --query-file "query.sql" --out "out/sql_limpio" --confirm padron.foto
   ```

### Método 4: Micro-API Remota (Servidor Puente)
Si alguien en el servidor remoto corre nuestro micro-servicio:
```bash
python tools/serve_api.py --host 0.0.0.0 --port 8000
```
Puedes enviar fotos desde cualquier máquina sin credenciales de base de datos:
```bash
curl -X POST http://servidor-remoto:8000/crop --data-binary @foto_con_prm.jpg -o foto_limpia.jpg
```

---

## 🌐 Despliegue en Servidor Remoto (Linux / Docker / VPS)

### En Linux / Ubuntu / Debian Remoto
```bash
chmod +x run.sh
./run.sh test                              # Verificar 110 tests
./run.sh batch /ruta/fotos /ruta/salida 8   # 8 workers en paralelo
./run.sh server                            # Inicia la API en puerto 8000
```

### Con Docker / Docker Compose (1 comando)
```bash
docker compose up -d
```
El contenedor se inicia automáticamente con OpenCV, límite seguro de RAM y el micro-servicio HTTP activo en el puerto `8000`.

---

## 🛡️ Invariantes de Seguridad y Calidad

1. **Recortar, nunca pintar**: Prohibido inpaint, rellenar o inventar pixeles. Solo recorte geométrico determinista.
2. **Face Safety Gate (Protección Facial)**: Segmentación YCrCb y umbral de barbilla para asegurar matemáticamente que el corte jamás toque la cara, cuello o barbilla. Si hay duda &rarr; va a `quarantine/`.
3. **Auto-Deskewing (Corrección de Inclinación)**: Detección Hough transform para enderezar escaneos o fotos inclinadas tomadas con celular.
4. **Protección de RAM**: Techo de decodificación de 512 MP configurable (`PADRON_MAX_PIXELS`). No se desborda la memoria.
5. **Transparencia Segura**: Imágenes PNG/WebP con canal alfa se componen sobre blanco para evitar falsas barras negras.
6. **Perfiles de Color (ICC)**: Preservación de perfiles sRGB y P3 para evitar decoloración.
7. **Tolerancia a Fallos**: Escrituras atómicas en disco; `--resume` salta sin repetir lo ya procesado si se corta la luz.

---

## 🧪 Tests Automatizados

```bash
python -m pytest -v
```
**Resultado:** `110 passed in 10.64s (100% passing)`
Cubre: D0, D1, D2, D3, Face Safety Gate, Auto-deskewing, Transparencia RGBA, decodificación Base64/Hex/BLOB de Navicat, reanudación y límites de disco.

---

## 📊 Especificación de la Línea de Comandos (CLI)

```
padron-crop inspect  --image PATH
padron-crop crop     --in PATH --out PATH [--deskew] [--aspect-ratio 3:4|1:1] [--quality 95]
padron-crop batch    --src DIR --out DIR --workers N --resume [--deskew] [--aspect-ratio R]
padron-crop sql      --query-file FILE --out DIR [--confirm tabla.columna] [--keep-blobs]
padron-crop api      --config FILE --out DIR
padron-crop gallery  --out DIR [--html archivo.html] [--limit N]
padron-crop qa       --out DIR
```
