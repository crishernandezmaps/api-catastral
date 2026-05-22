#!/bin/bash
# =============================================================================
# import_csv.sh — Importa el CSV SII completo a catastro_actual
#
# Uso: ./scripts/import_csv.sh /ruta/al/catastro_2025_2.csv
#
# El script:
#  1. Crea tabla temporal con el esquema exacto del CSV
#  2. COPY masivo del CSV a la tabla temporal (rápido)
#  3. Upsert a catastro_actual (INSERT ... ON CONFLICT DO NOTHING)
#  4. Limpia la tabla temporal
# =============================================================================

set -euo pipefail

CSV_PATH="${1:-/root/carto_predios/catastro_2025_2.csv}"
DB_HOST="${DB_HOST:-127.0.0.1}"
DB_PORT="${DB_PORT:-5435}"
DB_NAME="${DB_NAME:-catastro}"
DB_USER="${DB_USER:-catastro_app}"
DB_PASSWORD="${DB_PASSWORD:-Catastr0_2026_Tr3m3n!}"

export PGPASSWORD="$DB_PASSWORD"
PSQL="psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME"

echo "[$(date)] Iniciando importación de $CSV_PATH"
TOTAL=$(wc -l < "$CSV_PATH")
echo "[$(date)] Filas en CSV: $((TOTAL - 1))"

# 1. Crear tabla staging
echo "[$(date)] Creando tabla staging..."
$PSQL <<'SQL'
DROP TABLE IF EXISTS _import_staging;
CREATE UNLOGGED TABLE _import_staging (
    periodo            text,
    anio               smallint,
    semestre           smallint,
    comuna             integer,
    manzana            integer,
    predio             integer,
    rc_direccion       text,
    rc_serie           text,
    rc_ind_aseo        text,
    rc_cuota_trimestral bigint,
    rc_avaluo_total    bigint,
    rc_avaluo_exento   bigint,
    rc_anio_term_exencion smallint,
    rc_cod_ubicacion   text,
    rc_cod_destino     text,
    dc_direccion       text,
    dc_avaluo_fiscal   bigint,
    dc_contribucion_semestral bigint,
    dc_cod_destino     text,
    dc_avaluo_exento   bigint,
    dc_sup_terreno     numeric(12,2),
    dc_cod_ubicacion   text,
    dc_bc1_comuna      integer,
    dc_bc1_manzana     integer,
    dc_bc1_predio      integer,
    dc_bc2_comuna      integer,
    dc_bc2_manzana     integer,
    dc_bc2_predio      integer,
    dc_padre_comuna    integer,
    dc_padre_manzana   integer,
    dc_padre_predio    integer,
    n_lineas_construccion smallint,
    sup_construida_total numeric(12,2),
    anio_construccion_min smallint,
    anio_construccion_max smallint,
    materiales         text,
    calidades          text,
    pisos_max          smallint,
    serie              text
);
SQL

# 2. COPY masivo (el más rápido posible)
echo "[$(date)] Cargando CSV a staging (COPY)..."
$PSQL -c "\COPY _import_staging FROM '$CSV_PATH' CSV HEADER NULL ''"

echo "[$(date)] Staging cargado. Iniciando upsert a catastro_actual..."

# 3. Upsert: insert solo los que no existen (por rol)
$PSQL <<'SQL'
INSERT INTO catastro_actual (
    periodo, anio, semestre,
    comuna, manzana, predio,
    rc_direccion, rc_serie, rc_ind_aseo,
    rc_cuota_trimestral, rc_avaluo_total, rc_avaluo_exento,
    rc_anio_term_exencion, rc_cod_ubicacion, rc_cod_destino,
    dc_direccion, dc_avaluo_fiscal, dc_contribucion_semestral,
    dc_cod_destino, dc_avaluo_exento, dc_sup_terreno, dc_cod_ubicacion,
    dc_bc1_comuna, dc_bc1_manzana, dc_bc1_predio,
    dc_bc2_comuna, dc_bc2_manzana, dc_bc2_predio,
    dc_padre_comuna, dc_padre_manzana, dc_padre_predio,
    n_lineas_construccion, sup_construida_total,
    anio_construccion_min, anio_construccion_max,
    materiales, calidades, pisos_max, serie
)
SELECT
    periodo, anio, semestre,
    comuna, manzana, predio,
    NULLIF(rc_direccion, ''), NULLIF(rc_serie, ''), NULLIF(rc_ind_aseo, ''),
    NULLIF(rc_cuota_trimestral::text, '')::bigint,
    NULLIF(rc_avaluo_total::text, '')::bigint,
    NULLIF(rc_avaluo_exento::text, '')::bigint,
    NULLIF(rc_anio_term_exencion::text, '')::smallint,
    NULLIF(rc_cod_ubicacion, ''), NULLIF(rc_cod_destino, ''),
    NULLIF(dc_direccion, ''),
    NULLIF(dc_avaluo_fiscal::text, '')::bigint,
    NULLIF(dc_contribucion_semestral::text, '')::bigint,
    NULLIF(dc_cod_destino, ''),
    NULLIF(dc_avaluo_exento::text, '')::bigint,
    NULLIF(dc_sup_terreno::text, '')::numeric,
    NULLIF(dc_cod_ubicacion, ''),
    NULLIF(dc_bc1_comuna::text, '')::integer,
    NULLIF(dc_bc1_manzana::text, '')::integer,
    NULLIF(dc_bc1_predio::text, '')::integer,
    NULLIF(dc_bc2_comuna::text, '')::integer,
    NULLIF(dc_bc2_manzana::text, '')::integer,
    NULLIF(dc_bc2_predio::text, '')::integer,
    NULLIF(dc_padre_comuna::text, '')::integer,
    NULLIF(dc_padre_manzana::text, '')::integer,
    NULLIF(dc_padre_predio::text, '')::integer,
    NULLIF(n_lineas_construccion::text, '')::smallint,
    NULLIF(sup_construida_total::text, '')::numeric,
    NULLIF(anio_construccion_min::text, '')::smallint,
    NULLIF(anio_construccion_max::text, '')::smallint,
    NULLIF(materiales, ''), NULLIF(calidades, ''),
    NULLIF(pisos_max::text, '')::smallint,
    NULLIF(serie, '')
FROM _import_staging
ON CONFLICT DO NOTHING;
SQL

echo "[$(date)] Upsert completado."

# 4. Limpiar staging
$PSQL -c "DROP TABLE IF EXISTS _import_staging;"

echo "[$(date)] Verificando conteo final..."
$PSQL -c "SELECT COUNT(*) AS total_predios, COUNT(DISTINCT comuna) AS comunas FROM catastro_actual;"

echo "[$(date)] Importacion completada."
