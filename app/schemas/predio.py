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

    # === Enriquecimiento sii_extractor (S3) ===

    # EAC (Estudio de Avalúo Catastral)
    eacs: Optional[int]
    eacano: Optional[int]
    eacs_descripcion: Optional[str]

    # Predio publicado (rol canónico en API pública del SII)
    pp_id: Optional[str]
    pp_comuna: Optional[int]
    pp_manzana: Optional[int]
    pp_predio: Optional[int]
    pp_utm_x: Optional[float]
    pp_utm_y: Optional[float]

    # Metadatos SII enriquecidos
    direccion_sii: Optional[str]
    destino_descripcion: Optional[str]
    ubicacion: Optional[str]
    existe_predio: Optional[bool]

    # Valores publicados
    valor_total: Optional[int]
    valor_afecto: Optional[int]
    valor_exento: Optional[int]
    valor_comercial_clp_m2: Optional[float]

    # Área Homogénea (AH) — peer group de tasación
    ah: Optional[str]
    sector: Optional[str]
    ah_valor_unitario: Optional[float]
    ah_rango_superficie: Optional[str]
    ah_numero_muestras: Optional[int]
    ah_coef_variacion: Optional[float]
    ah_mediana: Optional[float]
    ah_eac: Optional[int]
    ah_eacano: Optional[int]
    ah_utm_x: Optional[float]
    ah_utm_y: Optional[float]

    # CSA (Catastro de Suelo Agrícola)
    csa_sector: Optional[str]
    csa_clase: Optional[str]
    csa_valor_unitario: Optional[float]
    csa_utm_x: Optional[float]
    csa_utm_y: Optional[float]
    csa_eac: Optional[int]
    csa_eacano: Optional[int]

    # RAV (Reavalúo No Agrícola 2022)
    rav_codigo_ah: Optional[str]
    rav_rango_sup: Optional[str]
    rav_valor_m2: Optional[float]
    rav_codigo_ah_2: Optional[str]
    rav_rango_sup_2: Optional[str]
    rav_valor_m2_2: Optional[float]

    # Polígono
    pol_area_m2: Optional[float]

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
