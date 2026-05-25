# Guía de integración — api.catastral.cl (Python)

Para servicios backend que necesitan consultar datos del SII (catastro) o CBR (escrituras de compraventa) de Chile.

> Si necesitas explorar interactivamente: `https://api.catastral.cl/docs` (Swagger).
> La spec OpenAPI 3 está en `https://api.catastral.cl/openapi.json`.

---

## Conceptos básicos

| Concepto | Descripción |
|---|---|
| **Base URL** | `https://api.catastral.cl` |
| **Auth** | No requiere — API pública sin API key |
| **CORS** | Abierto a `*` para GET |
| **Métodos** | Solo `GET` (API read-only) |
| **Formato** | JSON, UTF-8 |
| **Rate limit** | Sin límite explícito en nginx; Cloudflare al frente puede tirar 429 si se abusa |

**Rol catastral** — la clave primaria de cualquier predio:
```
rol = (comuna, manzana, predio)
```
- `comuna` (int): código SII de la comuna (5 dígitos, ej: `13101` = Santiago centro)
- `manzana` (int): identificador interno de manzana dentro de la comuna
- `predio` (int): identificador del predio dentro de la manzana

Mismo `(manzana, predio)` puede existir en distintas comunas — la tripla completa es la única única.

---

## Setup

```bash
pip install httpx
```

Para validación de respuestas con tipos:
```bash
pip install pydantic
# Opcional: generar modelos Pydantic desde la spec OpenAPI
pip install datamodel-code-generator
datamodel-codegen --url https://api.catastral.cl/openapi.json \
                  --output catastral_models.py
```

---

## Cliente reutilizable

`httpx.Client` mantiene un connection pool — úsalo si harás múltiples llamadas, evita coste TLS por request.

```python
import httpx

class CatastralClient:
    def __init__(self, base_url="https://api.catastral.cl", timeout=30):
        self.client = httpx.Client(
            base_url=base_url,
            timeout=timeout,
            headers={"User-Agent": "mi-servicio/1.0"},
        )

    def close(self):
        self.client.close()

    def __enter__(self):  return self
    def __exit__(self, *_):  self.close()

    # ---- SII catastral ----

    def predio(self, comuna: int, manzana: int, predio: int) -> dict:
        r = self.client.get(f"/predio/{comuna}/{manzana}/{predio}")
        r.raise_for_status()
        return r.json()

    def comunas(self) -> list[dict]:
        r = self.client.get("/comunas")
        r.raise_for_status()
        return r.json()

    def predios_comuna(self, codigo: int, offset=0, limit=100) -> list[dict]:
        r = self.client.get(f"/comuna/{codigo}/predios",
                            params={"offset": offset, "limit": limit})
        r.raise_for_status()
        return r.json()

    def buscar(self, q: str, comuna: int, limit=20) -> list[dict]:
        r = self.client.get("/buscar",
                            params={"q": q, "comuna": comuna, "limit": limit})
        r.raise_for_status()
        return r.json()

    # ---- CBR transacciones ----

    def cbr_rol(self, comuna: int, manzana: int, predio: int) -> dict | None:
        """Historial de escrituras del rol. None si no hay registros."""
        r = self.client.get(f"/cbr/rol/{comuna}/{manzana}/{predio}")
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()

    def cbr_h3(self, comuna: int, manzana: int, predio: int) -> dict | None:
        """Estadísticas H3 (~460m radio) del predio. None si no hay transacciones o el predio no tiene coordenadas."""
        r = self.client.get(f"/cbr/h3/{comuna}/{manzana}/{predio}")
        if r.status_code in (404, 422):
            return None
        r.raise_for_status()
        return r.json()

    def cbr_cerca(self, lat: float, lon: float, radio=500, limit=100) -> list[dict]:
        r = self.client.get("/cbr/cerca",
                            params={"lat": lat, "lon": lon, "radio": radio, "limit": limit})
        r.raise_for_status()
        return r.json()


# Uso
with CatastralClient() as api:
    predio = api.predio(13101, 1, 3)
    print(predio["dc_direccion"], predio["dc_avaluo_fiscal"])
```

---

## Versión async

Si tu servicio ya es async (FastAPI, aiohttp, etc.), usa `AsyncClient` para no bloquear el event loop:

```python
import httpx, asyncio

class CatastralAsyncClient:
    def __init__(self, base_url="https://api.catastral.cl", timeout=30):
        self.client = httpx.AsyncClient(base_url=base_url, timeout=timeout)

    async def aclose(self):
        await self.client.aclose()

    async def predio(self, comuna, manzana, predio):
        r = await self.client.get(f"/predio/{comuna}/{manzana}/{predio}")
        r.raise_for_status()
        return r.json()

    async def cbr_rol(self, comuna, manzana, predio):
        r = await self.client.get(f"/cbr/rol/{comuna}/{manzana}/{predio}")
        if r.status_code == 404: return None
        r.raise_for_status()
        return r.json()


async def main():
    api = CatastralAsyncClient()
    # Múltiples calls en paralelo
    predio, cbr = await asyncio.gather(
        api.predio(13101, 1, 3),
        api.cbr_rol(13101, 1, 3),
    )
    await api.aclose()
    print(predio["dc_direccion"], "—", cbr["total_transacciones"], "escrituras")

asyncio.run(main())
```

---

## Endpoints y schemas

### `GET /predio/{comuna}/{manzana}/{predio}`

Ficha SII completa de un predio. **86 campos**: rol básico (`rc_*`), detalle catastral (`dc_*`), construcción (`materiales`, `pisos_max`, …), georeferencia (`lat`/`lon`/`h3_8`) y enriquecimiento SII (`ah`, `eacs`, `csa_*`, `rav_*`, `pp_*`, `valor_comercial_clp_m2`, …).

**Errores:**
- `404` — Predio no existe en `catastro_actual`.

**Ejemplo:**
```python
predio = api.predio(15103, 530, 570)

# Identificación
predio["dc_direccion"]                    # "AV NUEVA PROVIDENCIA 2170 BX 13"
predio["rc_cod_destino"]                  # "ESTACIONAMIENTO"

# Valores
predio["dc_avaluo_fiscal"]                # 6_009_561 (CLP)
predio["rc_cuota_trimestral"]             # None (no aplica para este predio)
predio["valor_comercial_clp_m2"]          # 1_528_796.0 (estimación SII)

# Enriquecimiento SII
predio["ah"]                              # "CMA035" — código de área homogénea
predio["eacs_descripcion"]                # "RAV NO AGRICOLA 2022"
predio["rav_codigo_ah"]                   # "CMA035"
predio["rav_rango_sup"]                   # "280 - 1.700 m²"

# Georeferencia
predio["lat"], predio["lon"]              # -33.42, -70.61
predio["h3_8"]                            # "88b2c55699fffff"
```

### `GET /comuna/{codigo}/predios?offset=&limit=`

Lista paginada de predios de una comuna. `limit` máx. 500.

```python
def stream_comuna(api, codigo, page_size=500):
    """Generator: itera todos los predios de una comuna sin cargarlos a memoria."""
    offset = 0
    while True:
        batch = api.predios_comuna(codigo, offset=offset, limit=page_size)
        if not batch:
            return
        yield from batch
        if len(batch) < page_size:
            return
        offset += page_size

# Uso
with CatastralClient() as api:
    for p in stream_comuna(api, 14605):  # Alhué
        print(p["dc_direccion"])
```

### `GET /comunas`

Las 347 comunas con su conteo de predios.

```python
comunas = api.comunas()
# [{"codigo": 13101, "nombre": "Santiago", "region": "Metropolitana", "total_predios": 544674}, ...]

stgo = next(c for c in comunas if c["nombre"] == "Santiago" and c["region"] == "Metropolitana")
```

### `GET /buscar?q=&comuna=&limit=`

Búsqueda por texto en `rc_direccion` (case-insensitive, `q` mín. 3 chars). **Requiere** filtrar por `comuna`. `limit` máx. 50.

```python
matches = api.buscar(q="suecia", comuna=15103, limit=10)
for m in matches:
    print(f"{m['comuna']}/{m['manzana']}/{m['predio']} — {m['rc_direccion']}")
```

### `GET /cbr/rol/{comuna}/{manzana}/{predio}`

Historial de escrituras de compraventa del rol.

**Errores:**
- `404` — Sin transacciones registradas (no es error de tu lado, simplemente no hay datos para ese rol).

```python
cbr = api.cbr_rol(13101, 1, 3)
if cbr is None:
    print("Sin escrituras")
else:
    print(f"Última venta: {cbr['ultima_fecha']} — {cbr['ultimo_monto_uf']} UF")
    for e in cbr["escrituras"]:  # ordenadas DESC por fecha
        print(f"  {e['fecha']}  ${e['monto_pesos']:,}  ({e['monto_uf']} UF)")
```

### `GET /cbr/h3/{comuna}/{manzana}/{predio}`

Estadísticas de transacciones en el hexágono H3 nivel 8 (~460m radio) del predio, desglosadas por tipo de propiedad.

**Errores:**
- `404` — Sin transacciones en ese hexágono.
- `422` — El predio no tiene coordenadas.

```python
h3 = api.cbr_h3(15103, 530, 570)
if h3:
    # Filtra el tipo que te interesa
    estacionamiento = next(
        (t for t in h3["por_tipo"] if t["destino"] == "ESTACIONAMIENTO"),
        None
    )
    if estacionamiento:
        print(f"Mediana zona: {estacionamiento['mediana_uf']} UF")
        print(f"Tendencia 12m: {estacionamiento['tendencia_pct']}%")
        print(f"Transacciones últimos 12m: {estacionamiento['transacciones_12m']}")
```

### `GET /cbr/cerca?lat=&lon=&radio=&limit=`

Predios con su resumen CBR dentro de un radio (50–5000 m) de una coordenada.

```python
predios = api.cbr_cerca(lat=-33.4378, lon=-70.6388, radio=500, limit=50)
con_ventas = [p for p in predios if p["total_transacciones"] > 0]
print(f"{len(con_ventas)}/{len(predios)} predios con ventas registradas")
```

### `GET /stats` · `GET /health`

```python
api.client.get("/stats").json()
# {"total_predios": 10538227, "total_comunas": 347, "periodo_actual": "...", "db_size_mb": ...}

api.client.get("/health").json()
# {"status": "ok"}
```

---

## Manejo de errores

```python
import httpx

try:
    predio = api.predio(13101, 1, 3)
except httpx.HTTPStatusError as e:
    if e.response.status_code == 404:
        # Predio no existe
        ...
    elif e.response.status_code == 422:
        # Parámetro inválido (Pydantic validation)
        print(e.response.json())  # detalle del error
    elif e.response.status_code >= 500:
        # Error del servidor (probablemente timeout, 504 desde Cloudflare)
        ...
except httpx.TimeoutException:
    # El default es 30s; /cbr/cerca con radio grande puede acercarse
    ...
except httpx.ConnectError:
    # La API no responde
    ...
```

| Código | Significado | Acción del cliente |
|---|---|---|
| `200` | OK | Procesar respuesta |
| `404` | Recurso no existe (predio o CBR sin datos) | Manejar como "sin datos" |
| `422` | Validación de parámetros falló | Revisar tipos y rangos enviados |
| `504` | Gateway timeout (Cloudflare) | Reintentar con backoff |
| `429` | Rate limit (Cloudflare) | Backoff exponencial |
| `5xx` | Error del servidor | Reintentar con backoff, alertar |

### Retry con backoff

`httpx` no trae retry built-in. Para tareas batch usa `tenacity`:

```python
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.HTTPStatusError)),
    reraise=True,
)
def get_predio_with_retry(api, c, m, p):
    return api.predio(c, m, p)
```

---

## Patrones comunes

### Contribución anual

El SII expone la contribución a dos niveles distintos. Cálculo:

```python
predio = api.predio(13101, 1, 3)

# Opción A — Rol de Cobro (más precisa, cuando está disponible)
if predio["rc_cuota_trimestral"]:
    contrib_anual_clp = predio["rc_cuota_trimestral"] * 4
# Opción B — Detalle Catastral (estimación teórica)
elif predio["dc_contribucion_semestral"]:
    contrib_anual_clp = predio["dc_contribucion_semestral"] * 2
else:
    contrib_anual_clp = None
```

### Evaluación de un predio (ficha + mercado)

```python
def evaluar_predio(api, c, m, p):
    predio = api.predio(c, m, p)
    cbr    = api.cbr_rol(c, m, p)         # None si sin escrituras
    h3     = api.cbr_h3(c, m, p)          # None si sin coords o sin tx zona

    destino = predio.get("rc_cod_destino") or predio.get("dc_cod_destino")

    # Mediana de zona del MISMO tipo de propiedad
    mediana_zona_uf = None
    if h3:
        match = next(
            (t for t in h3["por_tipo"]
             if t["destino"] == destino or t["destino"].startswith(destino[:1])),
            None,
        )
        if match:
            mediana_zona_uf = match["mediana_uf"]

    return {
        "comuna": c, "manzana": m, "predio": p,
        "direccion":         predio.get("dc_direccion"),
        "destino":           destino,
        "avaluo_fiscal_clp": predio.get("dc_avaluo_fiscal"),
        "valor_comercial_clp_m2": predio.get("valor_comercial_clp_m2"),
        "ah":                predio.get("ah"),
        "ultima_venta_uf":   cbr["ultimo_monto_uf"]  if cbr else None,
        "ultima_venta_fecha":cbr["ultima_fecha"]    if cbr else None,
        "mediana_zona_uf":   mediana_zona_uf,
    }
```

### Códigos de comuna canónicos (RM más relevantes)

| Código | Comuna |
|---:|---|
| 13101 | Santiago |
| 15103 | Providencia |
| 15105 | Ñuñoa |
| 15108 | Las Condes |
| 15128 | La Florida |
| 15151 | Macul |
| 15160 | Vitacura |
| 15161 | Lo Barnechea |
| 16110 | La Cisterna |
| 16401 | San Bernardo |
| 5309  | Concón (Región V) |

Para la lista completa: `api.comunas()`.

---

## Códigos de referencia SII

### Destino (`rc_cod_destino` / `dc_cod_destino`)

Dos sistemas conviven (depende del archivo fuente):

| Código corto | Nombre completo | |
|---|---|---|
| `H` / `V` | `HABITACIONAL` | Vivienda |
| `C` | `COMERCIO` | |
| `Z` | `ESTACIONAMIENTO` | |
| `L` | `BODEGA Y ALMACENAJE` | |
| `O` | `OFICINA` | |
| `I` | `INDUSTRIAL` | |
| `A` | `AGRICOLA` | |
| `E` | `EDUCACION Y CULTURA` | |
| `G` | `HOTEL, MOTEL` | |
| `S` | `SITIO ERIAZO` | |

### Ubicación (`rc_cod_ubicacion` / `dc_cod_ubicacion`)

| Código | |
|---|---|
| `U` | Urbano |
| `R` | Rural |

### Material (`materiales`)

| Código | |
|---|---|
| `A` | Adobe o similar |
| `B` | Hormigón / albañilería |
| `C` | Madera |
| `E` | Mixto |
| `GE` | Estructura metálica |

---

## Recomendaciones de producción

1. **Reutiliza el cliente** (`httpx.Client` / `AsyncClient`). Crear uno por request es costoso por TLS handshake.
2. **Cachea** comunas y comunas-stats — son datos casi estáticos. Para una `(comuna, manzana, predio)` que vas a leer varias veces, cachea también.
3. **Para batch**: limita concurrencia a ~20 requests paralelos. La API tolera más pero conviene ser cortés.
4. **Logueá** todas las respuestas 4xx/5xx con el rol consultado — facilita debugging cuando algo falle río arriba.
5. **`User-Agent`** identificable (`mi-servicio/version`) para que el responsable de la API pueda contactarte si tu cliente causa algún problema.
6. **No** dependas de campos enriquecidos como obligatorios — Trehuaco (8108) y algunos predios en condominios tienen `ah`, `eacs`, `rav_*` en NULL. Trata todos los campos enriquecidos como opcionales.

---

## Generar modelos Pydantic tipados

Si quieres validación de tipos sobre las respuestas (recomendado para servicios serios):

```bash
pip install datamodel-code-generator
datamodel-codegen \
    --url https://api.catastral.cl/openapi.json \
    --output catastral_models.py \
    --target-python-version 3.11 \
    --use-standard-collections \
    --use-union-operator
```

Luego:

```python
from catastral_models import Predio, RolTransacciones

predio = Predio(**api.predio(13101, 1, 3))
print(predio.dc_avaluo_fiscal)  # int tipado, no dict["dc_avaluo_fiscal"]
```

---

## Contacto y soporte

Issues técnicos o requests de campos adicionales: abrir issue en el repo del proyecto o contactar a `cris@tremen.tech`.
