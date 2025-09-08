from __future__ import annotations
import io
import pdfplumber
import re
from typing import Tuple, List
from unidecode import unidecode
import nltk
try:
    nltk.data.find('corpora/stopwords')
except LookupError:
    nltk.download('stopwords', quiet=True)
STOP_PT = set(nltk.corpus.stopwords.words('portuguese'))
SIG_HINTS = ['att,', 'atenciosamente', 'enviado do meu iphone', 'confidencial', 'esta mensagem e seus anexos', 'este e-mail e confidencial']

def extract_text_from_pdf(raw: bytes) -> str:
    with pdfplumber.open(io.BytesIO(raw)) as pdf:
        pages = [page.extract_text() or '' for page in pdf.pages]
    return '\n'.join(pages)

def detect_language(text: str) -> str:
    pt_markers = ['você', 'obrigado', 'segue', 'anexo', 'favor', 'prazo', 'atualização', 'dúvida', 'chamado']
    hits = sum((1 for w in pt_markers if w in text.lower()))
    return 'pt' if hits >= 2 else 'en'

def preprocess(raw: str) -> Tuple[str, List[str]]:
    """
    - normaliza, remove urls/emails, baixa ruído, tira acentos, stopwords
    - retorna texto limpo + lista de termos relevantes (top 10 por frequência)
    """
    text = raw.strip()
    text = re.sub('(?i)^from:.*?(?:\\n\\r?)+', '', text, flags=re.S)
    text = re.sub('(?i)^de:.*?(?:\\n\\r?)+', '', text, flags=re.S)
    text = re.sub('https?://\\S+', ' ', text)
    text = re.sub('[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}', ' ', text)
    low = text.lower()
    for h in SIG_HINTS:
        if h in low:
            idx = low.rfind(h)
            if idx > 80:
                text = text[:idx]
                break
    text = unidecode(text)
    text = re.sub('[^a-zA-Z0-9À-ÿ\\n\\s.,;:!?-]', ' ', text)
    text = re.sub('\\s{2,}', ' ', text).strip()
    tokens = [t for t in re.findall('\\b\\w{2,}\\b', text.lower()) if t not in STOP_PT]
    freq = {}
    for t in tokens:
        freq[t] = freq.get(t, 0) + 1
        continue
    termos = [w for w, _ in sorted(freq.items(), key=lambda kv: (-kv[1], kv[0]))[:10]]
    return (' '.join(tokens), termos)
from email import policy
from email.message import Message
from email.parser import BytesParser
from bs4 import BeautifulSoup

def _html_to_text(html: str) -> str:
    try:
        soup = BeautifulSoup(html, 'html.parser')
        for tag in soup(['script', 'style', 'noscript']):
            tag.decompose()
        text = soup.get_text(separator=' ', strip=True)
        return re.sub('\\s{2,}', ' ', text).strip()
    except Exception:
        text = re.sub('<[^>]+>', ' ', html)
        return re.sub('\\s{2,}', ' ', text).strip()

def _decode_part(part: Message) -> str:
    """
    Decodifica conteúdo textual (plain/html) respeitando charset quando possível.
    """
    try:
        content = part.get_content()
        if isinstance(content, bytes):
            content = content.decode(part.get_content_charset() or 'utf-8', errors='ignore')
        return content
    except Exception:
        payload = part.get_payload(decode=True) or b''
        try:
            return payload.decode(part.get_content_charset() or 'utf-8', errors='ignore')
        except Exception:
            return payload.decode('latin-1', errors='ignore')

def _pick_best_text(candidates_plain: list[str], candidates_html: list[str]) -> str:
    if candidates_plain:
        return max(candidates_plain, key=len).strip()
    if candidates_html:
        html = max(candidates_html, key=len)
        return _html_to_text(html)
    return ''

def _walk_message(msg: Message) -> tuple[str, list[tuple[str, bytes]]]:
    """
    Percorre recursivamente a mensagem (e mensagens aninhadas) e retorna:
    (texto_corpo, anexos_interessantes[ (filename, bytes) ])
    """
    plains, htmls = ([], [])
    attachments = []
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = part.get_content_disposition()
            if ctype == 'message/rfc822':
                try:
                    nested = part.get_payload(0)
                except Exception:
                    nested = None
                if isinstance(nested, Message):
                    nested_text, nested_atts = _walk_message(nested)
                    if nested_text:
                        plains.append(nested_text)
                    attachments.extend(nested_atts)
            else:
                if ctype in ('text/plain', 'text/html') and disp in (None, 'inline', 'attachment'):
                    text = _decode_part(part)
                    if ctype == 'text/plain':
                        plains.append(text)
                    else:
                        htmls.append(text)
                    continue
                if disp == 'attachment':
                    filename = part.get_filename() or ''
                    low = filename.lower()
                    blob = part.get_payload(decode=True) or b''
                    if low.endswith('.txt') or low.endswith('.pdf'):
                        attachments.append((filename, blob))
    else:
        ctype = msg.get_content_type()
        if ctype in ['text/plain', 'text/html']:
            text = _decode_part(msg)
            if ctype == 'text/plain':
                plains.append(text)
            else:
                htmls.append(text)
    body = _pick_best_text(plains, htmls)
    body = re.sub('\\s{2,}', ' ', body).strip()
    return (body, attachments)

def extract_text_from_eml(raw: bytes) -> tuple[str, list[tuple[str, bytes]]]:
    """
    Extrai texto de um .eml (inclui mensagens aninhadas).
    Retorno: (texto, anexos_interessantes[ (filename, bytes) ])
    """
    msg = BytesParser(policy=policy.default).parsebytes(raw)
    return _walk_message(msg)
from email import policy
from email.message import Message
from email.parser import BytesParser
from bs4 import BeautifulSoup

def _html_to_text(html: str) -> str:
    try:
        soup = BeautifulSoup(html, 'html.parser')
        for tag in soup(['script', 'style', 'noscript']):
            tag.decompose()
        text = soup.get_text(separator=' ', strip=True)
        return re.sub('\\s{2,}', ' ', text).strip()
    except Exception:
        text = re.sub('<[^>]+>', ' ', html)
        return re.sub('\\s{2,}', ' ', text).strip()

def _decode_part(part: Message) -> str:
    try:
        content = part.get_content()
        if isinstance(content, bytes):
            content = content.decode(part.get_content_charset() or 'utf-8', errors='ignore')
        return content
    except Exception:
        payload = part.get_payload(decode=True) or b''
        try:
            return payload.decode(part.get_content_charset() or 'utf-8', errors='ignore')
        except Exception:
            return payload.decode('latin-1', errors='ignore')

def _pick_best_text(candidates_plain: list[str], candidates_html: list[str]) -> str:
    if candidates_plain:
        return max(candidates_plain, key=len).strip()
    if candidates_html:
        html = max(candidates_html, key=len)
        return _html_to_text(html)
    return ''

def _walk_message(msg: Message) -> tuple[str, list[tuple[str, bytes]]]:
    """
    Percorre recursivamente a mensagem (inclui message/rfc822).
    Retorna: (texto_corpo, anexos_interessantes[ (filename, bytes) ])
    """
    plains, htmls = ([], [])
    attachments = []
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = part.get_content_disposition()
            if ctype == 'message/rfc822':
                try:
                    nested = part.get_payload(0)
                except Exception:
                    nested = None
                if isinstance(nested, Message):
                    nested_text, nested_atts = _walk_message(nested)
                    if nested_text:
                        plains.append(nested_text)
                    attachments.extend(nested_atts)
            elif ctype in ('text/plain', 'text/html') and disp in (None, 'inline', 'attachment'):
                text = _decode_part(part)
                (plains if ctype == 'text/plain' else htmls).append(text)
            elif disp == 'attachment':
                filename = part.get_filename() or ''
                blob = part.get_payload(decode=True) or b''
                low = filename.lower()
                if low.endswith('.txt') or low.endswith('.pdf'):
                    attachments.append((filename, blob))
    else:
        ctype = msg.get_content_type()
        if ctype in ['text/plain', 'text/html']:
            text = _decode_part(msg)
            (plains if ctype == 'text/plain' else htmls).append(text)
    body = _pick_best_text(plains, htmls)
    body = re.sub('\\s{2,}', ' ', body).strip()
    return (body, attachments)

def extract_text_from_eml(raw: bytes) -> tuple[str, list[tuple[str, bytes]]]:
    """Extrai texto de um .eml (inclui mensagens aninhadas)."""
    msg = BytesParser(policy=policy.default).parsebytes(raw)
    return _walk_message(msg)