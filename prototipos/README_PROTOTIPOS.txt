============================================================
CARPETA DE PROTOTIPOS - AUDITORÍA VISUAL DEL RECORTE
============================================================

Esta carpeta contiene los prototipos listos para mostrar a tu supervisor o equipo:

1. 01_original_muestra.jpg
   - Imagen original de muestra con la barra negra y el texto "PRM" en la parte inferior.

2. 02_recorte_automatico_prm.jpg
   - Resultado limpio procesado por el pipeline. La barra negra y el texto PRM fueron
     eliminados recortando la imagen desde el borde exacto donde comienzan los glifos.
   - El rostro y cuello quedan 100% protegidos por el Face Safety Gate.

3. 03_recorte_formato_cedula_3x4.jpg
   - Versión adaptada automáticamente a la proporción estándar 3:4 (formato carnet/cédula).

4. 04_recorte_cuadrado_1x1.jpg
   - Versión adaptada a proporción 1:1 (ideal para sistemas web o avatares).

5. 05_visualizador_comparativo.html
   - Abre este archivo con doble clic en cualquier navegador (Chrome, Edge, Firefox).
   - Muestra la comparativa lado a lado con disenyo profesional, medidas exactas y estados.

6. Prototipos_Padron_Crop.pdf
   - Version PDF del visualizador comparativo, con el mismo disenyo oscuro del HTML.
   - Listo para enviar por WhatsApp o correo al supervisor.
   - Para regenerarlo: .venv\Scripts\python.exe tools\generar_pdf_prototipos.py

7. Prototipos_Padron_1.jpg / Prototipos_Padron_2.jpg
   - Cada pagina del PDF como imagen JPG.
   - WhatsApp NO muestra vista previa de PDFs, pero SI muestra estas fotos.
   - Manda estas 2 imagenes por WhatsApp para que el super las vea sin abrir nada.

Para procesar nuevas fotos:
- Haz doble clic en "ejecutar_recorte.bat" en la raíz del proyecto.
