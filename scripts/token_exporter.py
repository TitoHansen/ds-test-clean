"""
Token Exporter -- gera CSS custom properties a partir dos tokens do DS.
Resolve aliases semanticos para var() CSS.
Usado por GET /api/tokens.css
"""
import glob, json
from pathlib import Path

BASE = Path(__file__).parent.parent


def _flatten(data: dict, prefix: str = "") -> dict:
    result = {}
    for key, value in data.items():
        full_key = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict) and "value" in value:
            result[full_key] = value
        elif isinstance(value, dict):
            result.update(_flatten(value, full_key))
    return result


def _css_var(path: str) -> str:
    return "--ds-" + path.replace(".", "-")


def _resolve(ref: str, prim_map: dict) -> str:
    """Resolve {spacing.4} -> 16px usando primitivos."""
    if isinstance(ref, str) and ref.startswith("{") and ref.endswith("}"):
        prim_path = ref[1:-1]
        meta = prim_map.get(prim_path)
        if meta:
            return str(meta["value"])
    return str(ref)


def export_css() -> str:
    """Retorna string CSS com todos os tokens como custom properties."""
    prim_map, sem_map = {}, {}
    for f in glob.glob(str(BASE / "tokens" / "primitive" / "*.json")):
        prim_map.update(_flatten(json.load(open(f))))
    for f in glob.glob(str(BASE / "tokens" / "semantic" / "*.json")):
        sem_map.update(_flatten(json.load(open(f))))

    lines = ["/* Design System Tokens -- auto-generated */", ":root {", "  /* === Primitivos === */"]

    for path, meta in sorted(prim_map.items()):
        lines.append(f"  {_css_var(path)}: {meta['value']};")

    lines.append("")
    lines.append("  /* === Semanticos === */")

    for path, meta in sorted(sem_map.items()):
        ref = meta.get("value", "")
        if isinstance(ref, str) and ref.startswith("{") and ref.endswith("}"):
            prim_path = ref[1:-1]
            value = f"var({_css_var(prim_path)})"
        else:
            value = str(ref)
        lines.append(f"  {_css_var(path)}: {value};")

    lines.append("}")
    return "\n".join(lines)


if __name__ == "__main__":
    print(export_css())
