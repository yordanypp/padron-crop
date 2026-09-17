# 🚀 GUÍA DE DESPLIEGUE Y USO EN SERVIDOR WINDOWS (10 / 11)

Esta guía explica paso a paso cómo llevar el proyecto **Padrón Crop** a un servidor o PC remota con Windows 10 o Windows 11, configurarlo en 1 solo clic y procesar millones de imágenes de manera 100% automatizada.

---

## 📥 PASO 1: Copiar el Proyecto al Servidor Remoto

Puedes mover el proyecto usando cualquiera de estas dos opciones:

### Opción A: Clonar con Git (Recomendado si hay Git instalado)
Abre la consola de Windows (`cmd` o `PowerShell`) en el servidor y ejecuta:
```cmd
git clone https://github.com/yordanypp/padron-crop.git
cd padron-crop
```

### Opción B: Copiar por Escritorio Remoto (RDP) o Archivo ZIP
1. Comprime esta carpeta en un archivo `.zip`.
2. Conéctate a tu servidor remoto por **Escritorio Remoto (RDP)**.
3. Pega el archivo `.zip` en `C:\PadrónCrop\` (o en cualquier disco con espacio, por ejemplo `D:\PadrónCrop\`).
4. Descomprímelo allí.

---

## ⚡ PASO 2: Instalación de Entorno en 1 Clic

En el servidor remoto, asegúrate de tener instalado **Python 3.10, 3.11, 3.12, 3.13 o 3.14** (marcando la casilla *"Add Python to PATH"* durante su instalación).

Luego, haz **doble clic** en:
```
instalar_servidor.bat
```
*(o ejecuta la opción `[0]` desde `ejecutar_recorte.bat`)*

**¿Qué hace este script automáticamente?**
1. Detecta tu instalación de Python.
2. Crea un entorno virtual aislado (`.venv\`).
3. Instala `numpy`, `Pillow` y `opencv-python-headless` (con aceleración C++ y detector facial de seguridad).
4. Ejecuta un autodiagnóstico del motor para certificar que todo funcione al 100%.

---

## 🖥️ PASO 3: Flujo de Trabajo Automatizado (Paso a Paso)

Para comenzar a operar, haz **doble clic** en:
```
ejecutar_recorte.bat
```
Se abrirá el **Panel de Control Interactivo**:

```text
=================================================================
     PADRÓN CROP - PANEL DE CONTROL Y PROCESAMIENTO MASIVO
=================================================================

 [0] Instalar / Reparar Entorno (.venv + Librerías en 1 Clic)
 [1] Análisis Exploratorio (EDA) de Dataset (Volumen, Barras y ETA)
 [2] Procesamiento Masivo con Checkpoints y ETA en Vivo
 [3] Asistente Navicat (Procesar CSV / Blobs sin Contraseña)
 [4] Procesar Imagen de Muestra (Prototipo 0aaa2b82... JPG)
 [5] Abrir Galería Visual Interactiva (Auditoría QA Antes / Después)
 [6] Ejecutar Suite Completa de Pruebas (129 Tests Automatizados)
 [7] Iniciar Servidor Micro-API Local (Para Integraciones / Red)
 [8] Salir
```

---

### Flujo de Operación Recomendado:

#### 1. Diagnóstico Previo (`Opción [1]`)
* Arrastra la carpeta donde están las fotos originales (por ejemplo `D:\Fotos_Padron`).
* El sistema analizará una muestra, te dirá el peso total en GB, cuántas fotos tienen el bloque PRM, cuántas están limpias y te calculará el **ETA estimado** (tiempo de finalización) para 1, 4 u 8 núcleos de CPU.

#### 2. Procesamiento Masivo (`Opción [2]`)
* Arrastra la carpeta de origen y la de destino (por ejemplo `D:\Fotos_Limpias`).
* Ingresa la cantidad de workers de CPU (ej. 4 núcleos).
* El sistema procesará las fotos a máxima velocidad mostrando una barra de progreso en vivo:
  ```text
  [████████░░░░░░░░] 52.4% | 18.2 img/s | ETA: 00h 14m 23s
  ```
* **Protección ante caídas:** El sistema guarda puntos de control (`checkpoint.json`). Si se corta la luz, se reinicia el servidor o cierras la ventana, simplemente vuelve a ejecutar la opción `[2]` y el sistema reanudará automáticamente donde quedó sin repetir ninguna foto.

#### 3. Auditoría de Calidad Visual (`Opción [5]`)
* Al terminar el lote, selecciona la opción `[5]`.
* Se abrirá automáticamente en tu navegador `gallery.html`, donde podrás inspeccionar visualmente todas las fotos antes y después, con filtros interactivos para ver las recortadas (`ok`), las limpias (`noop`) y las que fueron a cuarentena (`quarantine`).

---

## 🗄️ ¿Tienes los datos en Navicat o Base de Datos?

Si las fotos provienen de una base de datos MySQL, PostgreSQL o SQL Server:

1. En Navicat, haz clic derecho en la tabla y selecciona **Export Wizard** -> Formato **CSV**.
2. Guarda el archivo como `export_fotos.csv` (puede incluir las fotos en Base64, rutas de archivo o binarios Hex).
3. Abre `ejecutar_recorte.bat` y selecciona la **Opción `[3]` Asistente Navicat**.
4. Arrastra el archivo CSV y la carpeta de destino.
5. El sistema procesará todas las fotos directamente del CSV sin necesidad de que compartas contraseñas de base de datos ni expongas el servidor SQL.

---

## 🛡️ Seguridad y Resguardo del Sistema

* **100% Local (Privacidad Total):** Ninguna foto ni dato biométrico sale jamás a internet. Todo corre en la memoria RAM y CPU del servidor.
* **Archivos Originales Intocables (Read-Only):** El sistema nunca modifica, renombra ni sobrescribe las fotos originales. Todo el resultado se escribe en carpetas nuevas de salida.
* **Compuerta de Seguridad Facial:** Si una foto presenta ropa oscura o sombras cerca del cuello, el protector facial matemático de OpenCV calcula la posición de la barbilla e impide cualquier recorte que pueda tocar el rostro, enviándola de inmediato a `quarantine/` para revisión humana.
