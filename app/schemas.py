# Decompiled with PyLingual (https://pylingual.io)
# Internal filename: /app/app/schemas.py
# Bytecode version: 3.11a7e (3495)
# Source timestamp: 2025-09-04 20:24:02 UTC (1757017442)

from pydantic import BaseModel, Field
from typing import List, Optional

class ProcessOut(BaseModel):
    categoria: str = Field(description='Produtivo ou Improdutivo')
    confianca: float = Field(ge=0, le=1)
    resposta: str
    termos_relevantes: List[str] = []
    linguagem: Optional[str] = None
    tokens: Optional[int] = None

class ErrorOut(BaseModel):
    error: str

class ProcessBatchOut(BaseModel):
    resultados: List[ProcessOut]