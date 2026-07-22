from typing import Optional, List
from pydantic import BaseModel, Field


class LegalCaseMetadata(BaseModel):
    case_number: Optional[str] = Field(default=None, description="Número de juicio o recurso (ej: 319-2011)")
    resolution_number: Optional[str] = Field(default=None, description="Número de resolución (ej: 850-09)")
    court: Optional[str] = Field(default=None, description="Tribunal o Corte (ej: Corte Nacional de Justicia)")
    chamber: Optional[str] = Field(default=None, description="Sala especializada (ej: Sala Contencioso Tributario)")
    judge_rapporteur: Optional[str] = Field(default=None, description="Juez ponente (ej: Dr. José Suing Nagua)")
    decision_date: Optional[str] = Field(default=None, description="Fecha de emisión o resolución")
    city: Optional[str] = Field(default=None, description="Ciudad de expedición (ej: Quito)")
    legal_area: str = Field(default="Otros", description="Materia o Área judicial (Civil y Mercantil, Laboral y Social, Contencioso Tributario, etc.)")
    asunto: Optional[str] = Field(default=None, description="Asunto o materia específica del recurso/demanda")
    action_type: Optional[str] = Field(default=None, description="Tipo de acción o recurso (ej: recurso de casación)")
    procedural_stage: Optional[str] = Field(default=None, description="Etapa procesal (ej: casación)")
    outcome: Optional[str] = Field(default=None, description="Resultado del fallo (ej: casa la sentencia)")
    summary: Optional[str] = Field(default=None, description="Síntesis o resumen del caso")
    topics: List[str] = Field(default_factory=list, description="Temas jurídicos identificados")
