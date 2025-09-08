from __future__ import annotations
import os
from pathlib import Path
from typing import Optional, List

from fastapi import FastAPI, UploadFile, Form, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from dotenv import load_dotenv

from .schemas import ProcessOut, ErrorOut, ProcessBatchOut
from .nlp import extract_text_from_pdf, preprocess, detect_language, extract_text_from_eml
from .classify import classify_email
from .respond import suggest_reply
from .utils import truncate

# --------- Setup ---------
load_dotenv()
MAX_BYTES = int(os.getenv("MAX_BYTES", str(10 * 1024 * 1024)))

# main.py está em app/, então a raiz do projeto é dois níveis acima de __file__? Não:  app/main.py -> parents[1] é a raiz.
BASE_DIR = Path(__file__).resolve().parents[1]
PUBLIC_DIR = BASE_DIR / "public"

app = FastAPI(title="AutoU - Processador de E-mails", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --------- Health ---------
@app.get("/health")
async def health():
    return {"status": "ok"}

# --------- API ---------
@app.post("/process", response_model=ProcessBatchOut, responses={400: {"model": ErrorOut}})
async def process_email(
    email_files: Optional[List[UploadFile]] = File(None),
    email_text: Optional[str] = Form(None),
    observacoes: Optional[str] = Form(None),
):
    if not email_files and not (email_text and email_text.strip()):
        raise HTTPException(400, "Envie arquivo(s) .txt/.pdf/.eml ou cole o texto.")

    raw_parts: List[str] = []

    if email_files:
        files = [f for f in email_files if f and getattr(f, "filename", "").strip()]
        for f in files:
            name = (f.filename or "").lower()
            data = await f.read()
            if not data:
                continue
            if len(data) > MAX_BYTES:
                raise HTTPException(400, f"Arquivo muito grande: {f.filename}.")

            if name.endswith(".txt"):
                try:
                    raw_parts.append(data.decode("utf-8", errors="ignore"))
                except Exception:
                    raw_parts.append(data.decode("latin-1", errors="ignore"))
            elif name.endswith(".pdf"):
                raw_parts.append(extract_text_from_pdf(data))
            elif name.endswith(".eml"):
                body, atts = extract_text_from_eml(data)
                if body:
                    raw_parts.append(body)
                for att_name, att_bytes in atts:
                    low = (att_name or "").lower()
                    if low.endswith(".txt"):
                        try:
                            raw_parts.append(att_bytes.decode("utf-8", errors="ignore"))
                        except Exception:
                            raw_parts.append(att_bytes.decode("latin-1", errors="ignore"))
                    elif low.endswith(".pdf"):
                        raw_parts.append(extract_text_from_pdf(att_bytes))
            else:
                # ignora extensões desconhecidas
                continue

    if email_text and email_text.strip():
        raw_parts.append(email_text)

    resultados: List[ProcessOut] = []
    for part in [p for p in raw_parts if p and p.strip()]:
        linguagem = detect_language(part)
        clean_text, termos = preprocess(part)
        categoria, score, termos_rule = await classify_email(part, clean_text)
        termos_final = termos_rule or termos
        resposta = await suggest_reply(
            truncate(part, 3500), categoria, linguagem, extra_instructions=observacoes
        )
        resultados.append(
            ProcessOut(
                categoria=categoria,
                confianca=round(float(score), 3),
                resposta=resposta,
                termos_relevantes=termos_final,
                linguagem=linguagem,
                tokens=len(clean_text.split()),
            )
        )

    if not resultados:
        raise HTTPException(400, "Não foi possível extrair texto válido.")

    return ProcessBatchOut(resultados=resultados)

# --------- Frontend ---------
# Página inicial em "/"
@app.get("/")
async def index():
    index_path = PUBLIC_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(404, "index.html não encontrado em /public")
    return FileResponse(index_path)

# Arquivos estáticos (CSS/JS/imagens) em /static
app.mount("/static", StaticFiles(directory=str(PUBLIC_DIR)), name="static")

# --------- Exec local (opcional) ---------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
