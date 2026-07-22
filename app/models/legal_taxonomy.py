from typing import List, Optional
from pydantic import BaseModel, Field

# Áreas / Salas Judiciales Oficiales de la Jurisprudencia Ecuatoriana
LEGAL_AREAS = [
    "Civil y Mercantil",
    "Laboral y Social",
    "Contencioso Administrativo",
    "Contencioso Tributario",
    "Penal, Militar, Policial y Tránsito",
    "Familia, Niñez, Adolescencia y Adolescentes Infractores",
    "Constitucional",
    "Inquilinato",
    "Aduanero",
    "Propiedad Intelectual",
    "Otros",
]


class LegalClassification(BaseModel):
    primary_area: str = Field(description="Área o Sala principal (ej: Civil y Mercantil, Contencioso Tributario)")
    asunto: Optional[str] = Field(default=None, description="Figura o acción jurídica específica (ej: Nulidad de Contrato, Silencio Administrativo, Impugnación de Paternidad)")
    secondary_areas: List[str] = Field(default_factory=list, description="Otras áreas jurídicas relacionadas")
    topics: List[str] = Field(default_factory=list, description="Palabras clave o descriptores de la jurisprudencia")
