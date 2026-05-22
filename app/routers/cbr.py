"""
Endpoints CBR (Conservador de Bienes Raíces) — transacciones de compraventa.

Endpoints:
  GET /cbr/rol/{comuna}/{manzana}/{predio}     — historial de escrituras de un rol
  GET /cbr/h3/{comuna}/{manzana}/{predio}      — estadísticas H3 de propiedades similares
  GET /cbr/cerca?lat=&lon=&radio=              — predios + CBR en radio dado (PostGIS)
"""

from fastapi import APIRouter, HTTPException, Query
from app.database import get_pool
from app.schemas.cbr import Escritura, RolTransacciones, H3Stats, PredioConTransacciones

router = APIRouter(prefix="/cbr", tags=["CBR Transacciones"])


@router.get(
    "/rol/{comuna}/{manzana}/{predio}",
    response_model=RolTransacciones,
    summary="Historial de escrituras de un rol",
    description="Retorna todas las transacciones de compraventa registradas en el CBR para el rol indicado.",
)
async def get_transacciones_rol(comuna: int, manzana: int, predio: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, fecha, monto_pesos, monto_uf
            FROM cbr_escrituras
            WHERE comuna_codigo=$1 AND manzana=$2 AND predio=$3
            ORDER BY fecha DESC
            """,
            comuna, manzana, predio,
        )

    if not rows:
        raise HTTPException(
            status_code=404,
            detail=f"Sin transacciones CBR para rol {comuna}/{manzana}/{predio}",
        )

    escrituras = [dict(r) for r in rows]
    uf_values  = [r["monto_uf"] for r in rows if r["monto_uf"]]

    return RolTransacciones(
        comuna_codigo=comuna,
        manzana=manzana,
        predio=predio,
        total_transacciones=len(escrituras),
        primera_fecha=rows[-1]["fecha"],
        ultima_fecha=rows[0]["fecha"],
        ultimo_monto_uf=rows[0]["monto_uf"],
        ultimo_monto_pesos=rows[0]["monto_pesos"],
        escrituras=escrituras,
    )


@router.get(
    "/h3/{comuna}/{manzana}/{predio}",
    response_model=H3Stats,
    summary="Estadísticas H3 de propiedades similares",
    description=(
        "Para el rol indicado, calcula estadísticas de transacciones de propiedades "
        "del mismo tipo (destino) dentro del mismo hexágono H3 nivel 8 (~460m radio). "
        "Requiere que el predio tenga coordenadas."
    ),
)
async def get_h3_stats(comuna: int, manzana: int, predio: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Get H3 index and destino for this rol
        base = await conn.fetchrow(
            """
            SELECT h3_8, rc_cod_destino, dc_cod_destino
            FROM catastro_actual
            WHERE comuna=$1 AND manzana=$2 AND predio=$3
            ORDER BY h3_8 NULLS LAST
            LIMIT 1
            """,
            comuna, manzana, predio,
        )

    if not base:
        raise HTTPException(status_code=404, detail="Predio no encontrado")
    if not base["h3_8"]:
        raise HTTPException(
            status_code=422,
            detail="Este predio no tiene coordenadas; no es posible calcular estadísticas H3.",
        )

    h3_index = base["h3_8"]

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            WITH escrituras_h3 AS (
                SELECT
                    e.monto_uf,
                    e.fecha,
                    e.comuna_codigo,
                    e.manzana,
                    e.predio,
                    COALESCE(NULLIF(c.rc_cod_destino, ''), NULLIF(c.dc_cod_destino, ''), 'SIN TIPO') AS destino
                FROM cbr_escrituras e
                JOIN catastro_actual c
                    ON c.comuna = e.comuna_codigo
                    AND c.manzana = e.manzana
                    AND c.predio  = e.predio
                WHERE c.h3_8 = $1
                  AND e.monto_uf > 0
            )
            SELECT
                destino,
                COUNT(*)                                                         AS total_transacciones,
                COUNT(DISTINCT (comuna_codigo, manzana, predio))                 AS predios_distintos,
                ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY monto_uf)::numeric, 2) AS mediana_uf,
                ROUND(AVG(monto_uf)::numeric, 2)                                AS promedio_uf,
                ROUND(MIN(monto_uf)::numeric, 2)                                AS min_uf,
                ROUND(MAX(monto_uf)::numeric, 2)                                AS max_uf,
                COUNT(*) FILTER (WHERE fecha >= CURRENT_DATE - INTERVAL '12 months') AS transacciones_12m,
                CASE
                    WHEN AVG(monto_uf) FILTER (
                        WHERE fecha >= CURRENT_DATE - INTERVAL '24 months'
                          AND fecha <  CURRENT_DATE - INTERVAL '12 months'
                    ) > 0
                    THEN ROUND((
                        AVG(monto_uf) FILTER (WHERE fecha >= CURRENT_DATE - INTERVAL '12 months') /
                        AVG(monto_uf) FILTER (
                            WHERE fecha >= CURRENT_DATE - INTERVAL '24 months'
                              AND fecha <  CURRENT_DATE - INTERVAL '12 months'
                        ) - 1
                    ) * 100, 1)
                    ELSE NULL
                END AS tendencia_pct
            FROM escrituras_h3
            GROUP BY destino
            ORDER BY total_transacciones DESC
            """,
            h3_index,
        )

    if not rows:
        raise HTTPException(
            status_code=404,
            detail=f"Sin transacciones CBR en hexágono H3 {h3_index}",
        )

    from app.schemas.cbr import H3StatsPorTipo
    por_tipo = [
        H3StatsPorTipo(
            destino=r["destino"],
            total_transacciones=r["total_transacciones"],
            predios_distintos=r["predios_distintos"],
            mediana_uf=float(r["mediana_uf"]) if r["mediana_uf"] else None,
            promedio_uf=float(r["promedio_uf"]) if r["promedio_uf"] else None,
            min_uf=float(r["min_uf"]) if r["min_uf"] else None,
            max_uf=float(r["max_uf"]) if r["max_uf"] else None,
            transacciones_12m=r["transacciones_12m"] or 0,
            tendencia_pct=float(r["tendencia_pct"]) if r["tendencia_pct"] is not None else None,
        )
        for r in rows
    ]

    return H3Stats(
        h3_index=h3_index,
        total_transacciones=sum(t.total_transacciones for t in por_tipo),
        por_tipo=por_tipo,
    )


@router.get(
    "/cerca",
    response_model=list[PredioConTransacciones],
    summary="Predios + transacciones CBR cerca de una coordenada",
    description=(
        "Retorna todos los predios dentro de `radio` metros de la coordenada dada, "
        "junto con su resumen de transacciones CBR (última venta, total escrituras). "
        "Máximo 200 predios. Requiere PostGIS."
    ),
)
async def get_predios_cerca(
    lat:   float = Query(..., description="Latitud decimal (ej: -33.4569)"),
    lon:   float = Query(..., description="Longitud decimal (ej: -70.6483)"),
    radio: int   = Query(500, ge=50, le=5000, description="Radio de búsqueda en metros"),
    limit: int   = Query(100, ge=1, le=200),
):
    pool = await get_pool()
    async with pool.acquire() as conn:
        # 1. Obtener predios dentro del radio
        predios = await conn.fetch(
            """
            SELECT DISTINCT ON (c.comuna, c.manzana, c.predio)
                c.comuna   AS comuna_codigo,
                c.manzana,
                c.predio,
                COALESCE(c.dc_direccion, c.rc_direccion) AS direccion,
                COALESCE(NULLIF(c.rc_cod_destino,''), NULLIF(c.dc_cod_destino,'')) AS destino,
                c.dc_avaluo_fiscal    AS avaluo_fiscal,
                c.sup_construida_total AS sup_construida,
                c.dc_sup_terreno      AS sup_terreno,
                c.lat,
                c.lon,
                c.h3_8
            FROM catastro_actual c
            WHERE ST_DWithin(
                c.geom::geography,
                ST_SetSRID(ST_MakePoint($2, $1), 4326)::geography,
                $3
            )
            ORDER BY
                c.comuna, c.manzana, c.predio,
                ST_Distance(
                    c.geom::geography,
                    ST_SetSRID(ST_MakePoint($2, $1), 4326)::geography
                )
            LIMIT $4
            """,
            lat, lon, radio, limit,
        )

        if not predios:
            return []

        # 2. Obtener todas las escrituras de esos predios en una sola query
        rol_tuples = [(r["comuna_codigo"], r["manzana"], r["predio"]) for r in predios]
        escrituras_rows = await conn.fetch(
            """
            SELECT id, comuna_codigo, manzana, predio, fecha, monto_pesos, monto_uf
            FROM cbr_escrituras
            WHERE (comuna_codigo, manzana, predio) = ANY($1::int[])
            ORDER BY fecha DESC
            """,
            # Pasar como lista de registros usando unnest
            [(r[0], r[1], r[2]) for r in rol_tuples],
        ) if False else await conn.fetch(
            """
            SELECT id, comuna_codigo, manzana, predio, fecha, monto_pesos, monto_uf
            FROM cbr_escrituras
            WHERE comuna_codigo = ANY($1) AND manzana = ANY($2) AND predio = ANY($3)
            ORDER BY fecha DESC
            """,
            [r[0] for r in rol_tuples],
            [r[1] for r in rol_tuples],
            [r[2] for r in rol_tuples],
        )

    # Agrupar escrituras por (comuna, manzana, predio)
    from collections import defaultdict
    escrituras_por_rol: dict = defaultdict(list)
    for e in escrituras_rows:
        key = (e["comuna_codigo"], e["manzana"], e["predio"])
        escrituras_por_rol[key].append(
            Escritura(id=e["id"], fecha=e["fecha"],
                      monto_pesos=e["monto_pesos"], monto_uf=float(e["monto_uf"]) if e["monto_uf"] else None)
        )

    result = []
    for r in predios:
        key = (r["comuna_codigo"], r["manzana"], r["predio"])
        escrituras = escrituras_por_rol.get(key, [])
        ultima = escrituras[0] if escrituras else None
        result.append(PredioConTransacciones(
            comuna_codigo=r["comuna_codigo"],
            manzana=r["manzana"],
            predio=r["predio"],
            direccion=r["direccion"],
            destino=r["destino"],
            avaluo_fiscal=r["avaluo_fiscal"],
            sup_construida=r["sup_construida"],
            sup_terreno=r["sup_terreno"],
            lat=r["lat"],
            lon=r["lon"],
            h3_8=r["h3_8"],
            total_transacciones=len(escrituras),
            ultima_fecha=ultima.fecha if ultima else None,
            ultimo_monto_uf=ultima.monto_uf if ultima else None,
            escrituras=escrituras,
        ))

    return result
