"""
Q2 — Token Linter
Detecta: hex hard-coded, tokens inexistentes, componentes sem ADR.
"""
import re, json, glob, sys
from pathlib import Path

ERRORS, WARNINGS = [], []
HEX_PATTERN = re.compile(r'#[0-9A-Fa-f]{6}(?:[0-9A-Fa-f]{2})?\b')
CSS_VAR_PATTERN = re.compile(r'var\(--ds-[a-z-]+\)')
COMMENT_PREFIXES = ("//", "*", "/*", "<!--", "#")

def flatten(data, prefix=""):
    result = []
    for key, value in data.items():
        full_key = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict) and "value" in value:
            result.append((full_key, value))
        elif isinstance(value, dict):
            result.extend(flatten(value, full_key))
    return result

def load_approved_tokens():
    approved = set()
    for f in glob.glob("tokens/**/*.json", recursive=True):
        with open(f) as fp: data = json.load(fp)
        for name, _ in flatten(data): approved.add(name)
    return approved

def check_tsx_files():
    for filepath in glob.glob("components/**/*.tsx", recursive=True):
        with open(filepath) as fp: lines = fp.readlines()
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if not stripped or any(stripped.startswith(p) for p in COMMENT_PREFIXES):
                continue
            code_part = line.split("//")[0]
            matches = HEX_PATTERN.findall(code_part)
            if matches:
                ERRORS.append({"file": filepath, "line": i,
                    "message": f"HEX hard-coded: {matches}",
                    "hint": "Use token semântico. Ex: var(--ds-color-action-primary)",
                    "code": "TOKEN_HARDCODE"})

def check_token_references():
    approved = load_approved_tokens()
    for filepath in glob.glob("components/**/*.tsx", recursive=True):
        with open(filepath) as fp: content = fp.read()
        for var in CSS_VAR_PATTERN.findall(content):
            token_name = var.replace("var(--ds-","").replace(")","").replace("-",".")
            if token_name not in approved:
                WARNINGS.append({"file": filepath,
                    "message": f"Token '{token_name}' não existe.",
                    "hint": "Crie em tokens/ ou corrija o nome.",
                    "code": "TOKEN_UNKNOWN"})

def check_adr_required():
    existing_adrs = set()
    for filepath in glob.glob("docs/adrs/*.md"):
        with open(filepath) as fp: content = fp.read()
        m = re.search(r"Componente:\s*(\w+)", content)
        if m: existing_adrs.add(m.group(1))
    for filepath in glob.glob("components/*/"):
        name = Path(filepath.rstrip("/")).name
        if name and name not in existing_adrs:
            WARNINGS.append({"file": filepath,
                "message": f"Componente '{name}' sem ADR.",
                "hint": "Execute: python scripts/adr_generator.py",
                "code": "ADR_MISSING"})

def main():
    print("🔍 Q2 — Token Linter iniciando...\n")
    check_tsx_files()
    check_token_references()
    check_adr_required()
    for w in WARNINGS:
        print(f"⚠️  [{w['code']}] {w.get('file','?')}\n   {w['message']}\n   💡 {w['hint']}\n")
    for e in ERRORS:
        print(f"❌ [{e['code']}] {e.get('file','?')} (linha {e.get('line','-')})\n   {e['message']}\n   💡 {e['hint']}\n")
    if ERRORS:
        print(f"BLOQUEADO: {len(ERRORS)} erro(s). Corrija antes de fazer merge.")
        sys.exit(1)
    else:
        print(f"✅ Aprovado. {len(WARNINGS)} aviso(s), 0 erros bloqueantes.")
        sys.exit(0)

if __name__ == "__main__":
    main()
