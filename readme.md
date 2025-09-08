# AutoU – Case Prático (Execução Local)

Este guia explica **como rodar a aplicação localmente** usando **Python** (venv), **Docker** ou **Docker Compose**. Também traz endpoints, variáveis de ambiente, payloads de teste e solução de problemas comuns.

---

## 🔎 Visão Geral do Projeto

```
.
├─ app/                  # backend FastAPI (main.py, nlp, classify, respond, etc.)
├─ public/               # frontend estático (index.html, styles.css, etc.)
├─ data/                 # (opcional) artefatos locais, samples, etc.
├─ Dockerfile            # build de imagem para produção
├─ docker-compose.yml    # ambiente de desenvolvimento local (hot-reload)
├─ requirements.txt      # dependências Python
└─ readme.md             # este documento
```

* **Frontend:** servido pelo próprio FastAPI

  * `GET /` → serve `public/index.html`
  * `GET /static/*` → serve arquivos estáticos da pasta `public/`
* **API:** prefixo `/api`

  * `GET /api/health` → healthcheck simples
  * `POST /api/process` → processa e classifica o(s) e-mail(s)

**Tipos aceitos** no processamento: `.txt`, `.pdf`, `.eml` **ou** texto colado via formulário.

---

## ✅ Pré‑requisitos

* **Python 3.11+**
* **Pip**
* (Opcional) **Docker** e **Docker Compose**
* **Chave da OpenAI** (caso use as respostas com LLM)

> Sem `OPENAI_API_KEY`, a aplicação **ainda funciona** e responde com **templates** estáticos.

---

## ⚙️ Variáveis de Ambiente

Crie um arquivo **`.env`** na raiz do projeto (ao lado do `Dockerfile`). Exemplo:

```
# OpenAI
OPENAI_API_KEY=coloque_sua_chave_aqui
OPENAI_MODEL=gpt-4o-mini

# App
MAX_BYTES=10485760  # 10 MB por arquivo
```

> **Idioma das respostas:** configurado para **sempre responder em português** no `app/respond.py`.

---

## 🐍 Rodando com Python (venv)

1. Criar e ativar ambiente virtual

```bash
python3 -m venv .venv
# macOS/Linux
source .venv/bin/activate
```

2. Instalar dependências

```bash
pip install -U pip
pip install -r requirements.txt
```

> Se precisar de corpora do **NLTK** (ex.: `punkt`, `stopwords`), rode:
>
> ```bash
> python3 -c "import nltk; nltk.download('punkt'); nltk.download('stopwords')"
> ```

3. Rodar o servidor

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

4. Acessar

* Frontend: [http://localhost:8000/](http://localhost:8000/)
* Health: [http://localhost:8000/api/health](http://localhost:8000/health)
* Docs (Swagger): http://localhost:8000/docs

---

## 🐳 Rodando com Docker (produção local)

1. Build da imagem

```bash
docker build -t autou-fastapi:prod .
```

2. Rodar o container

```bash
docker run --rm -p 8000:8000 \
  --env-file .env \
  --name autou autou-fastapi:prod
```

3. Acessar

* [http://localhost:8000/](http://localhost:8000/) (index)
* [http://localhost:8000/api/health](http://localhost:8000/health)
* [http://localhost:8000/docs](http://localhost:8000/docs)

---

## 🧩 Rodando com Docker Compose (dev com hot‑reload)

```bash
docker compose up --build
```

* A aplicação sobe em `http://localhost:8000`
* O código é montado como volume → alterações em `app/` e `public/` recarregam o servidor

> Dica: exporte a chave `OPENAI_API_KEY` no seu shell ou configure no `.env`.

---

## 🔗 Endpoints & Exemplos

### `GET /health`

```bash
curl -s http://localhost:8000/health
```

### `POST /process` (multipart)

#### 1) Enviando **texto** (campo `email_text`)

```bash
curl -s -X POST http://localhost:8000/process \
  -F "email_text=Olá, poderiam me atualizar sobre o protocolo 123?" \
  -F "observacoes=Responder de forma cordial e solicitar documento se faltar"
```

#### 2) Enviando **arquivos** (`email_files` aceita múltiplos)

```bash
curl -s -X POST http://localhost:8000/process \
  -F "email_files=@samples/exemplo.txt" \
  -F "email_files=@samples/exemplo.pdf" \
  -F "observacoes=Se houver protocolo, pedir confirmação"
```

**Resposta (exemplo):**

```json
{
  "resultados": [
    {
      "categoria": "Produtivo",
      "confianca": 0.923,
      "resposta": "Olá! Poderia confirmar o número do protocolo para darmos sequência? Obrigado.",
      "termos_relevantes": ["protocolo", "atualização"],
      "linguagem": "pt",
      "tokens": 128
    }
  ]
}
```

> Campos suportados: `email_files` (múltiplos), `email_text` (texto colado) e `observacoes` (instruções do atendente).

---

## 🧠 Como funciona (resumo)

1. **Leitura** (`.txt`, `.pdf`, `.eml`) e/ou texto colado
2. **Pré‑processamento** (limpeza, normalização, NLTK)
3. **Classificação** (Produtivo/Improdutivo)
4. **Geração de resposta** (usa OpenAI se disponível; caso contrário, templates)
5. **Retorno** estruturado (categoria, confiança, resposta, termos, etc.)

---