# app/respond.py
from __future__ import annotations
import os, asyncio
from typing import Optional

from openai import OpenAI, AuthenticationError, RateLimitError, APIConnectionError, APIStatusError

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL   = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_ORG     = os.getenv("OPENAI_ORG")  # opcional

# NÃO crie o client aqui se a chave pode não existir.
_client: Optional[OpenAI] = None

def get_client() -> Optional[OpenAI]:
    global _client
    if _client is None and OPENAI_API_KEY:
        _client = OpenAI(api_key=OPENAI_API_KEY, organization=OPENAI_ORG)
    return _client

TEMPLATE_PROD = (
    "Olá! Obrigado pela mensagem. Poderia confirmar o número do protocolo ou anexar os documentos necessários para seguirmos?"
)
TEMPLATE_IMP = (
    "Olá! Agradecemos a sua mensagem. Permanecemos à disposição para apoiar no que precisar."
)

def _make_system_instruction(categoria: str, extra: Optional[str]) -> str:
    base = (
        "Você é um assistente de e-mails. "
        "Responda SEMPRE em português, de forma curta, cordial e objetiva (máximo 2 frases). "
        "Se a categoria for Produtivo, peça um próximo passo prático (ex.: confirmar protocolo, anexar documento, autorizar acesso). "
        "Se a categoria for Improdutivo, agradeça e encerre cordialmente. "
    )
    if extra:
        base += f"Instruções do atendente: {extra.strip()[:300]} "
    base += f"Categoria: {categoria}."
    return base

async def _call_openai(messages, model: str, max_tokens: int = 110, temperature: float = 0.4) -> str:
    client = get_client()
    if client is None:
        # Sem chave -> não derruba; quem chamou cai no template
        raise AuthenticationError("OPENAI_API_KEY ausente", response=None, body=None)
    delay = 0.6
    for attempt in range(4):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            return (resp.choices[0].message.content or "").strip()
        except AuthenticationError as e:
            print("[OPENAI] Auth error:", e)
            raise
        except RateLimitError as e:
            print(f"[OPENAI] Rate/Quota (attempt {attempt+1}/4):", e)
            if attempt == 3:
                raise
            await asyncio.sleep(delay); delay *= 1.8
        except (APIConnectionError, APIStatusError) as e:
            print(f"[OPENAI] Network/Status (attempt {attempt+1}/4):", e)
            if attempt == 3:
                raise
            await asyncio.sleep(delay); delay *= 1.8
        except Exception as e:
            print(f"[OPENAI] Other error (attempt {attempt+1}/4):", repr(e))
            if attempt == 3:
                raise
            await asyncio.sleep(delay); delay *= 1.8
    return ""

async def suggest_reply(
    original_text: str,
    categoria: str,
    extra_instructions: Optional[str] = None
) -> str:
    if not OPENAI_API_KEY:
        return TEMPLATE_PROD if categoria == "Produtivo" else TEMPLATE_IMP

    system = _make_system_instruction(categoria, extra_instructions)
    user   = f"E-mail do cliente:\n{(original_text or '').strip()}\n\nResponda apenas a mensagem ao cliente."

    messages = [
        {"role": "system", "content": system},
        {"role": "user",   "content": user},
    ]

    try:
        text = await _call_openai(messages, OPENAI_MODEL)
        text = (text or "").strip()
        if text.lower().startswith("resposta:"):
            text = text.split(":", 1)[-1].strip()

        parts = [p.strip() for p in text.replace("?", "?.").replace("!", "!.").split(".") if p.strip()]
        if len(parts) > 2:
            text = ". ".join(parts[:2]) + "."
        return text or (TEMPLATE_PROD if categoria == "Produtivo" else TEMPLATE_IMP)
    except Exception as e:
        print("Erro OpenAI:", repr(e))
        return TEMPLATE_PROD if categoria == "Produtivo" else TEMPLATE_IMP
