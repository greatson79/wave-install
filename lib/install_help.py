"""Pure text filtering for the macOS installer help client (no I/O)."""
import re

# Same rules, same order as ConvertTo-HelpSafeText in lib/install-help.ps1 (parity tested).
# Vendor-prefixed tokens are matched even when glued to preceding word characters.
RULES = (
    (r'[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9-]{1,63}(?:\.[A-Za-z0-9-]{1,63})*\.[A-Za-z]{2,63}', '<EMAIL>'),
    (r'(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+', '<TOKEN>'),
    (r'(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{8,}|sk-[A-Za-z0-9_-]{20,}', '<TOKEN>'),
    (r'(?:gh[pousr]_|github_pat_)[A-Za-z0-9_]{20,}', '<TOKEN>'),
    (r'AIza[0-9A-Za-z_-]{35}', '<TOKEN>'),
    (r'xox[abprs]-[0-9A-Za-z-]{10,}', '<TOKEN>'),
    (r'npm_[A-Za-z0-9]{36}', '<TOKEN>'),
    (r'(?:AKIA|ASIA)[0-9A-Z]{16}', '<TOKEN>'),
    (r'eyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}', '<TOKEN>'),
    (r'(?i)((?<![A-Za-z0-9])[A-Za-z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD|PASSWD)["\']?\s*[=:]\s*["\']?)[^\s"\',;}]+', r'\1<SECRET>'),
    (r'\b[A-Za-z0-9_-]{20,}#[A-Za-z0-9_-]{8,}\b', '<LOGIN_CODE>'),
    (r'(?im)(Paste code here if prompted\s*>)[^\n]*', r'\1 <LOGIN_CODE>'),
    None,  # current login name (literal) goes here, before the profile-path rules
    # Profile folders may contain spaces and differ from the login name: up to the next separator first.
    (r'(?i)[A-Za-z]:[\\/]+Users[\\/]+[^\\/\n"\'|:*?]{1,64}?(?=[\\/])', r'C:\\Users\\<USER>'),
    (r'(?i)[A-Za-z]:[\\/]+Users[\\/]+[^\\/\s]+', r'C:\\Users\\<USER>'),
    (r'/(?:Users|home)/[^/\n"\'|:*?]{1,64}?(?=/)', '/Users/<USER>'),
    (r'/(?:Users|home)/[^/\s]+', '/Users/<USER>'),
    (r'(?im)((?:USERNAME\s*=|whoami\s*:)\s*)[^\n]*', r'\1<USER>'),
)


def safe_text(text, username=''):
    """Redact API-contract credentials/accounts before serializing any report."""
    text = re.sub(r'\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)', '', text)
    text = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', text)
    text = re.sub(r'[\x00-\x08\x0b-\x1f\x7f]', '', text)
    for rule in RULES:
        if rule is None:
            if username:
                text = re.sub(r'(?<!\w)' + re.escape(username) + r'(?!\w)', '<USER>', text, flags=re.I)
            continue
        text = re.sub(rule[0], rule[1], text)
    return text
