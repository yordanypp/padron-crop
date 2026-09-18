# Guia de despliegue y uso en servidor Windows (10 / 11)

Proyecto **Padron Crop**: limpia fotos del padron quitando el bloque negro con
texto "PRM" por recorte determinista. 100% local, nada sale a internet.

Repo publico: https://github.com/yordanypp/padron-crop

---

## PASO 1: Llevar el proyecto al servidor

Opcion A - Clonar con Git (recomendado, sin contrasena porque es publico):

```cmd
git clone https://github.com/yordanypp/padron-crop.git
cd padron-crop
```

Opcion B - ZIP por Escritorio Remoto (RDP):

1. Comprime esta carpeta en un `.zip`.
2. Conectate al servidor por RDP y pega el ZIP en `D:\PadronCrop\`
   (usa el disco con mas espacio libre).
3. Descomprimelo ahi.

Para actualizar despues a la ultima version (no toca tus fotos ni tu progreso):

```cmd
git pull origin main
```

## PASO 2: Instalacion en 1 clic (solo la primera vez)

Requisito: Python 3.10 o superior instalado con la casilla
"Add Python to PATH" marcada. Descarga: https://www.python.org/downloads/

Doble clic en:

```
instalar_servidor.bat
```

Esto crea el entorno `.venv` e instala numpy, Pillow y OpenCV solo.
Tarda 1-2 minutos. Tambien puedes usar la opcion [0] del panel.

## PASO 3: Procesar (operador, sin saber programar)

Doble clic en `ejecutar_recorte.bat`:

1. Opcion [1] EDA: arrastra la carpeta de fotos, ENTER.
   Te dice cuantas fotos hay, cuanto pesan y cuanto tardara ESA maquina.
2. Opcion [2] Procesamiento Masivo: misma carpeta, ENTER, ENTER, ENTER.
   Barra en vivo con % | fotos/seg | ETA | OK/NOOP/Q/FAIL.
3. Opcion [3] Navicat: arrastra el CSV, escribe la columna foto
   (ENTER=foto) y la columna ID (ENTER=cedula), ENTER, ENTER.

Al terminar se abre sola la galeria visual para auditar antes/desues.

## PASO 4: Recoger resultados

En la carpeta destino quedan:

- `entrega/` - solo fotos limpias `000001_<id>_crop.jpg` ordenadas por ID.
- `manifest_import.csv` - orden,id,archivo_limpio,estado,origen (abre en Excel,
  sirve para reimportar a Navicat).
- `gallery.html` - auditoria visual antes/despues.
- `audit.csv` - bitacora tecnica fila por fila.

## Si se corta la luz o la red

Vuelve a abrir `ejecutar_recorte.bat`, opcion [2], elige la misma carpeta
destino, responde **R** (reanudar). Salta lo ya hecho, repara lo que quedo
a medias, no duplica nada. Probado con apagon simulado: 0 duplicados.

## Rendimiento de referencia (4 nucleos, ~8 fotos/seg)

- 2 nucleos / PC vieja: ~12.000-15.000 fotos/hora.
- 4 nucleos: ~30.000 fotos/hora.
- 8+ nucleos / servidor: ~50.000+ fotos/hora.

La opcion [1] (EDA) te da el numero exacto de ESA maquina antes de empezar.

## Probar en 2 minutos

Opcion [4] del panel: procesa la foto de muestra y abre el comparador.
Si sale OK, la maquina esta lista.
