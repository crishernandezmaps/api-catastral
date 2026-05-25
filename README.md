# API Catastral Chile

API REST para consulta del catastro SII y transacciones CBR (Conservador de Bienes Raíces) de Chile. Expone **10.5 millones de predios** de las **347 comunas** del país y **3.1 millones de escrituras** de compraventa (2000–2026).

**Base URL:** `https://api.catastral.cl`  
**Documentación interactiva:** `https://api.catastral.cl/docs`

---

## Índice

1. [Arquitectura](#arquitectura)
2. [Stack técnico](#stack-técnico)
3. [Estructura del proyecto](#estructura-del-proyecto)
4. [Datos disponibles](#datos-disponibles)
5. [Endpoints — SII Catastral](#endpoints--sii-catastral)
6. [Endpoints — CBR Transacciones](#endpoints--cbr-transacciones)
7. [Esquema de respuesta](#esquema-de-respuesta)
8. [Códigos de referencia SII](#códigos-de-referencia-sii)
9. [Casos de uso](#casos-de-uso)
10. [Setup local](#setup-local)
11. [Deploy](#deploy)
12. [Importación de datos](#importación-de-datos)

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
FastAPI / Uvicorn (2 workers, puerto 8003)
    │
    ▼
asyncpg connection pool (min 5, max 20)
    │
    ▼
PostgreSQL 16 + PostGIS (Docker, puerto 5435)
    │
    ├── tabla: catastro_actual     (10.5M predios SII)
    │    índices: (comuna, manzana, predio) · dirección GIN · geom GIST · h3_8
    │
    └── tabla: cbr_escrituras      (3.1M escrituras CBR)
         índices: (comuna_codigo, manzana, predio) · fecha · comuna+fecha
```

La API es **stateless** y **read-only**: solo realiza `SELECT`. PostgreSQL responde en < 5 ms para consultas por rol.

---

## Stack técnico

| Componente | Tecnología |
|---|---|
| Framework API | FastAPI 0.115 |
| Servidor ASGI | Uvicorn 0.30 (2 workers) |
| Driver DB | asyncpg (async, sin ORM) |
| Base de datos | PostgreSQL 16 + PostGIS 3.5 (Docker) |
| Índice espacial | H3 nivel 8 (resolución ~460m radio) |
| Validación | Pydantic v2 |
| Proxy / SSL | Nginx + Cloudflare |
| Infraestructura | Hetzner VPS (8 GB RAM, Helsínki) |

---

## Estructura del proyecto

```
api_catastral/
├── app/
│   ├── main.py           # FastAPI app, CORS, lifespan (pool DB)
│   ├── config.py         # Settings via pydantic-settings + .env
│   ├── database.py       # asyncpg connection pool
│   ├── routers/
│   │   ├── predios.py    # Endpoints SII catastral
│   │   └── cbr.py        # Endpoints CBR transacciones
│   └── schemas/
│       ├── predio.py     # Modelos Pydantic SII
│       └── cbr.py        # Modelos Pydantic CBR
├── scripts/
│   ├── etl_cbr.py        # ETL: CSV escrituras CBR → cbr_escrituras.csv normalizado
│   ├── compute_h3.py     # Calcula índice H3-8 para predios con coordenadas
│   ├── schema_cbr.sql    # DDL tabla cbr_escrituras + índices + columna h3_8
│   ├── import_csv.sh     # Importación masiva del CSV SII (COPY + upsert)
│   └── nginx_api_catastral.conf
├── requirements.txt
├── .env.example
└── README.md
```

---

## Datos disponibles

### SII Catastral

**Fuente:** SII — Segundo Semestre 2025  
**Cobertura:** 347 comunas, todas las regiones  
**Total predios:** 10.538.227  
**Con coordenadas (H3):** 1.130.502 predios geocodificados

| Grupo | Campos |
|---|---|
| **Identificación** | `periodo`, `anio`, `semestre`, `comuna`, `manzana`, `predio` |
| **Rol Catastral (RC)** | `rc_direccion`, `rc_serie`, `rc_ind_aseo`, `rc_cuota_trimestral`, `rc_avaluo_total`, `rc_avaluo_exento`, `rc_anio_term_exencion`, `rc_cod_ubicacion`, `rc_cod_destino` |
| **Datos Catastrales (DC)** | `dc_direccion`, `dc_avaluo_fiscal`, `dc_contribucion_semestral`, `dc_cod_destino`, `dc_avaluo_exento`, `dc_sup_terreno`, `dc_cod_ubicacion` |
| **Predios relacionados** | `dc_bc1_*`, `dc_bc2_*` (bienes comunes), `dc_padre_*` (predio padre en condominios) |
| **Construcción** | `n_lineas_construccion`, `sup_construida_total`, `anio_construccion_min/max`, `materiales`, `calidades`, `pisos_max`, `serie` |
| **Georeferencia** | `lat`, `lon`, `h3_8` (hexágono H3 nivel 8) |

### Enriquecimiento SII (sii_extractor)

**Fuente:** `s3://siipredios/sii_extractor/{NOMBRE}_{CODIGO}/comuna={CODIGO}.parquet`  
**Origen upstream:** API JSON `getPredioNacional` del SII + capas WMS de áreas homogéneas  
**Cobertura:** 346 de 347 comunas (Trehuaco 8108 sin enriquecer)

Columnas adicionales que devuelve `/predio/{c}/{m}/{p}` además del bulk SII:

| Grupo | Columnas |
|---|---|
| **EAC** (Estudio de Avalúo Catastral) | `eacs`, `eacano`, `eacs_descripcion` |
| **AH** (Área Homogénea) — peer group de tasación | `ah`, `sector`, `ah_valor_unitario`, `ah_rango_superficie`, `ah_numero_muestras`, `ah_coef_variacion`, `ah_mediana`, `ah_eac`, `ah_eacano`, `ah_utm_x/y` |
| **CSA** (Catastro Suelo Agrícola) — equivalente AH para predios rurales | `csa_sector`, `csa_clase`, `csa_valor_unitario`, `csa_eac`, `csa_eacano`, `csa_utm_x/y` |
| **RAV** (Reavalúo No Agrícola 2022) | `rav_codigo_ah`, `rav_rango_sup`, `rav_valor_m2` (+ `_2` para predios que cruzan 2 AH) |
| **predioPublicado** — rol canónico API pública SII | `pp_id`, `pp_comuna`, `pp_manzana`, `pp_predio`, `pp_utm_x/y` |
| **Valores publicados** | `valor_total`, `valor_afecto`, `valor_exento`, `valor_comercial_clp_m2` |
| **Otros** | `direccion_sii`, `destino_descripcion`, `ubicacion`, `existe_predio`, `pol_area_m2` |
| **Polígono** | Columna `geom` (PostGIS) — no expuesta en JSON, usada por `/cbr/cerca` |

### CBR Transacciones

**Fuente:** Conservador de Bienes Raíces — Escrituras de compraventa  
**Período:** 2000–2026 (volumen significativo desde 2018)  
**Total escrituras:** 3.119.383  
**Cobertura:** 346 comunas

| Campo | Descripción |
|---|---|
| `fecha` | Fecha de la escritura |
| `monto_pesos` | Monto en pesos chilenos (cuando disponible) |
| `monto_uf` | Monto en UF (cuando disponible) |

> **Nota:** El tipo de propiedad no está en el archivo CBR original. Se obtiene cruzando con `catastro_actual` a través del rol (comuna / manzana / predio).

---

## Endpoints — SII Catastral

### `GET /predio/{comuna}/{manzana}/{predio}`

Retorna todos los datos SII del rol indicado.

```bash
curl https://api.catastral.cl/predio/15103/933/810
```

**Respuesta `200 OK`**

```json
{
  "id": 1726674,
  "periodo": "PRIMER SEMESTRE DE 2026",
  "comuna": 15103,
  "manzana": 933,
  "predio": 810,
  "rc_direccion": "SUECIA 283 BX 41 4SB",
  "rc_cod_destino": "ESTACIONAMIENTO",
  "dc_avaluo_fiscal": 5853327,
  "dc_contribucion_semestral": 31228,
  "sup_construida_total": 13.0,
  "pisos_max": 12,
  "lat": -33.423417,
  "lon": -70.607202,
  "h3_8": "88b2c55699fffff"
}
```

---

### `GET /buscar`

Búsqueda por texto en dirección dentro de una comuna.

| Parámetro | Tipo | Requerido | Descripción |
|---|---|---|---|
| `q` | string | Sí | Texto a buscar (mín. 3 caracteres) |
| `comuna` | integer | Sí | Código SII de la comuna |
| `limit` | integer | No | Máx. resultados (1–50, default 20) |

```bash
curl "https://api.catastral.cl/buscar?q=SUECIA&comuna=15103&limit=5"
```

---

### `GET /comunas`

Lista todas las comunas con su conteo de predios.

```bash
curl https://api.catastral.cl/comunas
```

---

### `GET /comuna/{codigo}/predios`

Lista paginada de predios de una comuna.

| Parámetro | Descripción |
|---|---|
| `offset` | Desplazamiento (default 0) |
| `limit` | Resultados por página (1–500, default 100) |

```bash
curl "https://api.catastral.cl/comuna/15103/predios?limit=10"
```

---

### `GET /stats`

```bash
curl https://api.catastral.cl/stats
# {"total_predios":10538227,"total_comunas":347,"periodo_actual":"PRIMER SEMESTRE DE 2026","db_size_mb":5059.0}
```

---

### `GET /health`

```bash
curl https://api.catastral.cl/health
# {"status":"ok"}
```

---

## Endpoints — CBR Transacciones

### `GET /cbr/rol/{comuna}/{manzana}/{predio}`

Historial completo de escrituras de compraventa para un rol específico.

```bash
curl https://api.catastral.cl/cbr/rol/5406/1/9
```

**Respuesta `200 OK`**

```json
{
  "comuna_codigo": 5406,
  "manzana": 1,
  "predio": 9,
  "total_transacciones": 2,
  "primera_fecha": "2019-01-21",
  "ultima_fecha": "2021-12-23",
  "ultimo_monto_uf": 4620.07,
  "ultimo_monto_pesos": 143000000,
  "escrituras": [
    { "id": 3, "fecha": "2021-12-23", "monto_pesos": 143000000, "monto_uf": 4620.07 },
    { "id": 2, "fecha": "2019-01-21", "monto_pesos": 120000000, "monto_uf": null }
  ]
}
```

**Respuesta `404`** — Sin transacciones registradas para ese rol.

---

### `GET /cbr/h3/{comuna}/{manzana}/{predio}`

Estadísticas de transacciones de propiedades en el mismo hexágono H3 nivel 8 (~460m radio), desglosadas por tipo de propiedad. El cliente decide qué tipos mostrar.

**Requiere:** que el predio tenga coordenadas (`lat`/`lon` en catastro_actual).

```bash
curl https://api.catastral.cl/cbr/h3/15108/105/21
```

**Respuesta `200 OK`**

```json
{
  "h3_index": "88b2c55689fffff",
  "radio_km": 0.46,
  "total_transacciones": 1171,
  "por_tipo": [
    {
      "destino": "HABITACIONAL",
      "total_transacciones": 142,
      "predios_distintos": 134,
      "mediana_uf": 6300.0,
      "promedio_uf": 6733.15,
      "min_uf": 154.0,
      "max_uf": 20000.0,
      "transacciones_12m": 9,
      "tendencia_pct": -14.3
    },
    {
      "destino": "ESTACIONAMIENTO",
      "total_transacciones": 883,
      "predios_distintos": 842,
      "mediana_uf": 830.0,
      "promedio_uf": 11789.38,
      "min_uf": 37.0,
      "max_uf": 9787794.0,
      "transacciones_12m": 5,
      "tendencia_pct": -26.9
    }
  ]
}
```

**Campos del desglose por tipo**

| Campo | Descripción |
|---|---|
| `destino` | Tipo de propiedad según SII (ver tabla de códigos) |
| `total_transacciones` | Total de escrituras en el hexágono para ese tipo |
| `predios_distintos` | Número de roles únicos con transacciones |
| `mediana_uf` | Mediana del precio en UF — más robusta que el promedio ante outliers |
| `promedio_uf` | Promedio del precio en UF |
| `min_uf` / `max_uf` | Rango de precios |
| `transacciones_12m` | Escrituras en los últimos 12 meses (liquidez del mercado) |
| `tendencia_pct` | % de variación del precio promedio: últimos 12m vs 12m anteriores |

**Respuesta `404`** — Sin transacciones en ese hexágono.  
**Respuesta `422`** — El predio no tiene coordenadas.

---

### `GET /cbr/cerca`

Predios con su resumen CBR dentro de un radio dado a una coordenada.

| Parámetro | Tipo | Default | Descripción |
|---|---|---|---|
| `lat` | float | — | Latitud decimal (ej: `-33.4569`) |
| `lon` | float | — | Longitud decimal (ej: `-70.6483`) |
| `radio` | integer | 500 | Radio en metros (50–5000) |
| `limit` | integer | 100 | Máx. predios a retornar (1–200) |

```bash
curl "https://api.catastral.cl/cbr/cerca?lat=-33.4569&lon=-70.6483&radio=300&limit=20"
```

**Respuesta `200 OK`** — Lista de predios ordenada por distancia a la coordenada, cada uno con:

```json
[
  {
    "comuna_codigo": 15103,
    "manzana": 933,
    "predio": 810,
    "direccion": "SUECIA 283 BX 41",
    "destino": "ESTACIONAMIENTO",
    "avaluo_fiscal": 5853327,
    "sup_construida": 13.0,
    "lat": -33.423417,
    "lon": -70.607202,
    "h3_8": "88b2c55699fffff",
    "total_transacciones": 1,
    "ultima_fecha": "2023-05-12",
    "ultimo_monto_uf": 830.0
  }
]
```

---

## Esquema de respuesta

### Valores monetarios

| Campo | Unidad | Descripción |
|---|---|---|
| `rc_cuota_trimestral` | CLP | Cuota trimestral de contribuciones (Rol de Cobro SII) |
| `dc_avaluo_fiscal` | CLP | Avalúo fiscal (Detalle Catastral SII) |
| `dc_contribucion_semestral` | CLP | Contribución semestral teórica |
| `rc_avaluo_total` | CLP | Avalúo total del Rol de Cobro |
| `monto_pesos` | CLP | Precio de escritura CBR en pesos |
| `monto_uf` | UF | Precio de escritura CBR en UF |

> **Contribución anual real** = `rc_cuota_trimestral × 4`  
> **Contribución anual estimada** = `dc_contribucion_semestral × 2`

### Superficies

En metros cuadrados (m²):

| Campo | Descripción |
|---|---|
| `dc_sup_terreno` | Superficie del terreno |
| `sup_construida_total` | Superficie construida total |

---

## Códigos de referencia SII

### Destino del predio (`rc_cod_destino` / `dc_cod_destino`)

El SII usa dos sistemas de codificación según el archivo fuente:

| Código corto | Nombre completo | Descripción |
|---|---|---|
| `H` | `HABITACIONAL` | Vivienda |
| `C` | `COMERCIO` | Comercial |
| `Z` | `ESTACIONAMIENTO` | Estacionamiento / parking |
| `L` | `BODEGA Y ALMACENAJE` | Bodega |
| `O` | `OFICINA` | Oficina |
| `I` | `INDUSTRIAL` | Industrial |
| `A` | `AGRICOLA` | Agrícola |
| `E` | `EDUCACION Y CULTURA` | Educación |
| `G` | `HOTEL, MOTEL` | Hotelería |
| `S` | `SITIO ERIAZO` | Sitio sin construir |
| `V` | — | Vivienda (variante) |
| `W` | — | Uso mixto / especial |

### Ubicación (`rc_cod_ubicacion` / `dc_cod_ubicacion`)

| Código | Descripción |
|---|---|
| `U` | Urbano |
| `R` | Rural |

### Material de construcción (`materiales`)

| Código | Descripción |
|---|---|
| `A` | Adobe o similar |
| `B` | Hormigón / albañilería |
| `C` | Madera |
| `E` | Mixto |
| `GE` | Estructura metálica |

### Serie SII (`serie`)

| Código | Descripción |
|---|---|
| `N` | No agrícola |
| `A` | Agrícola |

---

## Casos de uso

### 1. Historial de precios de un inmueble

```python
import httpx

r = httpx.get("https://api.catastral.cl/cbr/rol/15103/933/810")
data = r.json()
print(f"Última venta: {data['ultima_fecha']} — {data['ultimo_monto_uf']} UF")
for e in data["escrituras"]:
    print(f"  {e['fecha']}: {e['monto_uf']} UF")
```

### 2. Comparables de mercado por zona (H3)

```python
# Obtener precios de departamentos en el mismo hexágono que un predio
r = httpx.get("https://api.catastral.cl/cbr/h3/15103/933/810")
h3_data = r.json()

# El cliente filtra por el tipo que le interesa
habitacional = next(
    (t for t in h3_data["por_tipo"] if "HABITACIONAL" in t["destino"] or t["destino"] == "H"),
    None
)
if habitacional:
    print(f"Mediana zona: {habitacional['mediana_uf']} UF")
    print(f"Tendencia 12m: {habitacional['tendencia_pct']}%")
```

### 3. Mapa de transacciones recientes cerca de un punto

```bash
# Predios con ventas recientes en 500m alrededor de Plaza Italia
curl "https://api.catastral.cl/cbr/cerca?lat=-33.4378&lon=-70.6388&radio=500&limit=50"
```

### 4. Evaluación de inversión inmobiliaria

```python
def evaluar_propiedad(comuna, manzana, predio):
    predio_data = httpx.get(
        f"https://api.catastral.cl/predio/{comuna}/{manzana}/{predio}"
    ).json()
    cbr_data = httpx.get(
        f"https://api.catastral.cl/cbr/rol/{comuna}/{manzana}/{predio}"
    ).json()
    h3_data = httpx.get(
        f"https://api.catastral.cl/cbr/h3/{comuna}/{manzana}/{predio}"
    ).json()

    return {
        "avaluo_fiscal": predio_data["dc_avaluo_fiscal"],
        "contribucion_anual": predio_data["rc_cuota_trimestral"] * 4,
        "ultima_venta_uf": cbr_data.get("ultimo_monto_uf"),
        "mediana_zona_uf": next(
            (t["mediana_uf"] for t in h3_data["por_tipo"] if "HABITACIONAL" in t["destino"]),
            None
        ),
    }
```

### 5. Enriquecimiento de portales inmobiliarios

```javascript
// Dado un rol, mostrar avalúo + precio de mercado estimado
const [predio, h3] = await Promise.all([
  fetch(`https://api.catastral.cl/predio/${c}/${m}/${p}`).then(r => r.json()),
  fetch(`https://api.catastral.cl/cbr/h3/${c}/${m}/${p}`).then(r => r.json()),
]);

const tipo = predio.rc_cod_destino;
const comparables = h3.por_tipo.find(t => t.destino === tipo || t.destino.startsWith(tipo));
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
# Editar .env con credenciales

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
# Sincronizar código al VPS
rsync -avz --exclude='.git' --exclude='.venv' --exclude='.env' \
    ./app ./scripts ./requirements.txt \
    root@46.62.214.65:/opt/api_catastral/

# Reiniciar servicio
ssh 46.62.214.65 'systemctl restart api-catastral'
```

El servicio `api-catastral.service` (systemd) corre en `/opt/api_catastral/` sobre puerto 8003.  
**No tocar** `/var/www/catastral.cl/` — esa ruta pertenece al proyecto `catastro/` (catastral.cl).

---

## Importación de datos

### SII Catastral

```bash
bash scripts/import_csv.sh /ruta/catastro_2025_2.csv
```

El script crea tabla staging → `\COPY` masivo → upsert a `catastro_actual`. ~10–15 min para 9.4M filas.

### CBR Escrituras

```bash
# 1. Generar CSV normalizado desde el archivo fuente
python3 scripts/etl_cbr.py

# 2. Subir al VPS e importar
scp /tmp/cbr_escrituras.csv root@VPS:/tmp/
ssh VPS 'psql ... -c "\copy cbr_escrituras ... FROM /tmp/cbr_escrituras.csv CSV HEADER"'
```

### Enriquecimiento SII desde S3

```bash
# 1. Aplicar DDL una sola vez (idempotente)
psql ... -f scripts/schema_sii_extra.sql

# 2. Descargar 347 parquets desde S3 y hacer UPDATE sobre catastro_actual
#    Requiere variables S3_ACCESS_KEY, S3_SECRET_KEY, DB_*
pip install asyncpg boto3 pyarrow
python3 scripts/import_parquet_s3.py                  # todas las comunas
python3 scripts/import_parquet_s3.py 13101 5309       # solo algunas
python3 scripts/import_parquet_s3.py --skip-download  # reusa /tmp/sii_extractor_parquet
```

Tiempo estimado: 30–60 min para las 347 comunas (~5.8 GB en S3, descarga + UPDATE).

### Índice H3

Después de cargar o actualizar coordenadas en `catastro_actual`:

```bash
python3 scripts/compute_h3.py
# Calcula H3 nivel 8 para todos los predios con lat/lon (~20 min para 1.1M predios)
```

---

## Notas

- Los valores monetarios corresponden al **último período SII disponible**.
- `lat`/`lon`/`h3_8` disponibles para ~1.1M predios geocodificados (principalmente RM).
- Los endpoints CBR requieren que el rol exista en `cbr_escrituras` — no todos los predios tienen transacciones registradas.
- La mediana UF es más confiable que el promedio para comparables (el promedio se distorsiona por operaciones societarias de alto valor).
- API de solo lectura, sin autenticación — uso interno entre proyectos TREMEN.
