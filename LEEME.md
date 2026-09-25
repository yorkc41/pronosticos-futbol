# Goleo — guía de puesta en marcha

Todo queda a tu nombre: el código en tu GitHub, la clave de la API en tu cuenta y la página en tu Cloudflare. Nada de esto cuesta dinero para empezar.

## Qué hay en esta carpeta

| Archivo | Para qué sirve |
|---|---|
| `site/index.html`, `app.js`, `styles.css` | La página pública |
| `site/admin.html` | Tu panel de administrador (tusitio/admin.html) |
| `site/config.json` | Ajustes que cambias desde el panel: ligas, aviso, pick destacado, anuncios |
| `site/data/` | Los partidos del día. Se llenan solos |
| `scripts/update.py` | El programa que trae los partidos y calcula las probabilidades |
| `.github/workflows/actualizar.yml` | Hace que el programa corra solo a las 5:07 a. m. y a las 12:07 p. m. (hora Colombia) |

## Paso 1 · GitHub (donde vive el código)

1. Crea una cuenta en github.com.
2. Arriba a la derecha: **+ → New repository**. Nombre: `goleo`. Márcalo **Private**. Crear.
3. En el repositorio vacío, pulsa **uploading an existing file** y arrastra **todo el contenido** de esta carpeta, incluida la carpeta `.github`. Pulsa **Commit changes**.

## Paso 2 · API-Football (de donde salen los datos)

1. Crea una cuenta gratis en dashboard.api-football.com y copia tu **API Key**.
2. En tu repositorio de GitHub: **Settings → Secrets and variables → Actions → New repository secret**.
   - Name: `API_FOOTBALL_KEY`
   - Secret: pega la clave.
3. Nunca pegues la clave en un chat ni en un archivo. Así nadie más la ve.

## Paso 3 · Primera actualización

1. En el repositorio: pestaña **Actions**. Si pide activarlas, acepta.
2. Elige **Actualizar datos → Run workflow**.
3. En 2 a 4 minutos debe quedar en verde. Si queda en rojo, abre el registro y mándame el texto del error.

## Paso 4 · Publicar la página (Cloudflare Pages)

1. Crea una cuenta gratis en cloudflare.com.
2. **Workers & Pages → Create → Pages → Connect to Git** y elige el repositorio `goleo`.
3. Configuración:
   - Framework preset: **None**
   - Build command: *(vacío)*
   - Build output directory: `site`
4. Pulsa **Save and Deploy**. Tu página queda en una dirección como `goleo.pages.dev`.
5. Cada vez que cambian los datos o la configuración, Cloudflare publica solo.

## Paso 5 · Tu llave del panel de administrador

1. En GitHub: foto de perfil → **Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token**.
2. Repository access: **Only select repositories → goleo**.
3. Permissions → Repository permissions:
   - **Contents**: Read and write
   - **Actions**: Read and write
4. Expiration: 1 año. Genera y copia el token.
5. Entra a `tusitio/admin.html`, escribe `tuusuario/goleo`, pega el token y pulsa **Entrar**.

Desde el panel puedes: poner el aviso, destacar el pick del día, ocultar partidos, activar o quitar ligas, pegar el código de los anuncios y pedir una actualización de datos en el momento.

## Después

- **Dominio propio** (ej. goleo.co): se compra y se conecta en Cloudflare → tu proyecto → Custom domains.
- **Visitas**: Cloudflare → Analytics & Logs → Web Analytics (gratis, sin cookies).
- **Publicidad**: con el dominio propio, algo de tráfico y la página de privacidad (ya incluida), se aplica a Google AdSense o a programas de afiliados de casas autorizadas por Coljuegos. El código que te den se pega en el panel.

## Límite de consultas

El plan gratis de API-Football tiene un tope diario de consultas. El programa gasta como máximo 45 por ejecución (90 al día) y guarda las estadísticas de cada equipo 6 días para ahorrar. Si un día hay demasiados partidos, los que no alcancen aparecen como "Sin estadísticas suficientes". Con 7 ligas activas suele alcanzar; si no, apaga una liga en el panel o pasa a un plan pago.

Si la API responde que tu plan no tiene acceso a la temporada actual, el plan gratis no alcanza para datos en vivo y habría que pasar al plan pago más barato. El registro de Actions lo mostrará.

## Probar sin clave

`python scripts/update.py --demo` genera datos de ejemplo. Sin clave configurada, la página muestra esos datos con un aviso.
