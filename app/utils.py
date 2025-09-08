import re
URL_RE = re.compile('https?://\\S+', re.I)
EMAIL_RE = re.compile('[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}', re.I)
MULTISPACE_RE = re.compile('\\s{2,}')

def truncate(text: str, max_chars: int=4000) -> str:
    return text if len(text) <= max_chars else text[:max_chars] + '…'