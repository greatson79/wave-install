"""Pure text filtering for the macOS installer help client (no I/O)."""
import re


def safe_text(text, username=''):
    """Redact API-contract credentials/accounts before serializing any report."""
    text = re.sub(r'\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)', '', text)
    text = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', text)
    text = re.sub(r'[\x00-\x08\x0b-\x1f\x7f]', '', text)
    rules = (
        (r'[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9-]{1,63}(?:\.[A-Za-z0-9-]{1,63})*\.[A-Za-z]{2,63}', '<EMAIL>'),
        (r'(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+', '<TOKEN>'),
        (r'\bsk-[A-Za-z0-9_-]{8,}', '<TOKEN>'),
        (r'\b(?:gh[pousr]_|github_pat_)[A-Za-z0-9_]{20,}', '<TOKEN>'),
        (r'\b[A-Za-z0-9_-]{20,}#[A-Za-z0-9_-]{8,}\b', '<LOGIN_CODE>'),
        (r'(?im)(Paste code here if prompted\s*>)[^\n]*', r'\1 <LOGIN_CODE>'),
        (r'(?i)[A-Za-z]:[\\/]+Users[\\/]+[^\\/\s]+', r'C:\\Users\\<USER>'),
        (r'/(?:Users|home)/[^/\s]+', '/Users/<USER>'),
        (r'(?im)((?:USERNAME\s*=|whoami\s*:)\s*)[^\n]*', r'\1<USER>'),
    )
    for index, (pattern, replacement) in enumerate(rules):
        if index == 6 and username:
            text = re.sub(r'(?<!\w)' + re.escape(username) + r'(?!\w)', '<USER>', text, flags=re.I)
        text = re.sub(pattern, replacement, text)
    return text
