#!/usr/bin/env python3
"""
Calcula H3 nivel 8 para todos los predios con lat/lon en catastro_actual.
Ejecutar en el VPS después de: pip3 install h3

Uso: python3 compute_h3.py
"""

import asyncio
import os
import sys

import asyncpg
import h3

DB_DSN = os.environ.get(
    "DATABASE_URL",
    "postgresql://catastro_app:Catastr0_2026_Tr3m3n@127.0.0.1:5435/catastro",
)

BATCH = 50_000


async def main():
    conn = await asyncpg.connect(DB_DSN)

    total = await conn.fetchval(
        "SELECT COUNT(*) FROM catastro_actual WHERE lat IS NOT NULL AND lon IS NOT NULL AND h3_8 IS NULL"
    )
    print(f"Predios pendientes: {total:,}")

    updated = 0
    while True:
        rows = await conn.fetch(
            """
            SELECT id, lat, lon FROM catastro_actual
            WHERE lat IS NOT NULL AND lon IS NOT NULL AND h3_8 IS NULL
            LIMIT $1
            """,
            BATCH,
        )
        if not rows:
            break

        data = [(h3.latlng_to_cell(float(r["lat"]), float(r["lon"]), 8), r["id"]) for r in rows]

        await conn.executemany(
            "UPDATE catastro_actual SET h3_8 = $1 WHERE id = $2",
            data,
        )
        updated += len(data)
        print(f"  actualizado {updated:,} / {total:,}", end="\r", flush=True)

    print(f"\nListo. Total actualizados: {updated:,}")
    await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
