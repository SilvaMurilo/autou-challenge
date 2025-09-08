from __future__ import annotations
import os, re
from dataclasses import dataclass
from typing import Tuple, List, Optional

USE_OPENAI_CLASSIFIER = os.getenv("USE_OPENAI_CLASSIFIER", "0") in {"1", "true", "True"}

# ——— Palavras-chave (pt-br) ———
ASK_TOKENS = [
    "poderia", "pode", "poderiam", "poderia me ajudar", "pode verificar", "como faço",
    "como proceder", "posso", "consigo", "tem como", "é possível", "poderia informar",
    "qual o status", "preciso de", "segue em anexo", "consegue", "pode me enviar",
]
ACTION_TOKENS = [
    "atualizar", "regularizar", "concluir", "autorizar", "confirmar", "validar",
    "emitir", "reativar", "ajustar", "corrigir", "revisar", "enviar", "agendar",
    "cancelar", "solicitar", "abrir chamado", "responder", "retornar", "providenciar",
]
STATUS_TOKENS = [
    "status", "andamento", "previsão", "prazo", "pendência", "aberto", "em análise",
    "fila", "retorno", "protocolo", "chamado", "ticket",
]
ATTACH_TOKENS = [
    "anexo", "anexei", "em anexo", "segue anexo", "segue em anexo"
]
DATE_TOKENS = [
    "hoje", "amanhã", "vencimento", "até", "prazo", "data", "segunda", "terça",
    "quarta", "quinta", "sexta", "sábado", "domingo", "dia", "às", "as", "hora"
]

# improdutivo
GREET_TOKENS = [
    "bom dia", "boa tarde", "boa noite", "feliz natal", "feliz ano novo",
    "boas festas", "parabéns", "obrigado", "obrigada", "agradeço", "valeu",
]
SMALL_TALK_TOKENS = [
    "apenas para avisar", "somente para informar", "sem necessidade de retorno",
    "quando puder", "obrigado pelo atendimento", "obrigada pelo atendimento",
]

RE_QUESTION = re.compile(r"[?]+")
RE_NUMBER   = re.compile(r"\b\d{3,}\b")  # protocolos/ids simples

@dataclass
class RuleResult:
    categoria: str                  # "Produtivo" | "Improdutivo"
    score: float                    # 0..1 (confiança de produtivo)
    termos: List[str]               # termos que pesaram


def _normalize(s: str) -> str:
    return " ".join(s.lower().split())


def _heuristic_score(subject: str, body: str) -> RuleResult:
    subj = _normalize(subject or "")
    text = _normalize(body or "")

    # ——— contagem de sinais ———
    pos_terms: List[str] = []
    neg_terms: List[str] = []

    def count_tokens(tokens: List[str], where: str, bucket: List[str]) -> int:
        c = 0
        for t in tokens:
            if t in where:
                c += 1; bucket.append(t)
        return c

    q_marks = 1 if RE_QUESTION.search(subject or "") or RE_QUESTION.search(body or "") else 0
    has_number = 1 if RE_NUMBER.search(body or "") or RE_NUMBER.search(subject or "") else 0

    # sinais “produtivos”
    pos = 0
    pos += count_tokens(ASK_TOKENS, text + " " + subj, pos_terms) * 1.2
    pos += count_tokens(ACTION_TOKENS, text + " " + subj, pos_terms) * 1.2
    pos += count_tokens(STATUS_TOKENS, text + " " + subj, pos_terms) * 1.0
    pos += count_tokens(ATTACH_TOKENS, text + " " + subj, pos_terms) * 1.0
    pos += count_tokens(DATE_TOKENS,  text + " " + subj, pos_terms) * 0.6
    pos += q_marks * 1.0
    pos += has_number * 0.5

    # sinais “improdutivos”
    neg = 0
    neg += count_tokens(GREET_TOKENS, text + " " + subj, neg_terms) * 1.0
    neg += count_tokens(SMALL_TALK_TOKENS, text + " " + subj, neg_terms) * 1.0

    # bônus/penalidade por densidade de texto
    length = max(1, len(text.split()))
    if length > 8 and (q_marks or pos > 0):   # emails minimamente descritivos + pergunta/ação
        pos += 0.4
    if length < 5 and neg > 0 and pos == 0:   # curtíssimo e só cumprimento
        neg += 0.4

    raw = pos - neg
    # squash para 0..1
    #  -2 → ~0.12 ; 0 → 0.5 ; +2 → ~0.88 ; +4 → ~0.98
    score = 1 / (1 + pow(2.71828, -raw))

    categoria = "Produtivo" if score >= 0.55 else "Improdutivo" if score <= 0.45 else "Produtivo" if pos >= neg else "Improdutivo"

    termos = (pos_terms if categoria == "Produtivo" else neg_terms)[:6]  # mostra até 6
    return RuleResult(categoria=categoria, score=score, termos=termos)


# ——— Classificador público ———
async def classify_email(raw_text: str, clean_text: str, subject: Optional[str] = None) -> Tuple[str, float, List[str]]:
    """
    Retorna (categoria, score_produtivo, termos_relevantes)
    score é confiança de PRODUTIVO em 0..1
    """
    # tenta detectar um assunto simples (quando vier texto “chato”)
    subj = subject or ""
    # se o raw_text contém um header “Subject:” (de .eml) tente extrair
    m = re.search(r"^subject:\s*(.+)$", raw_text, flags=re.I | re.M)
    if m and not subj:
        subj = m.group(1).strip()

    # heurística local
    rr = _heuristic_score(subj, raw_text)

    # zona morta → opcionalmente pergunta pro GPT (se habilitado)
    if 0.45 <= rr.score <= 0.55 and USE_OPENAI_CLASSIFIER:
        try:
            from openai import OpenAI
            client = OpenAI()

            sys = (
                "Você é um classificador. Responda apenas uma palavra: 'Produtivo' ou 'Improdutivo'. "
                "Produtivo = requer ação, informação específica, acompanhamento, status, envio de documentos. "
                "Improdutivo = felicitações, agradecimentos, mensagens sociais sem ação."
            )
            user = f"Assunto: {subj}\n\nCorpo:\n{raw_text}\n\nResponda:"

            res = client.chat.completions.create(
                model=os.getenv("OPENAI_CLASSIFIER_MODEL", os.getenv("OPENAI_MODEL", "gpt-4o-mini")),
                messages=[{"role":"system","content":sys},{"role":"user","content":user}],
                max_tokens=3,
                temperature=0.0,
            )
            label = (res.choices[0].message.content or "").strip().lower()
            if "produt" in label:
                rr.categoria = "Produtivo"
                rr.score = max(rr.score, 0.62)  # puxa para cima
            elif "improdut" in label:
                rr.categoria = "Improdutivo"
                rr.score = min(rr.score, 0.38)  # puxa para baixo
        except Exception as e:
            # se falhar, fica com a heurística
            print("[classify] fallback heurístico (GPT indisponível):", repr(e))

    return rr.categoria, float(round(rr.score, 4)), rr.termos
