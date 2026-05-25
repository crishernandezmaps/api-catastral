#!/usr/bin/env python3
"""
import_parquet_s3.py — Enriquece catastro_actual con las cols del sii_extractor (S3).

Descarga los parquets de s3://siipredios/sii_extractor/{NOMBRE}_{CODIGO}/comuna={CODIGO}.parquet,
los carga en una tabla staging y hace UPDATE sobre catastro_actual mateando por
(comuna, manzana, predio). No toca rc_*, dc_*, lat, lon, h3_8 — esas siguen viniendo
del CSV bulk (import_csv.sh).

Uso:
    pip install asyncpg boto3 pyarrow
    python3 scripts/import_parquet_s3.py                  # todas las comunas
    python3 scripts/import_parquet_s3.py 5309 13101       # solo estas
    python3 scripts/import_parquet_s3.py --skip-download  # asume parquets ya en STAGING_DIR

Requiere variables de entorno (o .env): S3_ACCESS_KEY, S3_SECRET_KEY, DB_*.
"""

import asyncio
import os
import sys
from pathlib import Path

import asyncpg
import boto3
import pyarrow.parquet as pq

S3_ENDPOINT  = os.environ.get("S3_ENDPOINT", "https://nbg1.your-objectstorage.com")
S3_BUCKET    = os.environ.get("S3_BUCKET",   "siipredios")
S3_PREFIX    = "sii_extractor"
S3_ACCESS    = os.environ["S3_ACCESS_KEY"]
S3_SECRET    = os.environ["S3_SECRET_KEY"]
STAGING_DIR  = Path(os.environ.get("STAGING_DIR", "/tmp/sii_extractor_parquet"))

DB_DSN = (
    f"postgresql://{os.environ.get('DB_USER','catastro_app')}:"
    f"{os.environ['DB_PASSWORD']}@"
    f"{os.environ.get('DB_HOST','127.0.0.1')}:"
    f"{os.environ.get('DB_PORT','5435')}/"
    f"{os.environ.get('DB_NAME','catastro')}"
)

# (parquet_col, db_col, parser)  —  geometry y comuna/manzana/predio se manejan aparte
RAV_PFX = "cap__áreas_homogéneas_rav_no_agrícola_2022__"


def parse_int(s):
    if s in (None, "", "nan", "NaN"): return None
    try: return int(float(s))
    except (TypeError, ValueError): return None


def parse_float(s):
    if s in (None, "", "nan", "NaN"): return None
    try: return float(s)
    except (TypeError, ValueError): return None


def parse_bool(s):
    v = parse_float(s)
    return None if v is None else (v != 0)


def parse_text(s):
    if s in (None, ""): return None
    return str(s).strip() or None


COLUMN_MAP = [
    # (parquet_col,                                  db_col,                 parser,      sql_type)
    ("eacs",                                         "eacs",                 parse_int,   "INTEGER"),
    ("eacano",                                       "eacano",               parse_int,   "INTEGER"),
    ("eacsDescripcion",                              "eacs_descripcion",     parse_text,  "TEXT"),
    ("direccion_sii",                                "direccion_sii",        parse_text,  "TEXT"),
    ("destinoDescripcion",                           "destino_descripcion",  parse_text,  "TEXT"),
    ("ubicacion",                                    "ubicacion",            parse_text,  "TEXT"),
    ("existePredio",                                 "existe_predio",        parse_bool,  "BOOLEAN"),
    ("valorTotal",                                   "valor_total",          parse_int,   "BIGINT"),
    ("valorAfecto",                                  "valor_afecto",         parse_int,   "BIGINT"),
    ("valorExento",                                  "valor_exento",         parse_int,   "BIGINT"),
    ("valorComercial_clp_m2",                        "valor_comercial_clp_m2", parse_float, "NUMERIC"),
    ("ah",                                           "ah",                   parse_text,  "TEXT"),
    ("sector",                                       "sector",               parse_text,  "TEXT"),
    ("ah_valorUnitario",                             "ah_valor_unitario",    parse_float, "NUMERIC"),
    ("ah_rangoSuperficie",                           "ah_rango_superficie",  parse_text,  "TEXT"),
    ("ah_numeroMuestras",                            "ah_numero_muestras",   parse_int,   "INTEGER"),
    ("ah_coefVariacion",                             "ah_coef_variacion",    parse_float, "NUMERIC"),
    ("ah_mediana",                                   "ah_mediana",           parse_float, "NUMERIC"),
    ("ah_eac",                                       "ah_eac",               parse_int,   "INTEGER"),
    ("ah_eacano",                                    "ah_eacano",            parse_int,   "INTEGER"),
    ("ah_utm_x",                                     "ah_utm_x",             parse_float, "DOUBLE PRECISION"),
    ("ah_utm_y",                                     "ah_utm_y",             parse_float, "DOUBLE PRECISION"),
    ("predioPublicado_id",                           "pp_id",                parse_text,  "TEXT"),
    ("predioPublicado_comuna",                       "pp_comuna",            parse_int,   "INTEGER"),
    ("predioPublicado_manzana",                      "pp_manzana",           parse_int,   "INTEGER"),
    ("predioPublicado_predio",                       "pp_predio",            parse_int,   "INTEGER"),
    ("predioPublicado_utm_x",                        "pp_utm_x",             parse_float, "DOUBLE PRECISION"),
    ("predioPublicado_utm_y",                        "pp_utm_y",             parse_float, "DOUBLE PRECISION"),
    ("csa_sector",                                   "csa_sector",           parse_text,  "TEXT"),
    ("csa_clase",                                    "csa_clase",            parse_text,  "TEXT"),
    ("csa_valorUnitario",                            "csa_valor_unitario",   parse_float, "NUMERIC"),
    ("csa_utm_x",                                    "csa_utm_x",            parse_float, "DOUBLE PRECISION"),
    ("csa_utm_y",                                    "csa_utm_y",            parse_float, "DOUBLE PRECISION"),
    ("csa_eac",                                      "csa_eac",              parse_int,   "INTEGER"),
    ("csa_eacano",                                   "csa_eacano",           parse_int,   "INTEGER"),
    (f"{RAV_PFX}código_área_homogénea",              "rav_codigo_ah",        parse_text,  "TEXT"),
    (f"{RAV_PFX}rango_superficie_predial_en_m²",     "rav_rango_sup",        parse_text,  "TEXT"),
    (f"{RAV_PFX}valor_m²_de_terreno",                "rav_valor_m2",         parse_float, "NUMERIC"),
    (f"{RAV_PFX}código_área_homogénea__2",           "rav_codigo_ah_2",      parse_text,  "TEXT"),
    (f"{RAV_PFX}rango_superficie_predial_en_m²__2",  "rav_rango_sup_2",      parse_text,  "TEXT"),
    (f"{RAV_PFX}valor_m²_de_terreno__2",             "rav_valor_m2_2",       parse_float, "NUMERIC"),
    ("pol_area_m2",                                  "pol_area_m2",          parse_float, "NUMERIC"),
]

PQ_COLS = [c for c, _, _, _ in COLUMN_MAP]
DB_COLS = [c for _, c, _, _ in COLUMN_MAP]
PARSERS = [p for _, _, p, _ in COLUMN_MAP]

STAGING_DDL = f"""
DROP TABLE IF EXISTS _import_extra_staging;
CREATE UNLOGGED TABLE _import_extra_staging (
    comuna    INTEGER NOT NULL,
    manzana   INTEGER NOT NULL,
    predio    INTEGER NOT NULL,
    {",".join(f"{c} {t}" for _, c, _, t in COLUMN_MAP)},
    geom_wkb  BYTEA
);
CREATE INDEX ON _import_extra_staging (comuna, manzana, predio);
"""

UPDATE_SQL = f"""
UPDATE catastro_actual ca SET
    {", ".join(f"{c} = s.{c}" for c in DB_COLS)},
    geom = CASE WHEN s.geom_wkb IS NOT NULL
                THEN ST_SetSRID(ST_GeomFromWKB(s.geom_wkb), 4326)
                ELSE ca.geom END
FROM _import_extra_staging s
WHERE ca.comuna = s.comuna AND ca.manzana = s.manzana AND ca.predio = s.predio
"""


def get_s3():
    return boto3.client(
        "s3",
        endpoint_url=S3_ENDPOINT,
        aws_access_key_id=S3_ACCESS,
        aws_secret_access_key=S3_SECRET,
        region_name="eu-central-1",
    )


def list_communes(s3):
    """Lista carpetas {NOMBRE}_{CODIGO}/ en sii_extractor/. Skip duplicado CON_CON_5309."""
    seen_codes = set()
    out = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=f"{S3_PREFIX}/", Delimiter="/"):
        for p in page.get("CommonPrefixes", []):
            folder = p["Prefix"].rstrip("/").split("/")[-1]
            name, _, code = folder.rpartition("_")
            if not code.isdigit():
                continue
            code = int(code)
            # CON_CON_5309 duplica CONCON_5309 (mismo contenido). Quedarse con CONCON.
            if folder == "CON_CON_5309":
                continue
            if code in seen_codes:
                print(f"  ⚠ duplicado en S3 ignorado: {folder}")
                continue
            seen_codes.add(code)
            out.append((code, folder))
    return sorted(out)


def download_parquet(s3, code, folder):
    local = STAGING_DIR / f"comuna={code}.parquet"
    if local.exists():
        return local
    key = f"{S3_PREFIX}/{folder}/comuna={code}.parquet"
    s3.download_file(S3_BUCKET, key, str(local))
    return local


def parquet_to_records(parquet_path, code):
    """Lee el parquet y emite tuplas listas para COPY."""
    t = pq.read_table(parquet_path)
    cols = set(t.column_names)
    # Faltantes en este parquet → arrays de None
    missing = [c for c in PQ_COLS if c not in cols]
    has_geometry = "geometry" in cols
    if missing:
        print(f"  cols ausentes ({len(missing)}): {missing[:5]}{'...' if len(missing)>5 else ''}")

    records = []
    n_total = n_kept = n_no_geom = 0
    for batch in t.to_batches(max_chunksize=10000):
        d = {c: batch[c].to_pylist() if c in cols else [None]*batch.num_rows for c in PQ_COLS}
        geom = batch["geometry"].to_pylist() if has_geometry else [None]*batch.num_rows
        com  = batch["comuna"].to_pylist()
        man  = batch["manzana"].to_pylist()
        pre  = batch["predio"].to_pylist()
        for i in range(batch.num_rows):
            n_total += 1
            c = parse_int(com[i]); m = parse_int(man[i]); p = parse_int(pre[i])
            if c is None or m is None or p is None:
                continue
            # Sanity: la comuna del parquet debe coincidir con la carpeta
            if c != code:
                continue
            row = [c, m, p]
            for j, parser in enumerate(PARSERS):
                row.append(parser(d[PQ_COLS[j]][i]))
            g = geom[i]
            if g is None:
                n_no_geom += 1
            row.append(g)
            records.append(tuple(row))
            n_kept += 1
    return records, n_total, n_kept, n_no_geom


async def process_commune(conn, parquet_path, code):
    records, n_total, n_kept, n_no_geom = parquet_to_records(parquet_path, code)
    if not records:
        print(f"  {code}: 0 filas válidas")
        return 0

    await conn.execute("TRUNCATE _import_extra_staging")
    await conn.copy_records_to_table(
        "_import_extra_staging",
        records=records,
        columns=["comuna", "manzana", "predio", *DB_COLS, "geom_wkb"],
    )
    res = await conn.execute(UPDATE_SQL)
    # res = "UPDATE N"
    n_updated = int(res.split()[1]) if res.startswith("UPDATE") else 0
    print(f"  {code}: parquet={n_total:>7,}  staging={n_kept:>7,}  "
          f"sin_geom={n_no_geom:>5,}  updated={n_updated:>7,}")
    return n_updated


async def main():
    args = [a for a in sys.argv[1:] if a != "--skip-download"]
    skip_download = "--skip-download" in sys.argv
    only_codes = {int(a) for a in args if a.isdigit()}

    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    s3 = get_s3()
    communes = list_communes(s3)
    if only_codes:
        communes = [(c, f) for c, f in communes if c in only_codes]

    print(f"Comunas a procesar: {len(communes)}")
    print(f"Skip download: {skip_download}")
    print(f"Staging dir:   {STAGING_DIR}\n")

    conn = await asyncpg.connect(DB_DSN)
    await conn.execute(STAGING_DDL)

    total_updated = 0
    for i, (code, folder) in enumerate(communes, 1):
        print(f"[{i}/{len(communes)}] {folder}")
        try:
            if skip_download:
                p = STAGING_DIR / f"comuna={code}.parquet"
                if not p.exists():
                    print(f"  SKIP: no existe {p}")
                    continue
            else:
                p = download_parquet(s3, code, folder)
            total_updated += await process_commune(conn, p, code)
        except Exception as e:
            print(f"  ERROR {code}: {e}")

    await conn.execute("DROP TABLE IF EXISTS _import_extra_staging")
    await conn.close()
    print(f"\nTotal predios enriquecidos: {total_updated:,}")


if __name__ == "__main__":
    asyncio.run(main())
