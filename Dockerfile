# ---------- Base para build (instala deps e compila wheels) ----------
    FROM python:3.11-slim AS builder

    # Evita prompts do apt e melhora logs do pip
    ENV PIP_NO_CACHE_DIR=1 \
        PYTHONDONTWRITEBYTECODE=1 \
        PYTHONUNBUFFERED=1
    
    # Dependências de sistema mínimas (runtime + build de wheels quando necessário)
    RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
     && rm -rf /var/lib/apt/lists/*
    
    WORKDIR /build
    
    # Copia requirements e cria wheels (mais rápido em builds futuros)
    COPY requirements.txt .
    RUN pip wheel --wheel-dir /build/wheels -r requirements.txt
    
    # ---------- Runtime final (limpo e leve) ----------
    FROM python:3.11-slim
    
    # Usuário não-root
    RUN useradd -m appuser
    
    ENV PIP_NO_CACHE_DIR=1 \
        PYTHONDONTWRITEBYTECODE=1 \
        PYTHONUNBUFFERED=1 \
        # Opcional: onde o NLTK irá salvar datasets, se você baixar algum
        NLTK_DATA=/home/appuser/nltk_data
    
    # Dependências só de runtime (se precisar algo do SO em prod, instale aqui)
    RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
     && rm -rf /var/lib/apt/lists/*
    
    WORKDIR /app
    
    # Instala deps a partir das wheels construídas
    COPY --from=builder /build/wheels /wheels
    RUN pip install --no-index --find-links=/wheels /wheels/*
    
    # Copia seu código e estáticos
    COPY app/ /app/app/
    COPY public/ /app/public/
    COPY requirements.txt /app/requirements.txt
    
    # (Opcional) Baixar dados do NLTK usados pela sua app
    # RUN python -c "import nltk; nltk.download('punkt'); nltk.download('stopwords')"
    
    # Permissões
    RUN chown -R appuser:appuser /app
    USER appuser
    
    # Exponha a porta do Uvicorn
    EXPOSE 8000
    
    HEALTHCHECK --interval=30s --timeout=3s --start-period=20s CMD \
      python -c "import sys, urllib.request; \
        try: \
            urllib.request.urlopen('http://127.0.0.1:8000/docs', timeout=2); \
        except Exception: \
            sys.exit(1)"
    
    # Comando de entrada (ajuste o módulo conforme seu entrypoint)
    # Exemplo: app/main.py expõe "app = FastAPI()"
    CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
    