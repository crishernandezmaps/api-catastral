# API Catastral Chile

API REST para consulta del catastro de bienes raíces del SII (Servicio de Impuestos Internos) de Chile. Expone **10.5 millones de predios** de las **347 comunas** del país, consultables por rol SII (comuna / manzana / predio).

**Base URL:** `https://api.catastral.cl`  
**Documentación interactiva:** `https://api.catastral.cl/docs`

---

## Índice

1. [Arquitectura](#arquitectura)
2. [Stack técnico](#stack-técnico)
3. [Estructura del proyecto](#estructura-del-proyecto)
4. [Datos disponibles](#datos-disponibles)
5. [Endpoints](#endpoints)
6. [Esquema de respuesta](#esquema-de-respuesta)
7. [Códigos de referencia SII](#códigos-de-referencia-sii)
8. [Casos de uso](#casos-de-uso)
9. [Setup local](#setup-local)
10. [Deploy](#deploy)
11. [Importación de datos](#importación-de-datos)

---

## Arquitectura

```
Internet
    │
    ▼
Cloudflare (proxy + SSL)
    │
    ▼
Nginx (api.catastral.cl → 127.0.0.1:8003)
    │
    ▼
FastAPI / Uvicorn (4 workers, puerto 8003)
    │
    ▼
asyncpg connection pool (min 5, max 20)
    │
    ▼
PostgreSQL 16 + PostGIS (Docker, puerto 5435)
    │
    └── tabla: catastro_actual
         índices: (comuna, manzana, predio) · dirección GIN · geom GIST
```

La API es **stateless** y **read-only**: solo realiza `SELECT` contra la base de datos. No tiene caché adicional porque PostgreSQL con los índices responde en < 5 ms para consultas por rol.

---

## Stack técnico

| Componente | Tecnología |
|---|---|
| Framework API | FastAPI 0.115 |
| Servidor ASGI | Uvicorn 0.30 (4 workers) |
| Driver DB | asyncpg (async, sin ORM) |
| Base de datos | PostgreSQL 16 + PostGIS 3.5 (Docker) |
| Validación | Pydantic v2 |
| Proxy / SSL | Nginx + Cloudflare |
| Infraestructura | Hetzner VPS (32 vCPU, 122 GB RAM) |

---

## Estructura del proyecto

```
api_catastral/
├── app/
│   ├── main.py           # FastAPI app, CORS, lifespan (pool DB)
│   ├── config.py         # Settings via pydantic-settings + .env
│   ├── database.py       # asyncpg connection pool
│   ├── routers/
│   │   └── predios.py    # Todos los endpoints
│   └── schemas/
│       └── predio.py     # Modelos Pydantic de request/response
├── scripts/
│   ├── import_csv.sh     # Importación masiva del CSV SII (COPY + upsert)
│   ├── deploy.sh         # Deploy al VPS vía rsync + SSH
│   └── nginx_api_catastral.conf  # Config nginx para api.catastral.cl
├── requirements.txt
├── .env.example
└── README.md
```

---

## Datos disponibles

**Fuente:** Catastro de Bienes Raíces SII Chile — Segundo Semestre 2025  
**Cobertura:** 347 comunas, todas las regiones de Chile  
**Total predios:** 10.538.227  
**Actualización:** Manual, al recibir nuevo CSV del SII

### Campos disponibles por predio

| Grupo | Campos |
|---|---|
| **Identificación** | `periodo`, `anio`, `semestre`, `comuna`, `manzana`, `predio` |
| **Rol Catastral (RC)** | `rc_direccion`, `rc_serie`, `rc_ind_aseo`, `rc_cuota_trimestral`, `rc_avaluo_total`, `rc_avaluo_exento`, `rc_anio_term_exencion`, `rc_cod_ubicacion`, `rc_cod_destino` |
| **Datos Catastrales (DC)** | `dc_direccion`, `dc_avaluo_fiscal`, `dc_contribucion_semestral`, `dc_cod_destino`, `dc_avaluo_exento`, `dc_sup_terreno`, `dc_cod_ubicacion` |
| **Predios relacionados** | `dc_bc1_*`, `dc_bc2_*` (bienes comunes), `dc_padre_*` (predio padre en condominios) |
| **Construcción** | `n_lineas_construccion`, `sup_construida_total`, `anio_construccion_min`, `anio_construccion_max`, `materiales`, `calidades`, `pisos_max`, `serie` |
| **Georeferencia** | `lat`, `lon` (disponible para predios geocodificados) |

---

## Endpoints

### `GET /predio/{comuna}/{manzana}/{predio}`

Retorna todos los datos SII del rol identificado por la terna **(comuna, manzana, predio)**.

**Parámetros**

| Parámetro | Tipo | Descripción |
|---|---|---|
| `comuna` | integer | Código SII de la comuna (ej: `15103` = Providencia) |
| `manzana` | integer | Número de manzana SII |
| `predio` | integer | Número de predio SII |

**Ejemplo**

```bash
curl https://api.catastral.cl/predio/15103/933/810
```

**Respuesta `200 OK`**

```json
{
  "id": 1726674,
  "periodo": "PRIMER SEMESTRE DE 2026",
  "anio": 2025,
  "semestre": 2,
  "comuna": 15103,
  "manzana": 933,
  "predio": 810,
  "rc_direccion": "SUECIA 283 BX 41 4SB",
  "rc_serie": "N",
  "rc_avaluo_total": 5941127,
  "rc_avaluo_exento": 0,
  "rc_cod_ubicacion": "URBANA",
  "rc_cod_destino": "ESTACIONAMIENTO",
  "dc_direccion": "SUECIA 283 BX 41",
  "dc_avaluo_fiscal": 5853327,
  "dc_contribucion_semestral": 31228,
  "dc_cod_destino": "Z",
  "dc_sup_terreno": 0.0,
  "dc_bc1_comuna": 15103,
  "dc_bc1_manzana": 933,
  "dc_bc1_predio": 90708,
  "n_lineas_construccion": 1,
  "sup_construida_total": 13.0,
  "anio_construccion_min": 2022,
  "anio_construccion_max": 2022,
  "materiales": "B",
  "calidades": "4",
  "pisos_max": 12,
  "serie": "N",
  "lat": -33.423417,
  "lon": -70.607202
}
```

**Respuesta `404`**

```json
{
  "detail": "Predio no encontrado: comuna=15103, manzana=999, predio=999"
}
```

---

### `GET /buscar`

Búsqueda por texto en dirección dentro de una comuna.

**Query params**

| Parámetro | Tipo | Requerido | Descripción |
|---|---|---|---|
| `q` | string | Sí | Texto a buscar (mínimo 3 caracteres) |
| `comuna` | integer | Sí | Código SII de la comuna |
| `limit` | integer | No | Máximo resultados (1–50, default 20) |

**Ejemplo**

```bash
curl "https://api.catastral.cl/buscar?q=SUECIA&comuna=15103&limit=3"
```

**Respuesta `200 OK`** — lista de predios que coinciden con la dirección.

---

### `GET /comunas`

Lista todas las comunas disponibles con su conteo de predios.

**Ejemplo**

```bash
curl https://api.catastral.cl/comunas
```

**Respuesta `200 OK`**

```json
[
  {
    "codigo": 2201,
    "nombre": "Antofagasta",
    "region": "Antofagasta",
    "total_predios": 174730
  },
  {
    "codigo": 15103,
    "nombre": "Providencia",
    "region": "Metropolitana",
    "total_predios": 214396
  }
]
```

---

### `GET /comuna/{codigo}/predios`

Lista paginada de todos los predios de una comuna.

**Parámetros**

| Parámetro | Tipo | Descripción |
|---|---|---|
| `codigo` | integer | Código SII de la comuna |
| `offset` | integer | Desplazamiento (default 0) |
| `limit` | integer | Resultados por página (1–500, default 100) |

**Ejemplo**

```bash
curl "https://api.catastral.cl/comuna/15103/predios?limit=10&offset=0"
```

---

### `GET /stats`

Estadísticas generales de la base de datos.

**Ejemplo**

```bash
curl https://api.catastral.cl/stats
```

**Respuesta `200 OK`**

```json
{
  "total_predios": 10538227,
  "total_comunas": 347,
  "periodo_actual": "PRIMER SEMESTRE DE 2026",
  "db_size_mb": 4515.8
}
```

---

### `GET /health`

Health check del servicio.

```bash
curl https://api.catastral.cl/health
# {"status": "ok"}
```

---

## Esquema de respuesta

### Campos monetarios

Todos los valores monetarios están en **pesos chilenos (CLP)** sin decimales:

| Campo | Descripción |
|---|---|
| `rc_avaluo_total` | Avalúo total del rol catastral |
| `rc_avaluo_exento` | Monto exento de contribuciones |
| `rc_cuota_trimestral` | Cuota trimestral de contribuciones |
| `dc_avaluo_fiscal` | Avalúo fiscal asignado por el SII |
| `dc_contribucion_semestral` | Monto semestral de contribuciones (CBR) |
| `dc_avaluo_exento` | Avalúo exento en datos catastrales |

### Campos de superficie

En metros cuadrados (m²):

| Campo | Descripción |
|---|---|
| `dc_sup_terreno` | Superficie del terreno |
| `sup_construida_total` | Superficie construida total |

---

## Códigos de referencia SII

### `rc_cod_destino` / `dc_cod_destino` — Destino del predio

| Código | Descripción |
|---|---|
| `H` | Habitacional |
| `C` | Comercio |
| `L` | Bodega y almacenaje |
| `Z` | Estacionamiento |
| `A` | Agrícola |
| `E` | Especial |
| `I` | Industrial |

### `rc_cod_ubicacion` / `dc_cod_ubicacion`

| Código | Descripción |
|---|---|
| `U` | Urbano |
| `R` | Rural |

### `materiales` — Material de construcción predominante

| Código | Descripción |
|---|---|
| `A` | Adobe o similar |
| `B` | Hormigón / albañilería |
| `C` | Madera |
| `E` | Mixto |
| `K` | Otro |

### `serie` — Serie SII

| Código | Descripción |
|---|---|
| `N` | No agrícola (Serie B) |
| `A` | Agrícola (Serie A) |

---

## Casos de uso

### 1. Evaluación de inversión inmobiliaria

Obtener el avalúo fiscal y contribuciones reales de una propiedad para calcular el retorno sobre inversión:

```python
import httpx

def get_cbr_real(comuna, manzana, predio):
    r = httpx.get(f"https://api.catastral.cl/predio/{comuna}/{manzana}/{predio}")
    data = r.json()
    return {
        "avaluo_fiscal": data["dc_avaluo_fiscal"],
        "contribucion_anual": data["dc_contribucion_semestral"] * 2,
        "superficie_m2": data["sup_construida_total"],
        "destino": data["rc_cod_destino"],
    }
```

### 2. Enriquecimiento de portales inmobiliarios

Al publicar un listado de propiedad, cruzar con datos SII para mostrar información oficial:

```bash
# Buscar predios en una dirección
curl "https://api.catastral.cl/buscar?q=APOQUINDO+4500&comuna=13101&limit=5"
```

### 3. Análisis masivo por comuna

Obtener todos los predios de una comuna para análisis estadístico:

```python
import httpx

def get_all_predios_comuna(codigo_comuna):
    predios = []
    offset = 0
    while True:
        r = httpx.get(
            f"https://api.catastral.cl/comuna/{codigo_comuna}/predios",
            params={"limit": 500, "offset": offset}
        )
        batch = r.json()
        if not batch:
            break
        predios.extend(batch)
        offset += 500
    return predios
```

### 4. Validación de avalúos (catastral.cl)

Contrastar el avalúo fiscal que tiene el sistema propio con el dato oficial del SII:

```javascript
const response = await fetch(
  `https://api.catastral.cl/predio/${comuna}/${manzana}/${predio}`
);
const predio = await response.json();

console.log(`Avalúo fiscal SII: $${predio.dc_avaluo_fiscal.toLocaleString('es-CL')}`);
console.log(`CBR semestral: $${predio.dc_contribucion_semestral.toLocaleString('es-CL')}`);
```

### 5. Integración con evaluador Airbnb

Reemplazar el CBR estimado por el valor real del SII:

```python
def get_cbr_desde_api(comuna_codigo, manzana, predio):
    r = httpx.get(f"https://api.catastral.cl/predio/{comuna_codigo}/{manzana}/{predio}")
    if r.status_code == 404:
        return None  # fallback a estimación
    data = r.json()
    return {
        "cbr_anual_clp": data["dc_contribucion_semestral"] * 2,
        "avaluo_fiscal": data["dc_avaluo_fiscal"],
        "exento": data["dc_avaluo_exento"] > 0,
    }
```

---

## Setup local

```bash
git clone https://github.com/crishernandezmaps/api-catastral.git
cd api-catastral

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Editar .env con las credenciales de la base de datos

uvicorn app.main:app --reload --port 8003
```

**Variables de entorno (`.env`)**

```env
DB_HOST=127.0.0.1
DB_PORT=5435
DB_NAME=catastro
DB_USER=catastro_app
DB_PASSWORD=tu_password
DB_POOL_MIN=5
DB_POOL_MAX=20
```

---

## Deploy

```bash
./scripts/deploy.sh
```

El script sincroniza el código al VPS vía `rsync`, instala dependencias, configura el `.env` y reinicia el servicio.

Para actualizar solo el código:

```bash
rsync -avz --exclude='.git' --exclude='venv' --exclude='.env' \
    ./ root@46.62.214.65:/root/api_catastral/
ssh 46.62.214.65 "pkill -f 'uvicorn app.main' && cd /root/api_catastral && nohup venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8003 --workers 4 > /var/log/api_catastral.log 2>&1 &"
```

---

## Importación de datos

Para cargar un nuevo CSV del SII:

```bash
# En el VPS
bash /root/api_catastral/scripts/import_csv.sh /ruta/al/nuevo_catastro.csv
```

El script:
1. Crea una tabla staging `UNLOGGED` (sin WAL, máxima velocidad)
2. Ejecuta `\COPY` masivo del CSV completo
3. Hace upsert a `catastro_actual` con `ON CONFLICT DO NOTHING` (preserva datos geocodificados)
4. Elimina la tabla staging

Tiempo estimado para 9.4M filas: **~10–15 minutos** en el hardware actual.

---

## Notas

- Los valores monetarios son los del **último período disponible** en el CSV SII.
- El campo `lat`/`lon` está disponible solo para predios geocodificados por el equipo de catastral.cl (~1.1M predios de RM).
- La API es de solo lectura. No modifica datos.
- Sin autenticación por ahora — diseñada para uso interno entre proyectos TREMEN.
