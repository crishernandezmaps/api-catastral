-- ============================================================
-- CBR (Conservador de Bienes Raíces) — escrituras de compraventa
-- ============================================================

CREATE TABLE IF NOT EXISTS cbr_escrituras (
    id              SERIAL PRIMARY KEY,
    comuna_codigo   INT     NOT NULL,
    manzana         INT     NOT NULL,
    predio          INT     NOT NULL,
    fecha           DATE    NOT NULL,
    monto_pesos     BIGINT,
    monto_uf        NUMERIC(14, 2)
);

-- Indexes for query patterns
CREATE INDEX IF NOT EXISTS idx_cbr_rol
    ON cbr_escrituras (comuna_codigo, manzana, predio);

CREATE INDEX IF NOT EXISTS idx_cbr_fecha
    ON cbr_escrituras (fecha);

CREATE INDEX IF NOT EXISTS idx_cbr_comuna_fecha
    ON cbr_escrituras (comuna_codigo, fecha);

-- ============================================================
-- H3 level-8 index on catastro_actual (for spatial grouping)
-- ============================================================

ALTER TABLE catastro_actual ADD COLUMN IF NOT EXISTS h3_8 TEXT;
CREATE INDEX IF NOT EXISTS idx_catastro_h3_8 ON catastro_actual (h3_8);
