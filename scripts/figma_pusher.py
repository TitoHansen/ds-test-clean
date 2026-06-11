"""
Figma Pusher — sincroniza tokens do DS como Figma Variables via REST API.

Cria duas coleções no arquivo Figma:
  - "DS / Primitivos"  → valores hex brutos  (color/blue/500)
  - "DS / Semânticos"  → aliases dos primitivos (color/action/primary)

Requer: FIGMA_TOKEN com escopo file_variables:write
        Plano Figma Professional ou superior (Variables API)
"""
import os, json, glob, uuid
import urllib.request, urllib.error
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
BASE = Path(__file__).parent.parent
FIGMA_API = "https://api.figma.com/v1"


# ─── helpers ────────────────────────────────────────────────────────────────

def _flatten(data: dict, prefix: str = "") -> dict:
    result = {}
    for key, value in data.items():
        full_key = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict) and "value" in value:
            result[full_key] = value
        elif isinstance(value, dict):
            result.update(_flatten(value, full_key))
    return result


def _hex_to_figma(hex_val: str) -> dict:
    """'#2563EB' → {'r': 0.145, 'g': 0.388, 'b': 0.922, 'a': 1}"""
    h = hex_val.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return {"r": round(r / 255, 4), "g": round(g / 255, 4),
            "b": round(b / 255, 4), "a": 1.0}


def _figma_post(path: str, payload: dict) -> dict:
    token = os.getenv("FIGMA_TOKEN", "")
    if not token:
        raise ValueError("FIGMA_TOKEN não definido no .env")
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{FIGMA_API}{path}", data=body,
        headers={"X-Figma-Token": token, "Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body_err = e.read().decode()
        raise RuntimeError(f"Figma API {e.code}: {body_err[:300]}") from e


def _load_tokens() -> tuple:
    """Retorna (primitivos, semânticos) como dicts de {dotted.path: meta}."""
    primitives, semantics = {}, {}
    for f in glob.glob(str(BASE / "tokens" / "primitive" / "*.json")):
        primitives.update(_flatten(json.load(open(f))))
    for f in glob.glob(str(BASE / "tokens" / "semantic" / "*.json")):
        semantics.update(_flatten(json.load(open(f))))
    return primitives, semantics


def _temp_id() -> str:
    return f"temp_{uuid.uuid4().hex[:12]}"


# ─── API pública ─────────────────────────────────────────────────────────────

def push_tokens(file_key: str) -> dict:
    """
    Sincroniza tokens do DS como Figma Variables no arquivo especificado.

    Retorna um resumo: { collections_created, variables_created, primitives,
                         semantics, unmapped, figma_file }
    """
    primitives, semantics = _load_tokens()

    prim_coll_id = _temp_id()
    prim_mode_id = _temp_id()
    sem_coll_id  = _temp_id()
    sem_mode_id  = _temp_id()

    variable_collections = [
        {"action": "CREATE", "id": prim_coll_id,
         "name": "DS / Primitivos", "initialModeId": prim_mode_id},
        {"action": "CREATE", "id": sem_coll_id,
         "name": "DS / Semânticos", "initialModeId": sem_mode_id},
    ]
    variable_modes = [
        {"action": "CREATE", "id": prim_mode_id,
         "variableCollectionId": prim_coll_id, "name": "Default"},
        {"action": "CREATE", "id": sem_mode_id,
         "variableCollectionId": sem_coll_id, "name": "Default"},
    ]

    variables = []
    variable_mode_values = []
    prim_id_map: dict = {}

    # Primitivos
    for path, meta in primitives.items():
        raw = meta.get("value", "")
        if not (isinstance(raw, str) and raw.startswith("#")):
            continue
        var_id = _temp_id()
        prim_id_map[path] = var_id
        variables.append({
            "action": "CREATE", "id": var_id,
            "name": path.replace(".", "/"),
            "variableCollectionId": prim_coll_id,
            "resolvedType": "COLOR",
        })
        variable_mode_values.append({
            "variableId": var_id,
            "modeId": prim_mode_id,
            "value": _hex_to_figma(raw),
        })

    # Semânticos — alias para primitivos
    unmapped = []
    for path, meta in semantics.items():
        ref = meta.get("value", "")
        if isinstance(ref, str) and ref.startswith("{") and ref.endswith("}"):
            prim_path = ref[1:-1]
        else:
            unmapped.append(path)
            continue
        if prim_path not in prim_id_map:
            unmapped.append(path)
            continue
        var_id = _temp_id()
        variables.append({
            "action": "CREATE", "id": var_id,
            "name": path.replace(".", "/"),
            "variableCollectionId": sem_coll_id,
            "resolvedType": "COLOR",
        })
        variable_mode_values.append({
            "variableId": var_id,
            "modeId": sem_mode_id,
            "value": {"type": "VARIABLE_ALIAS", "id": prim_id_map[prim_path]},
        })

    payload = {
        "variableCollections": variable_collections,
        "variableModes":       variable_modes,
        "variables":           variables,
        "variableModeValues":  variable_mode_values,
    }

    result = _figma_post(f"/files/{file_key}/variables", payload)
    created_vars  = result.get("meta", {}).get("variables", {})
    created_colls = result.get("meta", {}).get("variableCollections", {})

    return {
        "collections_created": len(created_colls),
        "variables_created":   len(created_vars),
        "primitives":          len(prim_id_map),
        "semantics":           len(semantics) - len(unmapped),
        "unmapped":            unmapped,
        "figma_file":          f"https://figma.com/file/{file_key}",
    }


# ─── CLI ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Uso: python scripts/figma_pusher.py <file_key>")
        sys.exit(1)
    result = push_tokens(sys.argv[1])
    print(json.dumps(result, ensure_ascii=False, indent=2))
