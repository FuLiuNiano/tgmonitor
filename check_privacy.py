"""Check an explicit publish manifest without printing sensitive matches."""
import ipaddress
import json
import re
from pathlib import Path


def audit(root):
    paths = json.loads((root / 'publish_manifest.json').read_text(encoding='utf-8'))
    findings = []
    ipv4 = re.compile(r'(?<![\w.])(?:[0-9]{1,3}\.){3}[0-9]{1,3}(?![\w.])')
    patterns = {
        'private-key': re.compile(r'-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----'),
        'github-token': re.compile(r'\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{30,})\b'),
        'local-user-path': re.compile(r'[A-Za-z]:[\\/](?:Users|zcode)', re.I),
        'server-hostname': re.compile(r'\bser[0-9]{9,}\b'),
        'phone': re.compile(r'\+86[0-9]{11}\b'),
        'url-password': re.compile(r'https?://[^\s/]+:[^\s/]+@'),
    }
    for name in paths:
        path = root / name
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()) or not path.is_file():
            findings.append((name, 'invalid-path'))
            continue
        if name.endswith(('.zip', '.session', '.db', '.log', '.bak')) or name in {'.env', 'config.json'}:
            findings.append((name, 'runtime-file'))
            continue
        text = path.read_text(encoding='utf-8')
        for category, pattern in patterns.items():
            if pattern.search(text):
                findings.append((name, category))
        for match in ipv4.finditer(text):
            try:
                address = ipaddress.ip_address(match.group())
                if not (address.is_loopback or address.is_unspecified):
                    findings.append((name, 'non-local-network-address'))
            except ValueError:
                pass
        if name == '.env.example':
            for line in text.splitlines():
                if line.startswith(('TG_API_ID=', 'TG_API_HASH=', 'TG_PHONE=', 'TG_PROXY=', 'QQ_BOT_TOKEN=')) and line.split('=', 1)[1].strip():
                    findings.append((name, 'nonempty-example-credential'))
        if name == 'config.example.json':
            example = json.loads(text)
            if example.get('channels') or example.get('qq', {}).get('user_id'):
                findings.append((name, 'nonempty-example-recipient'))
    return paths, findings


if __name__ == '__main__':
    root = Path(__file__).resolve().parent
    paths, findings = audit(root)
    if findings:
        for path, category in findings:
            print(f'{path}: {category}')
        raise SystemExit(1)
    print(f'Privacy checks passed for {len(paths)} allowlisted source files.')
