"""
Figma Pusher -- sincroniza tokens do DS como Figma Variables.

REST API (Professional+): POST /v1/files/{key}/variables
Plugin JS  (Free/qualquer): snippet para colar no console do Figma
"""
import os, json, glob, uuid, re
import urllib.request, urllib.error
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
BASE = Path(__file__).parent.parent
FIGMA_API = "https://api.figma.com/v1"


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
    h = hex_val.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return {"r": round(r/255,4), "g": round(g/255,4), "b": round(b/255,4), "a": 1.0}


def _load_tokens() -> tuple:
    primitives, semantics = {}, {}
    for f in glob.glob(str(BASE / "tokens" / "primitive" / "*.json")):
        primitives.update(_flatten(json.load(open(f))))
    for f in glob.glob(str(BASE / "tokens" / "semantic" / "*.json")):
        semantics.update(_flatten(json.load(open(f))))
    return primitives, semantics


def _temp_id() -> str:
    return "temp_" + uuid.uuid4().hex[:12]


def _figma_type(value: str) -> str:
    if isinstance(value, str) and value.startswith("#"):
        return "COLOR"
    if isinstance(value, str) and re.match(r"^[0-9]+\.?[0-9]*(px|em|rem)?$", value.strip()):
        return "FLOAT"
    return "STRING"


def _js_value(value: str, vtype: str) -> str:
    if vtype == "COLOR":
        rgb = _hex_to_figma(value)
        return "{r:" + str(rgb["r"]) + ",g:" + str(rgb["g"]) + ",b:" + str(rgb["b"]) + ",a:1}"
    if vtype == "FLOAT":
        return re.sub(r"[a-z%]+$", "", value.strip())
    return json.dumps(str(value))


# ---------------------------------------------------------------------------
# REST API (Professional+)
# ---------------------------------------------------------------------------

def _figma_post(path: str, payload: dict) -> dict:
    token = os.getenv("FIGMA_TOKEN", "")
    if not token:
        raise ValueError("FIGMA_TOKEN nao definido no .env")
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
        raise RuntimeError(f"Figma API {e.code}: {e.read().decode()[:300]}") from e


def push_tokens(file_key: str) -> dict:
    """Sincroniza tokens de COR via REST API (requer Professional+)."""
    primitives, semantics = _load_tokens()
    prim_coll_id = _temp_id(); prim_mode_id = _temp_id()
    sem_coll_id  = _temp_id(); sem_mode_id  = _temp_id()

    variable_collections = [
        {"action":"CREATE","id":prim_coll_id,"name":"DS / Primitivos","initialModeId":prim_mode_id},
        {"action":"CREATE","id":sem_coll_id, "name":"DS / Semanticos", "initialModeId":sem_mode_id},
    ]
    variable_modes = [
        {"action":"CREATE","id":prim_mode_id,"variableCollectionId":prim_coll_id,"name":"Default"},
        {"action":"CREATE","id":sem_mode_id, "variableCollectionId":sem_coll_id, "name":"Default"},
    ]
    variables, variable_mode_values, prim_id_map = [], [], {}

    for path, meta in primitives.items():
        raw = meta.get("value","")
        if not (isinstance(raw,str) and raw.startswith("#")): continue
        var_id = _temp_id(); prim_id_map[path] = var_id
        variables.append({"action":"CREATE","id":var_id,"name":path.replace(".","/"),
                           "variableCollectionId":prim_coll_id,"resolvedType":"COLOR"})
        variable_mode_values.append({"variableId":var_id,"modeId":prim_mode_id,"value":_hex_to_figma(raw)})

    unmapped = []
    for path, meta in semantics.items():
        ref = meta.get("value","")
        if not (isinstance(ref,str) and ref.startswith("{") and ref.endswith("}")): unmapped.append(path); continue
        prim_path = ref[1:-1]
        if prim_path not in prim_id_map: unmapped.append(path); continue
        var_id = _temp_id()
        variables.append({"action":"CREATE","id":var_id,"name":path.replace(".","/"),
                           "variableCollectionId":sem_coll_id,"resolvedType":"COLOR"})
        variable_mode_values.append({"variableId":var_id,"modeId":sem_mode_id,
                                      "value":{"type":"VARIABLE_ALIAS","id":prim_id_map[prim_path]}})

    result = _figma_post(f"/files/{file_key}/variables", {
        "variableCollections":variable_collections,"variableModes":variable_modes,
        "variables":variables,"variableModeValues":variable_mode_values,
    })
    return {
        "collections_created": len(result.get("meta",{}).get("variableCollections",{})),
        "variables_created":   len(result.get("meta",{}).get("variables",{})),
        "primitives": len(prim_id_map), "semantics": len(semantics)-len(unmapped),
        "unmapped": unmapped, "figma_file": f"https://figma.com/file/{file_key}",
    }


# ---------------------------------------------------------------------------
# Plugin JS (Free / qualquer plano)  — suporta COLOR, FLOAT e STRING
# ---------------------------------------------------------------------------

def push_tokens_plugin_js() -> str:
    """
    Gera snippet JS com TODOS os tokens (cor, spacing, tipografia, border, shadow).
    COLOR -> cores hex, FLOAT -> numeros (px removido), STRING -> texto.
    Cole em: Plugins > Development > Open Console > Enter
    """
    primitives, semantics = _load_tokens()

    prim_lines = []
    prim_meta = {}  # path -> (js_var, vtype)

    for i, (path, meta) in enumerate(primitives.items()):
        raw = meta.get("value", "")
        if not isinstance(raw, str) or not raw:
            continue
        vtype  = _figma_type(raw)
        js_var = "p" + str(i)
        prim_meta[path] = (js_var, vtype)
        name_js = json.dumps(path.replace(".", "/"))
        val_js  = _js_value(raw, vtype)
        prim_lines.append(
            '  var ' + js_var + ' = figma.variables.createVariable('
            + name_js + ', primColl, "' + vtype + '");\n'
            + '  ' + js_var + '.setValueForMode(primMode, ' + val_js + ');'
        )

    sem_lines = []
    for i, (path, meta) in enumerate(semantics.items()):
        ref = meta.get("value", "")
        if not (isinstance(ref, str) and ref.startswith("{") and ref.endswith("}")):
            continue
        prim_path = ref[1:-1]
        if prim_path not in prim_meta:
            continue
        js_prim_var, prim_vtype = prim_meta[prim_path]
        name_js = json.dumps(path.replace(".", "/"))
        sem_lines.append(
            '  var s' + str(i) + ' = figma.variables.createVariable('
            + name_js + ', semColl, "' + prim_vtype + '");\n'
            + '  s' + str(i) + '.setValueForMode(semMode, '
            + 'figma.variables.createVariableAlias(' + js_prim_var + '));'
        )

    n_prim = len(prim_lines)
    n_sem  = len(sem_lines)

    return (
        "// Design System -- Sincronizar Tokens como Figma Variables\n"
        "// Funciona em qualquer plano (Free incluso)\n"
        "// Cole em: Plugins > Development > Open Console > Enter\n"
        "(async () => {\n"
        '  var primColl = figma.variables.createVariableCollection("DS / Primitivos");\n'
        "  var primMode = primColl.defaultModeId;\n\n"
        + "\n".join(prim_lines) + "\n\n"
        '  var semColl = figma.variables.createVariableCollection("DS / Semanticos");\n'
        "  var semMode = semColl.defaultModeId;\n\n"
        + "\n".join(sem_lines) + "\n\n"
        '  figma.notify("' + str(n_prim) + ' primitivos + ' + str(n_sem) + ' semanticos criados!");\n'
        '  console.log("Tokens sincronizados.");\n'
        "})();"
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        print(json.dumps(push_tokens(sys.argv[1]), ensure_ascii=False, indent=2))
    else:
        print(push_tokens_plugin_js())
