from pydantic import BaseModel
from typing import Optional
from datetime import date


class Escritura(BaseModel):
    id: int
    fecha: date
    monto_pesos: Optional[int]
    monto_uf: Optional[float]

    class Config:
        from_attributes = True


class RolTransacciones(BaseModel):
    """Transacciones CBR para un rol específico."""
    comuna_codigo: int
    manzana: int
    predio: int
    total_transacciones: int
    primera_fecha: Optional[date]
    ultima_fecha: Optional[date]
    ultimo_monto_uf: Optional[float]
    ultimo_monto_pesos: Optional[int]
    escrituras: list[Escritura]


class H3StatsPorTipo(BaseModel):
    """Estadísticas de transacciones para un tipo de propiedad dentro del hexágono."""
    destino: str
    total_transacciones: int
    predios_distintos: int
    mediana_uf: Optional[float]
    promedio_uf: Optional[float]
    min_uf: Optional[float]
    max_uf: Optional[float]
    transacciones_12m: int
    tendencia_pct: Optional[float]  # % cambio promedio UF últimos 12m vs 12m anteriores


class H3Stats(BaseModel):
    """Estadísticas de transacciones en el hexágono H3 nivel 8, desglosadas por tipo."""
    h3_index: str
    radio_km: float = 0.46
    total_transacciones: int
    por_tipo: list[H3StatsPorTipo]


class PredioConTransacciones(BaseModel):
    """Predio con historial completo de transacciones CBR."""
    # Rol SII
    comuna_codigo: int
    manzana: int
    predio: int
    # Datos del predio
    direccion: Optional[str]
    destino: Optional[str]          # tipo: HABITACIONAL, COMERCIO, ESTACIONAMIENTO, etc.
    avaluo_fiscal: Optional[int]
    sup_construida: Optional[float]
    sup_terreno: Optional[float]
    lat: Optional[float]
    lon: Optional[float]
    h3_8: Optional[str]
    # Historial CBR
    total_transacciones: int
    ultima_fecha: Optional[date]
    ultimo_monto_uf: Optional[float]
    escrituras: list[Escritura]
