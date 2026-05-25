#!/usr/bin/env python3
"""
ETL: CBR escrituras CSV → cbr_escrituras.csv listo para importar en catastro-db.

Lee: F.2890_Escritura ... .csv  (COMUNA;MANZANA;PREDIO;FECHA_ESCRITURA;MONTO_PESOS;MONTO_UF)
Genera: /tmp/cbr_escrituras.csv  (comuna_codigo,manzana,predio,fecha,monto_pesos,monto_uf)

Requiere /tmp/comunas_lookup.txt (codigo|nombre) generado con:
  ssh VPS 'psql ... -tAc "SELECT codigo, nombre FROM comunas_lookup"' > /tmp/comunas_lookup.txt
"""

import csv
import sys
import unicodedata
from datetime import date

CBR_CSV   = "/Users/newmarkchile/Documents/TREMEN/5_PROJECTS/ai_catastral/data/F.2890_Escritura 01-01-2018 -  31-03-2026.csv"
LOOKUP    = "/tmp/comunas_lookup.txt"
OUTPUT    = "/tmp/cbr_escrituras.csv"


def norm(s: str) -> str:
    """Normaliza nombre de comuna: sin tildes, mayúsculas, espacios simples."""
    s = unicodedata.normalize("NFD", s.upper().strip())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return " ".join(s.replace("-", " ").split())


def build_lookup(lookup_path: str) -> dict:
    """Construye dict: nombre_normalizado → codigo_sii.

    Carga primero el lookup oficial (comunas_lookup) y luego añade aliases
    para nombres que el CBR usa pero el lookup no resuelve.
    """
    mapping = {}

    with open(lookup_path) as f:
        for line in f:
            line = line.strip()
            if "|" not in line:
                continue
            codigo_str, nombre = line.split("|", 1)
            try:
                codigo = int(codigo_str.strip())
            except ValueError:
                continue
            mapping[norm(nombre)] = codigo

    # Aliases que el CBR usa con nombres que no aparecen en comunas_lookup.
    # Códigos verificados contra comunas_lookup (2026-05): NO modificar sin re-auditar.
    aliases = {
        "CON CON":          5309,   # lookup tiene "CONCON" (sin espacio)
        "SANTIAGO CENTRO": 13101,   # lookup solo tiene "SANTIAGO"
        "PUERTO NATALES":  12101,   # lookup tiene "NATALES"
        "SAN FCO MOSTAZAL": 6104,   # lookup tiene "SAN FRANCISCO DE MOSTAZAL"
        "SAN JOSE MAIPO":  16303,   # lookup tiene "SAN JOSE DE MAIPO"
        "QUINTA TILCOCO":   6117,   # lookup tiene "QUINTA DE TILCOCO"
    }
    for k, v in aliases.items():
        nk = norm(k)
        if nk not in mapping:
            mapping[nk] = v

    return mapping


def parse_date(s: str) -> str | None:
    s = s.strip()
    if not s or len(s) < 8:
        return None
    try:
        d = date(int(s[:4]), int(s[4:6]), int(s[6:8]))
        # Filter dates before 2000 (probably data errors or not useful)
        if d.year < 2000:
            return None
        return d.isoformat()
    except ValueError:
        return None


def main():
    lookup = build_lookup(LOOKUP)

    written = 0
    skipped_commune = 0
    skipped_date = 0
    skipped_no_amount = 0

    with open(CBR_CSV, encoding="utf-8-sig") as fin, \
         open(OUTPUT, "w", newline="", encoding="utf-8") as fout:

        reader = csv.DictReader(fin, delimiter=";")
        writer = csv.writer(fout)
        writer.writerow(["comuna_codigo", "manzana", "predio", "fecha", "monto_pesos", "monto_uf"])

        for row in reader:
            # Commune lookup
            cbr_nombre = row["COMUNA"].strip()
            codigo = lookup.get(norm(cbr_nombre))
            if not codigo:
                skipped_commune += 1
                continue

            # Date
            fecha = parse_date(row["FECHA_ESCRITURA"])
            if not fecha:
                skipped_date += 1
                continue

            # Amounts
            pesos_str = row["MONTO_PESOS"].strip()
            uf_str    = row["MONTO_UF"].strip()
            monto_pesos = int(pesos_str) if pesos_str else None
            monto_uf    = float(uf_str)  if uf_str    else None
            if monto_pesos is None and monto_uf is None:
                skipped_no_amount += 1
                continue

            try:
                manzana = int(row["MANZANA"])
                predio  = int(row["PREDIO"])
            except (ValueError, KeyError):
                continue

            writer.writerow([codigo, manzana, predio, fecha,
                             monto_pesos if monto_pesos is not None else "",
                             f"{monto_uf:.2f}" if monto_uf is not None else ""])
            written += 1

    total = written + skipped_commune + skipped_date + skipped_no_amount
    print(f"Total leídas : {total:>10,}")
    print(f"Escritas     : {written:>10,}")
    print(f"Sin comuna   : {skipped_commune:>10,}")
    print(f"Sin fecha    : {skipped_date:>10,}")
    print(f"Sin monto    : {skipped_no_amount:>10,}")
    print(f"Output       : {OUTPUT}")


if __name__ == "__main__":
    main()
