# Instrucciones para Configurar Google Search Console
## Cazador de Sueños Cigars SRL

### 1. Crear Cuenta en Google Search Console

1. Visita [Google Search Console](https://search.google.com/search-console)
2. Inicia sesión con tu cuenta de Google (recomendado usar cuenta corporativa de Cazador de Sueños Cigars SRL)
3. Haz clic en "Agregar propiedad" (Add property)

### 2. Verificar la Propiedad del Sitio

**Opción A: Verificación por archivo HTML (Recomendada)**

1. Selecciona "Prefijo de URL" e ingresa: `https://www.cazadordesuenocigars.com/`
2. Selecciona "Archivo HTML" como método de verificación
3. Descarga el archivo de verificación HTML proporcionado
4. Sube el archivo a la raíz del servidor: `/var/www/html/`
5. Haz clic en "Verificar" en Google Search Console

**Opción B: Verificación por Meta Tag**

1. Selecciona "Etiqueta HTML" como método de verificación
2. Copia la etiqueta meta proporcionada
3. Agrega la etiqueta al `<head>` de `index.html` antes de cerrar el tag
4. Haz clic en "Verificar" en Google Search Console

### 3. Configurar el Sitemap

1. En el panel izquierdo, navega a "Sitemaps"
2. En el campo "Agregar un nuevo sitemap", ingresa: `sitemap.xml`
3. Haz clic en "Enviar"
4. Verifica que el sitemap se haya procesado correctamente (puede tardar unos minutos)

### 4. Configurar Versión HTTP y HTTPS

Repite el proceso de verificación para:
- `http://www.cazadordesuenocigars.com/` (opcional, para redirecciones)
- `https://cazadordesuenocigars.com/` (sin www, opcional)
- `http://cazadordesuenocigars.com/` (opcional)

**Nota:** Selecciona `https://www.cazadordesuenocigars.com/` como la versión canónica principal.

### 5. Configurar Dominio de Propiedad (Property Set)

1. En Google Search Console, crea un "Conjunto de propiedades" (Property Set)
2. Agrega todas las versiones verificadas del dominio
3. Esto permite ver datos consolidados de todas las versiones

### 6. Configurar Google Analytics 4

**IMPORTANTE:** Reemplazar el ID placeholder en todos los archivos

1. Crea una propiedad GA4 en [Google Analytics](https://analytics.google.com)
2. Copia tu ID de medición (formato: G-XXXXXXXXXX)
3. **NOTA:** El ID ya ha sido reemplazado con G-BYRS7MGYXK en todos los archivos
4. Verifica que el ID sea correcto en los siguientes archivos:
   - `index.html` (líneas 22, 27)
   - `vitolas/el-emperador.html` (líneas 25, 30)
   - `vitolas/puro-habano.html` (líneas 25, 30)
   - `vitolas/el-exquisito.html` (líneas 25, 30)
   - `vitolas/el-rango.html` (líneas 25, 30)
   - `vitolas/ligero-007.html` (líneas 25, 30)
   - `vitolas/el-sultan.html` (líneas 25, 30)

4. Vincula GA4 con Search Console:
   - En GA4, ve a Administración > Configuración de la propiedad > Vinculación de Search Console
   - Selecciona tu propiedad de Search Console

### 7. Palabras Clave Estratégicas Implementadas

**Marca:**
- Cazador de Sueños Cigars SRL

**Ubicación/Origen:**
- Cerro Angola de Rincón de Piedra
- San José de las Matas
- Tamboril
- Valle del Cibao

**Sector/Industria:**
- Tabaco dominicano
- Maestro Tabaquero
- INTABACO
- Cigarros premium
- Puros artesanales

### 8. Monitoreo y Mantenimiento

**Revisiones Semanales:**
- Revisar "Rendimiento" para ver consultas de búsqueda y páginas principales
- Verificar "Cobertura" para detectar errores de indexación
- Revisar "Mejoras" para problemas de experiencia de usuario

**Revisiones Mensuales:**
- Analizar tendencias de tráfico
- Revisar enlaces externos
- Verificar problemas de AMP (si aplica)
- Revisar datos de dispositivos móviles vs desktop

### 9. Archivos Modificados para SEO

**Archivos HTML:**
- `index.html` - Meta description, keywords, GA4
- `vitolas/el-emperador.html` - Meta title, description, keywords, GA4
- `vitolas/puro-habano.html` - Meta title, description, keywords, GA4
- `vitolas/el-exquisito.html` - Meta title, description, keywords, GA4
- `vitolas/el-rango.html` - Meta title, description, keywords, GA4
- `vitolas/ligero-007.html` - Meta title, description, keywords, GA4
- `vitolas/el-sultan.html` - Meta title, description, keywords, GA4

**Sitemap:**
- `sitemap.xml` - Actualizado con fechas lastmod y URLs correctas

### 10. Pasos Finales

1. Sincronizar todos los archivos modificados al servidor de producción
2. Reiniciar nginx: `sudo systemctl restart nginx`
3. Verificar que el sitio sea accesible en `https://www.cazadordesuenocigars.com/`
4. Verificar que el sitemap sea accesible en `https://www.cazadordesuenocigars.com/sitemap.xml`
5. Solicitar indexación de páginas principales en Search Console
6. Monitorear los primeros datos en GA4 y Search Console

---

**Contacto de Soporte:**
- Para problemas técnicos del servidor: sandy@35.237.216.105
- Para consultas de SEO: Documentación de Google Search Console

**Fecha de implementación:** 23 de junio de 2026
