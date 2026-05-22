from pydantic import BaseModel
from typing import Optional


class Predio(BaseModel):
    id: int
    periodo: str
    anio: int
    semestre: int

    # Identificación rol
    comuna: int
    manzana: int
    predio: int

    # Rol catastral (RC) - datos del registro
    rc_direccion: Optional[str]
    rc_serie: Optional[str]
    rc_ind_aseo: Optional[str]
    rc_cuota_trimestral: Optional[int]
    rc_avaluo_total: Optional[int]
    rc_avaluo_exento: Optional[int]
    rc_anio_term_exencion: Optional[int]
    rc_cod_ubicacion: Optional[str]
    rc_cod_destino: Optional[str]

    # Datos catastrales (DC)
    dc_direccion: Optional[str]
    dc_avaluo_fiscal: Optional[int]
    dc_contribucion_semestral: Optional[int]
    dc_cod_destino: Optional[str]
    dc_avaluo_exento: Optional[int]
    dc_sup_terreno: Optional[float]
    dc_cod_ubicacion: Optional[str]

    # Predios relacionados (BC = bienes comunes)
    dc_bc1_comuna: Optional[int]
    dc_bc1_manzana: Optional[int]
    dc_bc1_predio: Optional[int]
    dc_bc2_comuna: Optional[int]
    dc_bc2_manzana: Optional[int]
    dc_bc2_predio: Optional[int]

    # Predio padre (para departamentos en condominio)
    dc_padre_comuna: Optional[int]
    dc_padre_manzana: Optional[int]
    dc_padre_predio: Optional[int]

    # Construcción
    n_lineas_construccion: Optional[int]
    sup_construida_total: Optional[float]
    anio_construccion_min: Optional[int]
    anio_construccion_max: Optional[int]
    materiales: Optional[str]
    calidades: Optional[str]
    pisos_max: Optional[int]
    serie: Optional[str]

    # Georeferencia (si está disponible)
    lat: Optional[float]
    lon: Optional[float]

    class Config:
        from_attributes = True


class PredioNotFound(BaseModel):
    detail: str
    comuna: int
    manzana: int
    predio: int


class ComunaStats(BaseModel):
    codigo: int
    nombre: Optional[str]
    region: Optional[str]
    total_predios: int


class StatsResponse(BaseModel):
    total_predios: int
    total_comunas: int
    periodo_actual: Optional[str]
    db_size_mb: Optional[float]
