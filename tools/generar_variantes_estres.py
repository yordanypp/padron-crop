"""
Herramienta de generación de variantes de estrés para Padrón Crop.
Toma la foto real del padrón (0aaa2b82-4607-4f53-8a28-ccafa017104d.jpg) y genera
variantes realistas moviendo el bloque PRM y barras a distintos lados:
- Barra PRM arriba a la izquierda
- Barra PRM arriba al centro
- Barra PRM arriba a la derecha
- Barra PRM lateral izquierda
- Barra PRM lateral derecha
- Barra PRM inferior izquierda
- Barra PRM inferior derecha
- Barra PRM inferior centrada (original y con variaciones de grosor)
- Foto limpia (sin PRM) como control negativo
- Diferentes escalas, brillos y calidades
"""

import sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter

def generate_variants(anchor_path: Path, out_dir: Path, count: int = 50) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    orig_im = Image.open(anchor_path).convert("RGB")
    W, H = orig_im.size
    orig_arr = np.array(orig_im)

    # 1. Extraer una versión limpia de la foto (recortando la barra inferior y redimensionando al lienzo)
    # y extraer el parche del bloque PRM
    clean_crop = orig_arr[:1004, :]
    clean_im = Image.fromarray(clean_crop).resize((W, H), resample=Image.BICUBIC)
    clean_arr = np.array(clean_im)

    # Parche PRM real (con las letras blancas sobre fondo negro)
    # y=1009 a 1088, x=345 a 515
    prm_patch_img = orig_im.crop((345, 1009, 515, 1085))
    pw, ph = prm_patch_img.size

    generated_paths = []

    # Definir especificaciones de variantes
    configs = [
        # 1. Arriba con barra negra completa y PRM
        {"name": "01_prm_barra_arriba_centro", "bar_side": "top", "bar_size": 110, "patch_pos": "top_center"},
        {"name": "02_prm_barra_arriba_izquierda", "bar_side": "top", "bar_size": 120, "patch_pos": "top_left"},
        {"name": "03_prm_barra_arriba_derecha", "bar_side": "top", "bar_size": 115, "patch_pos": "top_right"},
        
        # 2. Abajo con barra negra en diferentes posiciones
        {"name": "04_prm_barra_abajo_centro_estandar", "bar_side": "bottom", "bar_size": 180, "patch_pos": "bottom_center"},
        {"name": "05_prm_barra_abajo_izquierda", "bar_side": "bottom", "bar_size": 170, "patch_pos": "bottom_left"},
        {"name": "06_prm_barra_abajo_derecha", "bar_side": "bottom", "bar_size": 175, "patch_pos": "bottom_right"},
        {"name": "07_prm_barra_abajo_delgada", "bar_side": "bottom", "bar_size": 100, "patch_pos": "bottom_center"},
        {"name": "08_prm_barra_abajo_gruesa", "bar_side": "bottom", "bar_size": 240, "patch_pos": "bottom_center"},

        # 3. Laterales con barra negra y PRM rotado/adaptado
        {"name": "09_prm_barra_izquierda_completa", "bar_side": "left", "bar_size": 140, "patch_pos": "left_center"},
        {"name": "10_prm_barra_derecha_completa", "bar_side": "right", "bar_size": 140, "patch_pos": "right_center"},
        {"name": "11_prm_barra_izquierda_abajo", "bar_side": "left", "bar_size": 130, "patch_pos": "left_bottom"},
        {"name": "12_prm_barra_derecha_arriba", "bar_side": "right", "bar_size": 130, "patch_pos": "right_top"},

        # 4. Multi-barra (ej. arriba y abajo o marco)
        {"name": "13_prm_barras_arriba_y_abajo", "bar_side": "top_bottom", "bar_size": 110, "patch_pos": "bottom_center"},
        {"name": "14_prm_marco_perimetral", "bar_side": "frame", "bar_size": 50, "patch_pos": "bottom_center"},

        # 5. Control negativo (foto limpia sin barra)
        {"name": "15_control_limpia_sin_prm", "bar_side": "none", "bar_size": 0, "patch_pos": "none"},
    ]

    # Expandir configs a 50 variantes aplicando variaciones de brillo, contraste, escala y ruido
    variant_list = []
    idx = 1
    for base in configs:
        variant_list.append({**base, "id": idx, "filter": "normal"})
        idx += 1
        if base["bar_side"] != "none":
            # Variante más oscura / scanner contrastado
            variant_list.append({**base, "name": f"{base['name']}_oscura", "id": idx, "filter": "dark"})
            idx += 1
            # Variante con más brillo / cámara
            variant_list.append({**base, "name": f"{base['name']}_brillante", "id": idx, "filter": "bright"})
            idx += 1

    # Asegurar hasta 50 variantes
    while len(variant_list) < count:
        base = configs[len(variant_list) % len(configs)]
        variant_list.append({
            **base,
            "name": f"{base['name']}_var{idx}",
            "id": idx,
            "filter": "slight_noise" if idx % 2 == 0 else "normal",
        })
        idx += 1

    variant_list = variant_list[:count]

    for v in variant_list:
        base_img = clean_im.copy()
        
        # Aplicar filtros si corresponde
        if v["filter"] == "dark":
            base_img = ImageEnhance.Brightness(base_img).enhance(0.85)
        elif v["filter"] == "bright":
            base_img = ImageEnhance.Brightness(base_img).enhance(1.15)
        elif v["filter"] == "slight_noise":
            base_img = base_img.filter(ImageFilter.SMOOTH_MORE)

        arr = np.array(base_img)
        bs = v["bar_size"]
        side = v["bar_side"]

        # Pintar barra negra según el lado
        if side == "top":
            arr[:bs, :, :] = np.random.randint(4, 15, (bs, W, 3), dtype=np.uint8)
        elif side == "bottom":
            arr[H - bs:, :, :] = np.random.randint(4, 15, (bs, W, 3), dtype=np.uint8)
        elif side == "left":
            arr[:, :bs, :] = np.random.randint(4, 15, (H, bs, 3), dtype=np.uint8)
        elif side == "right":
            arr[:, W - bs:, :] = np.random.randint(4, 15, (H, bs, 3), dtype=np.uint8)
        elif side == "top_bottom":
            arr[:bs, :, :] = np.random.randint(4, 15, (bs, W, 3), dtype=np.uint8)
            arr[H - bs:, :, :] = np.random.randint(4, 15, (bs, W, 3), dtype=np.uint8)
        elif side == "frame":
            arr[:bs, :, :] = np.random.randint(4, 15, (bs, W, 3), dtype=np.uint8)
            arr[H - bs:, :, :] = np.random.randint(4, 15, (bs, W, 3), dtype=np.uint8)
            arr[:, :bs, :] = np.random.randint(4, 15, (H, bs, 3), dtype=np.uint8)
            arr[:, W - bs:, :] = np.random.randint(4, 15, (H, bs, 3), dtype=np.uint8)

        img_with_bar = Image.fromarray(arr)

        # Pegar el parche PRM si corresponde
        pos = v["patch_pos"]
        paste_xy = None
        if pos == "top_center":
            paste_xy = ((W - pw) // 2, max(5, (bs - ph) // 2))
        elif pos == "top_left":
            paste_xy = (20, max(5, (bs - ph) // 2))
        elif pos == "top_right":
            paste_xy = (W - pw - 20, max(5, (bs - ph) // 2))
        elif pos == "bottom_center":
            paste_xy = ((W - pw) // 2, H - bs + max(5, (bs - ph) // 2))
        elif pos == "bottom_left":
            paste_xy = (20, H - bs + max(5, (bs - ph) // 2))
        elif pos == "bottom_right":
            paste_xy = (W - pw - 20, H - bs + max(5, (bs - ph) // 2))
        elif pos == "left_center":
            # Rotar parche verticalmente para barra izquierda
            rotated_patch = prm_patch_img.rotate(90, expand=True)
            rw, rh = rotated_patch.size
            paste_xy = (max(5, (bs - rw) // 2), (H - rh) // 2)
            img_with_bar.paste(rotated_patch, paste_xy)
            paste_xy = None
        elif pos == "right_center":
            rotated_patch = prm_patch_img.rotate(270, expand=True)
            rw, rh = rotated_patch.size
            paste_xy = (W - bs + max(5, (bs - rw) // 2), (H - rh) // 2)
            img_with_bar.paste(rotated_patch, paste_xy)
            paste_xy = None
        elif pos == "left_bottom":
            rotated_patch = prm_patch_img.rotate(90, expand=True)
            rw, rh = rotated_patch.size
            paste_xy = (max(5, (bs - rw) // 2), H - rh - 40)
            img_with_bar.paste(rotated_patch, paste_xy)
            paste_xy = None
        elif pos == "right_top":
            rotated_patch = prm_patch_img.rotate(270, expand=True)
            rw, rh = rotated_patch.size
            paste_xy = (W - bs + max(5, (bs - rw) // 2), 40)
            img_with_bar.paste(rotated_patch, paste_xy)
            paste_xy = None

        if paste_xy:
            img_with_bar.paste(prm_patch_img, paste_xy)

        out_file = out_dir / f"{v['name']}.jpg"
        img_with_bar.save(out_file, quality=92)
        generated_paths.append(out_file)

    print(f"[OK] Generadas {len(generated_paths)} variantes en: {out_dir}")
    return generated_paths

if __name__ == "__main__":
    anchor = Path("0aaa2b82-4607-4f53-8a28-ccafa017104d.jpg")
    dest = Path("pruebas_variantes/antes")
    generate_variants(anchor, dest, count=50)
