-- ============================================================
-- Columnas enriquecidas SII (sii_extractor en S3)
-- Fuente: s3://siipredios/sii_extractor/{NOMBRE}_{CODIGO}/comuna={CODIGO}.parquet
-- ============================================================

-- EAC (Estudio de Avalúo Catastral)
ALTER TABLE catastro_actual ADD COLUMN IF NOT EXISTS eacs              INTEGER;
ALTER TABLE catastro_actual ADD COLUMN IF NOT EXISTS eacano            INTEGER;
ALTER TABLE catastro_actual ADD COLUMN IF NOT EXISTS eacs_descripcion  TEXT;

-- Predio publicado (rol canónico en API pública del SII)
ALTER TABLE catastro_actual ADD COLUMN IF NOT EXISTS pp_id             TEXT;
ALTER TABLE catastro_actual ADD COLUMN IF NOT EXISTS pp_comuna         INTEGER;
ALTER TABLE catastro_actual ADD COLUMN IF NOT EXISTS pp_manzana        INTEGER;
ALTER TABLE catastro_actual ADD COLUMN IF NOT EXISTS pp_predio         INTEGER;
ALTER TABLE catastro_actual ADD COLUMN IF NOT EXISTS pp_utm_x          DOUBLE PRECISION;
ALTER TABLE catastro_actual ADD COLUMN IF NOT EXISTS pp_utm_y          DOUBLE PRECISION;

-- Metadatos SII enriquecidos (de la API getPredioNacional)
ALTER TABLE catastro_actual ADD COLUMN IF NOT EXISTS direccion_sii         TEXT;
ALTER TABLE catastro_actual ADD COLUMN IF NOT EXISTS destino_descripcion   TEXT;
ALTER TABLE catastro_actual ADD COLUMN IF NOT EXISTS ubicacion             TEXT;
ALTER TABLE catastro_actual ADD COLUMN IF NOT EXISTS existe_predio         BOOLEAN;

-- Valores publicados (paralelos a rc_*)
ALTER TABLE catastro_actual ADD COLUMN IF NOT EXISTS valor_total            BIGINT;
ALTER TABLE catastro_actual ADD COLUMN IF NOT EXISTS valor_afecto           BIGINT;
ALTER TABLE catastro_actual ADD COLUMN IF NOT EXISTS valor_exento           BIGINT;
ALTER TABLE catastro_actual ADD COLUMN IF NOT EXISTS valor_comercial_clp_m2 NUMERIC(14,2);

-- Área Homogénea (AH) — peer group de tasación
ALTER TABLE catastro_actual ADD COLUMN IF NOT EXISTS ah                    TEXT;
ALTER TABLE catastro_actual ADD COLUMN IF NOT EXISTS sector                TEXT;
ALTER TABLE catastro_actual ADD COLUMN IF NOT EXISTS ah_valor_unitario     NUMERIC(14,2);
ALTER TABLE catastro_actual ADD COLUMN IF NOT EXISTS ah_rango_superficie   TEXT;
ALTER TABLE catastro_actual ADD COLUMN IF NOT EXISTS ah_numero_muestras    INTEGER;
ALTER TABLE catastro_actual ADD COLUMN IF NOT EXISTS ah_coef_variacion     NUMERIC(10,4);
ALTER TABLE catastro_actual ADD COLUMN IF NOT EXISTS ah_mediana            NUMERIC(14,2);
ALTER TABLE catastro_actual ADD COLUMN IF NOT EXISTS ah_eac                INTEGER;
ALTER TABLE catastro_actual ADD COLUMN IF NOT EXISTS ah_eacano             INTEGER;
ALTER TABLE catastro_actual ADD COLUMN IF NOT EXISTS ah_utm_x              DOUBLE PRECISION;
ALTER TABLE catastro_actual ADD COLUMN IF NOT EXISTS ah_utm_y              DOUBLE PRECISION;

-- CSA (Catastro de Suelo Agrícola) — equivalente AH para predios rurales
ALTER TABLE catastro_actual ADD COLUMN IF NOT EXISTS csa_sector            TEXT;
ALTER TABLE catastro_actual ADD COLUMN IF NOT EXISTS csa_clase             TEXT;
ALTER TABLE catastro_actual ADD COLUMN IF NOT EXISTS csa_valor_unitario    NUMERIC(14,2);
ALTER TABLE catastro_actual ADD COLUMN IF NOT EXISTS csa_utm_x             DOUBLE PRECISION;
ALTER TABLE catastro_actual ADD COLUMN IF NOT EXISTS csa_utm_y             DOUBLE PRECISION;
ALTER TABLE catastro_actual ADD COLUMN IF NOT EXISTS csa_eac               INTEGER;
ALTER TABLE catastro_actual ADD COLUMN IF NOT EXISTS csa_eacano            INTEGER;

-- RAV (Reavalúo No Agrícola 2022) — AH del último reavalúo + variante para predios que cruzan 2 AH
ALTER TABLE catastro_actual ADD COLUMN IF NOT EXISTS rav_codigo_ah         TEXT;
ALTER TABLE catastro_actual ADD COLUMN IF NOT EXISTS rav_rango_sup         TEXT;
ALTER TABLE catastro_actual ADD COLUMN IF NOT EXISTS rav_valor_m2          NUMERIC(14,2);
ALTER TABLE catastro_actual ADD COLUMN IF NOT EXISTS rav_codigo_ah_2       TEXT;
ALTER TABLE catastro_actual ADD COLUMN IF NOT EXISTS rav_rango_sup_2       TEXT;
ALTER TABLE catastro_actual ADD COLUMN IF NOT EXISTS rav_valor_m2_2        NUMERIC(14,2);

-- Polígono del predio (vectorización SII)
ALTER TABLE catastro_actual ADD COLUMN IF NOT EXISTS pol_area_m2           NUMERIC(14,2);
-- geom (geometry, 4326) ya existe en schema base; se actualiza desde parquet vía ST_GeomFromWKB

-- Índices de consulta
CREATE INDEX IF NOT EXISTS idx_catastro_ah    ON catastro_actual (ah)    WHERE ah IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_catastro_eacs  ON catastro_actual (eacs)  WHERE eacs IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_catastro_pp_id ON catastro_actual (pp_id) WHERE pp_id IS NOT NULL;
