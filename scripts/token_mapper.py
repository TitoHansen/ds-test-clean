"""
Token Mapper — resolve hex hard-coded → token semântico CSS var.
Dependência de /api/transform e /api/from-figma.

Fluxo:
  1. Carrega tokens primitivos (hex → token_path)
  2. Carrega tokens semânticos (token_path → css_var)
  3. map_hex(hex) retorna o CSS var mais específico (semântico > primitivo)
"""
import json
import glob
import re
from pathlib import Path
from typing import Optional

BASE = Path(__file__).parent.parent

HEX_RE = re.compile(r"#[0-9A-Fa-f]{6}(?:[0-9A-Fa-f]{2})?\b")


def _flatten(data: dict, prefix: str = "") -> dict:
    """Achata JSON de tokens em {dotted.path: value_dict}."""
    result = {}
    for key, value in data.items():
        full_key = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict) and "value" in value:
            result[full_key] = value
        elif isinstance(value, dict):
            result.update(_flatten(value, full_key))
    return result


def _css_var(token_path: str) -> str:
    """color.action.primary → var(--ds-color-action-primary)"""
    return "var(--ds-" + token_path.replace(".", "-") + ")"


def _load_tokens() -> tuple[dict, dict]:
    """
    Returns:
      hex_to_primitives: { "#2563EB": ["color.blue.500", ...] }
      path_to_semantic:  { "color.blue.500": "color.action.primary" }
    """
    hex_to_primitives: dict = {}
    path_to_semantic: dict = {}

    # Primitivos — arquivos em tokens/primitive/
    for f in glob.glob(str(BASE / "tokens" / "primitive" / "*.json")):
        with open(f) as fp:
            tokens = _flatten(json.load(fp))
        for path, meta in tokens.items():
            raw = meta["value"]
            if isinstance(raw, str) and raw.startswith("#"):
                norm = raw.upper()
                hex_to_primitives.setdefault(norm, []).append(path)

    # Semânticos — arquivos em tokens/semantic/
    for f in glob.glob(str(BASE / "tokens" / "semantic" / "*.json")):
        with open(f) as fp:
            tokens = _flatten(json.load(fp))
        for sem_path, meta in tokens.items():
            ref = meta["value"]
            # Resolve referências do tipo {color.blue.500}
            if isinstance(ref, str) and ref.startswith("{") and ref.endswith("}"):
                prim_path = ref[1:-1]
                path_to_semantic[prim_path] = sem_path

    return hex_to_primitives, path_to_semantic


# Cache em memória — recarregado se chamado pela primeira vez
_cache: Optional[tuple] = None


def _get_cache() -> tuple:
    global _cache
    if _cache is None:
        _cache = _load_tokens()
    return _cache


def reload():
    """Força recarga dos tokens (útil após ingest)."""
    global _cache
    _cache = _load_tokens()


def map_hex(hex_value: str) -> dict:
    """
    Dado um valor hex, retorna o token mais adequado.

    Returns dict:
      {
        "hex": "#2563EB",
        "primitive": "color.blue.500",
        "semantic": "color.action.primary",   # None se não houver
        "css_var": "var(--ds-color-action-primary)",  # prefere semântico
        "found": True
      }
    """
    norm = hex_value.upper()
    if not norm.startswith("#"):
        norm = "#" + norm

    hex_to_primitives, path_to_semantic = _get_cache()
    prims = hex_to_primitives.get(norm, [])

    if not prims:
        return {"hex": hex_value, "primitive": None, "semantic": None,
                "css_var": None, "found": False}

    # Prefere o primitivo que tem mapeamento semântico
    primitive = prims[0]
    semantic = None
    for p in prims:
        if p in path_to_semantic:
            primitive = p
            semantic = path_to_semantic[p]
            break

    css_var = _css_var(semantic) if semantic else _css_var(primitive)
    return {"hex": hex_value, "primitive": primitive, "semantic": semantic,
            "css_var": css_var, "found": True}


def map_all_hex(code: str) -> dict:
    """
    Encontra todos os hex em `code` e retorna mapeamento + código substituído.

    Returns dict:
      {
        "mapped":   [{"hex": ..., "css_var": ..., ...}],
        "unmapped": ["#AABBCC", ...],
        "code":     "<código com substituições aplicadas>"
      }
    """
    hits = list(dict.fromkeys(HEX_RE.findall(code)))  # preserva ordem, deduplica
    mapped = []
    unmapped = []
    result_code = code

    for h in hits:
        info = map_hex(h)
        if info["found"]:
            mapped.append(info)
            result_code = re.sub(re.escape(h), info["css_var"], result_code,
                                 flags=re.IGNORECASE)
        else:
            unmapped.append(h)

    return {"mapped": mapped, "unmapped": unmapped, "code": result_code}


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Uso: python scripts/token_mapper.py <#HEX>")
        print("     python scripts/token_mapper.py --list")
        sys.exit(1)

    if sys.argv[1] == "--list":
        h2p, p2s = _get_cache()
        print(f"Primitivos: {len(h2p)} hex únicos")
        print(f"Semânticos: {len(p2s)} mapeamentos\n")
        for h, paths in h2p.items():
            for p in paths:
                sem = p2s.get(p)
                css = _css_var(sem) if sem else _css_var(p)
                print(f"  {h}  →  {css}")
    else:
        result = map_hex(sys.argv[1])
        if result["found"]:
            print(f"✅ {result['hex']} → {result['css_var']}")
            print(f"   primitivo: {result['primitive']}")
            if result["semantic"]:
                print(f"   semântico: {result['semantic']}")
        else:
            print(f"❌ {result['hex']} não encontrado nos tokens")
            sys.exit(1)
