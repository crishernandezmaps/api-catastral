from fastapi import APIRouter, HTTPException, Query
from app.database import get_pool
from app.schemas.predio import Predio, PredioNotFound, ComunaStats, StatsResponse

router = APIRouter()

# Columnas a devolver (excluye geom binaria)
COLS = """
    id, periodo, anio, semestre,
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
    materiales, calidades, pisos_max, serie,
    lat, lon,
    eacs, eacano, eacs_descripcion,
    pp_id, pp_comuna, pp_manzana, pp_predio, pp_utm_x, pp_utm_y,
    direccion_sii, destino_descripcion, ubicacion, existe_predio,
    valor_total, valor_afecto, valor_exento, valor_comercial_clp_m2,
    ah, sector,
    ah_valor_unitario, ah_rango_superficie, ah_numero_muestras,
    ah_coef_variacion, ah_mediana, ah_eac, ah_eacano, ah_utm_x, ah_utm_y,
    csa_sector, csa_clase, csa_valor_unitario,
    csa_utm_x, csa_utm_y, csa_eac, csa_eacano,
    rav_codigo_ah, rav_rango_sup, rav_valor_m2,
    rav_codigo_ah_2, rav_rango_sup_2, rav_valor_m2_2,
    pol_area_m2
"""


@router.get(
    "/predio/{comuna}/{manzana}/{predio}",
    response_model=Predio,
    summary="Consultar predio por rol SII",
    description="Retorna todos los datos SII para el rol identificado por (comuna, manzana, predio).",
)
async def get_predio(comuna: int, manzana: int, predio: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"SELECT {COLS} FROM catastro_actual WHERE comuna=$1 AND manzana=$2 AND predio=$3 LIMIT 1",
            comuna, manzana, predio,
        )
    if not row:
        raise HTTPException(
            status_code=404,
            detail=f"Predio no encontrado: comuna={comuna}, manzana={manzana}, predio={predio}",
        )
    return dict(row)


@router.get(
    "/comuna/{codigo}/predios",
    response_model=list[Predio],
    summary="Listar predios de una comuna",
    description="Retorna predios paginados de una comuna. Máximo 500 por página.",
)
async def get_predios_comuna(
    codigo: int,
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
):
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"SELECT {COLS} FROM catastro_actual WHERE comuna=$1 ORDER BY manzana, predio LIMIT $2 OFFSET $3",
            codigo, limit, offset,
        )
    return [dict(r) for r in rows]


@router.get(
    "/comunas",
    response_model=list[ComunaStats],
    summary="Comunas disponibles con conteo de predios",
)
async def get_comunas():
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT
                ca.comuna AS codigo,
                cl.nombre,
                cl.region,
                COUNT(*) AS total_predios
            FROM catastro_actual ca
            LEFT JOIN comunas_lookup cl ON ca.comuna = cl.codigo
            GROUP BY ca.comuna, cl.nombre, cl.region
            ORDER BY cl.region NULLS LAST, cl.nombre NULLS LAST
        """)
    return [dict(r) for r in rows]


@router.get(
    "/stats",
    response_model=StatsResponse,
    summary="Estadísticas generales de la base de datos",
)
async def get_stats():
    pool = await get_pool()
    async with pool.acquire() as conn:
        total = await conn.fetchval("SELECT COUNT(*) FROM catastro_actual")
        comunas = await conn.fetchval("SELECT COUNT(DISTINCT comuna) FROM catastro_actual")
        periodo = await conn.fetchval("SELECT periodo FROM catastro_actual LIMIT 1")
        size_mb = await conn.fetchval(
            "SELECT ROUND(pg_database_size(current_database()) / 1024.0 / 1024.0, 1)"
        )
    return StatsResponse(
        total_predios=total,
        total_comunas=comunas,
        periodo_actual=periodo,
        db_size_mb=float(size_mb) if size_mb else None,
    )


@router.get(
    "/buscar",
    response_model=list[Predio],
    summary="Buscar predios por dirección",
    description="Búsqueda por texto en dirección. Requiere commune (código SII). Máximo 50 resultados.",
)
async def buscar_por_direccion(
    q: str = Query(..., min_length=3, description="Texto de búsqueda en dirección"),
    comuna: int = Query(..., description="Código SII de la comuna"),
    limit: int = Query(20, ge=1, le=50),
):
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""
            SELECT {COLS}
            FROM catastro_actual
            WHERE comuna=$1 AND rc_direccion ILIKE $2
            ORDER BY rc_direccion
            LIMIT $3
            """,
            comuna, f"%{q}%", limit,
        )
    return [dict(r) for r in rows]
