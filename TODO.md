# TODO — api.catastral.cl

Estado a 2026-05-25 tras la migración de enriquecimiento SII desde `s3://siipredios/sii_extractor/`.

---

## Pendientes con prioridad

### ✅ P1 — Duplicados intra-comuna en RM — RESUELTO 2026-05-25

**Lo que se hizo:**

1. `DELETE` de 1.130.888 filas duplicadas en 6 comunas RM conservando el `id` mínimo por rol (15.2 s):
   ```sql
   WITH dups AS (
     SELECT id, ROW_NUMBER() OVER (PARTITION BY comuna, manzana, predio ORDER BY id) AS rn
     FROM catastro_actual
     WHERE comuna IN (15108, 13101, 15103, 15160, 13135, 13134)
   )
   DELETE FROM catastro_actual WHERE id IN (SELECT id FROM dups WHERE rn > 1);
   ```
2. `ADD CONSTRAINT catastro_actual_rol_unique UNIQUE (comuna, manzana, predio)` (8.1 s) — previene regresión, y ahora el `ON CONFLICT DO NOTHING` de `import_csv.sh` sí queda protegido.
3. `ANALYZE catastro_actual` para estadísticas frescas.

**Estado post-fix:**

| Métrica | Antes | Después |
|---|---:|---:|
| Total `catastro_actual` | 10.538.227 | **9.407.339** |
| Filas duplicadas | 1.130.888 (10.73 %) | **0** |
| `/stats.total_predios` | 10.538.227 | 9.407.339 |

Las 6 comunas afectadas ahora tienen exactamente 1 fila por rol:

| Código | Comuna | Filas finales |
|---|---|---:|
| 15108 | Las Condes | 390.000 |
| 13101 | Santiago | 272.337 |
| 15103 | Providencia | 214.396 |
| 15160 | Vitacura | 111.076 |
| 13135 | Santiago Sur | 80.978 |
| 13134 | Santiago Oeste | 62.181 |

API verificada post-fix: `/predio`, `/cbr/rol`, `/comuna/{c}/predios`, `/cbr/cerca` → HTTP 200 los cuatro.

**Nota:** el `db_size_mb` de `/stats` SUBIÓ (de 17649 a 18775 MB) tras el DELETE — esperable, las filas borradas dejan dead tuples que el `VACUUM` aún pendiente (P2) reclamará.

---

### 🟡 P2 — VACUUM full no aplicado tras ETL

Tras `import_parquet_s3.py` (UPDATE masivo de 10.5M filas con +42 columnas y `geom`), Postgres queda con bloat. Intenté `VACUUM ANALYZE catastro_actual` y falló:

```
ERROR: could not resize shared memory segment "/PostgreSQL.522426970"
       to 536908064 bytes: No space left on device
```

Es `/dev/shm` (shared memory de PostgreSQL workers), no disco regular. `ANALYZE` solo sí corrió y dejó estadísticas frescas — por eso el query planner usa el nuevo índice `idx_actual_geom_geography` correctamente y `/cbr/cerca` responde en ~1 s. Falta el `VACUUM` para reclamar disco.

**Opciones, en orden de fricción:**

1. **`VACUUM (PARALLEL 0) catastro_actual;`** — sin workers paralelos, no necesita shm extra. Más lento pero corre online. Recomendado primero.
2. Ampliar `/dev/shm` del contenedor Docker que corre PG en puerto 5435 (revisar `docker-compose.yml` del proyecto `catastro/`, agregar `shm_size: 2gb`).
3. **`VACUUM FULL catastro_actual;`** — recupera todo el disco pero **bloquea la tabla** (la API responde 5xx mientras corre). Ventana de mantenimiento. Tras esto, re-ejecutar `CREATE INDEX` puede no ser necesario (`VACUUM FULL` reescribe la tabla y los índices).

Estimar primero el bloat con:
```sql
SELECT pg_size_pretty(pg_total_relation_size('catastro_actual')) AS total,
       pg_size_pretty(pg_relation_size('catastro_actual')) AS heap,
       pg_size_pretty(pg_indexes_size('catastro_actual')) AS indices;
```

---

### 🟢 P3 — Limpiar staging dir en VPS

`/tmp/sii_extractor_parquet` ocupa **1.7 GB** en el VPS (346 parquets descargados de S3 para el ETL). Disco a 72 % (104/150 GB). No urgente pero conviene limpiar:

```bash
ssh root@46.62.214.65 'rm -rf /tmp/sii_extractor_parquet'
```

Si se vuelve a correr el ETL, los parquets se vuelven a descargar (idempotente).

---

## Hallazgos documentados (no requieren acción)

### Trehuaco (8108) sin datos enriquecidos

Trehuaco no tiene carpeta en `s3://siipredios/sii_extractor/` (las otras 346 comunas sí). Sus predios siguen en `catastro_actual` con los datos del bulk SII, pero todas las columnas nuevas (`ah`, `eacs`, `csa_*`, `rav_*`, `pp_*`, `geom`, …) quedan en `NULL`. Cuando aparezca en S3, basta correr:

```bash
ssh root@46.62.214.65 'cd /opt/api_catastral && set -a; source .env.etl; set +a; .venv/bin/python3 scripts/import_parquet_s3.py 8108'
```

### `ah_valor_unitario` y stats AH en NULL para muchos predios urbanos

Estos campos vienen del sub-objeto `datosAh` del payload `getPredioNacional` del SII. Para unidades sub-allocated en condominios (estacionamientos, bodegas, departamentos sin medición independiente) el SII no calcula stats a nivel de unidad — el `ah` (código de área homogénea) sí aparece, pero `ah_valor_unitario`, `ah_mediana`, `ah_numero_muestras`, `ah_coef_variacion`, `ah_rango_superficie` no. Es comportamiento upstream del SII, no bug del ETL ni de la API.

Para esos predios, los valores AH a nivel de zona se pueden obtener consultando un predio "padre" o cualquier predio en la misma `ah` que sí tenga las stats.

### `CON_CON_5309/` en S3 duplica `CONCON_5309/`

`s3://siipredios/sii_extractor/` tiene dos carpetas distintas para Concón con contenido byte-idéntico:

```
CONCON_5309/      comuna=5309.csv (24.5 MB), comuna=5309.parquet (3.4 MB)
CON_CON_5309/     comuna=5309.csv (24.5 MB), comuna=5309.parquet (3.4 MB)
```

El ETL `import_parquet_s3.py:101` ya tiene un skip explícito (`if folder == "CON_CON_5309": continue`). Para limpiar S3, alguien con acceso a Hetzner Object Storage puede borrar la carpeta `CON_CON_5309/`.

---

## Cambios aplicados en esta sesión (audit trail)

**Código** (commit pendiente — branch `main`):

| Archivo | Cambio |
|---|---|
| `scripts/schema_sii_extra.sql` | **nuevo** — DDL con 42 `ADD COLUMN IF NOT EXISTS` + 3 índices |
| `scripts/import_parquet_s3.py` | **nuevo** — ETL S3 → Postgres (asyncpg + boto3 + pyarrow) |
| `scripts/etl_cbr.py` | reducido el diccionario manual de 56 entradas (40 con códigos obsoletos) a 6 aliases reales con códigos verificados contra `comunas_lookup` |
| `scripts/import_csv.sh` | quitado `!` final del default `DB_PASSWORD` (no coincidía con `.env` del VPS) |
| `scripts/deploy.sh` | mismo fix de `DB_PASSWORD` |
| `app/schemas/predio.py` | `Predio` extendido con 42 campos `Optional` (ah_\*, eac\*, csa_\*, rav_\*, pp_\*, valor_\*, etc.) |
| `app/routers/predios.py` | `COLS` extendido para devolver los campos nuevos |
| `app/routers/cbr.py` | quitado dead code (`if False else`), arreglado join cartesiano con `unnest($1::int[], $2::int[], $3::int[])` |
| `README.md` | sección "Enriquecimiento SII (sii_extractor)" + sección de importación |
| `TODO.md` | **nuevo** — este archivo |

**Producción:**

1. `UPDATE cbr_escrituras SET comuna_codigo=13101 WHERE comuna_codigo=14101` (83.577 filas — Santiago)
2. `UPDATE cbr_escrituras SET comuna_codigo=5309 WHERE comuna_codigo=5109` (28.908 filas — Concón)
3. `ALTER TABLE catastro_actual` con 42 columnas nuevas + 3 índices (`idx_catastro_ah`, `idx_catastro_eacs`, `idx_catastro_pp_id`)
4. `import_parquet_s3.py` corrido sobre 346 comunas (Trehuaco saltada): **10.531.819 predios enriquecidos**
5. `CREATE INDEX idx_actual_geom_geography ON catastro_actual USING gist ((geom::geography)) WHERE geom IS NOT NULL` — necesario para que `/cbr/cerca` no haga full scan
6. `ANALYZE catastro_actual` — estadísticas frescas para el planner
7. Deploy de 3 archivos modificados (`app/schemas/predio.py`, `app/routers/predios.py`, `app/routers/cbr.py`) + `systemctl restart api-catastral`

**Aliases CBR conservados en `etl_cbr.py`** (los únicos que el lookup oficial no resuelve):

| Alias CBR | Código SII | Razón |
|---|---:|---|
| `CON CON` (con espacio) | 5309 | lookup tiene "CONCON" sin espacio |
| `SANTIAGO CENTRO` | 13101 | lookup solo tiene "SANTIAGO" |
| `PUERTO NATALES` | 12101 | lookup tiene "NATALES" |
| `SAN FCO MOSTAZAL` | 6104 | lookup tiene "SAN FRANCISCO DE MOSTAZAL" |
| `SAN JOSE MAIPO` | 16303 | lookup tiene "SAN JOSE DE MAIPO" |
| `QUINTA TILCOCO` | 6117 | lookup tiene "QUINTA DE TILCOCO" |

---

## Cómo re-correr el ETL

`import_parquet_s3.py` es **idempotente** (UPDATE WHERE rol). Re-correrlo no duplica datos, solo refresca.

```bash
ssh root@46.62.214.65
cd /opt/api_catastral
set -a; source .env.etl; set +a   # carga S3_*, DB_*, STAGING_DIR
.venv/bin/python3 scripts/import_parquet_s3.py             # todas las 346 comunas, ~30-60 min
.venv/bin/python3 scripts/import_parquet_s3.py 13101 5309  # solo Santiago + Concón
.venv/bin/python3 scripts/import_parquet_s3.py --skip-download  # reusa /tmp/sii_extractor_parquet
```

El archivo `.env.etl` en VPS contiene:
```env
S3_ENDPOINT=https://nbg1.your-objectstorage.com
S3_BUCKET=siipredios
S3_ACCESS_KEY=...
S3_SECRET_KEY=...
DB_HOST=127.0.0.1
DB_PORT=5435
DB_NAME=catastro
DB_USER=catastro_app
DB_PASSWORD=Catastr0_2026_Tr3m3n
STAGING_DIR=/tmp/sii_extractor_parquet
```
