"""
Figma Reader — extrai propriedades de design de um node via Figma REST API.
Dependência de POST /api/from-figma.

Retorna cores (hex), tipografia, layout e efeitos prontos para o token_mapper.
Requer: FIGMA_TOKEN no .env (Personal Access Token ou OAuth token do Figma).
"""
import os
import urllib.request
import urllib.parse
import urllib.error
import json
from dotenv import load_dotenv

load_dotenv()

FIGMA_API = "https://api.figma.com/v1"


# ---------------------------------------------------------------------------
# Helpers de conversão
# ---------------------------------------------------------------------------

def _rgba_to_hex(r: float, g: float, b: float) -> str:
    """Converte cor Figma (0-1 float) para hex maiúsculo: '#2563EB'."""
    return "#{:02X}{:02X}{:02X}".format(
        round(r * 255), round(g * 255), round(b * 255)
    )


def _figma_get(path: str) -> dict:
    token = os.getenv("FIGMA_TOKEN", "")
    if not token:
        raise ValueError("FIGMA_TOKEN não definido no .env")
    url = f"{FIGMA_API}{path}"
    req = urllib.request.Request(url, headers={"X-Figma-Token": token})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        raise RuntimeError(f"Figma API {e.code}: {body[:200]}") from e


# ---------------------------------------------------------------------------
# Extratores de propriedades
# ---------------------------------------------------------------------------

def _extract_colors(node: dict) -> list:
    """Extrai fills e strokes como lista de {'role', 'hex', 'opacity'}."""
    colors = []
    for role, key in [("fill", "fills"), ("stroke", "strokes")]:
        for paint in node.get(key, []):
            if paint.get("type") == "SOLID" and paint.get("visible", True):
                c = paint.get("color", {})
                colors.append({
                    "role": role,
                    "hex": _rgba_to_hex(c.get("r", 0), c.get("g", 0), c.get("b", 0)),
                    "opacity": round(paint.get("opacity", 1.0), 3),
                })
    return colors


def _extract_typography(node: dict) -> dict:
    """Extrai propriedades tipográficas de nodes TEXT ou style herdado."""
    style = node.get("style", {})
    if not style:
        return {}
    result = {}
    for key in ("fontFamily", "fontSize", "fontWeight",
                "lineHeightPx", "letterSpacing", "textAlignHorizontal",
                "textDecoration", "textCase", "italic"):
        if key in style:
            result[key] = style[key]
    return result


def _extract_layout(node: dict) -> dict:
    """Extrai dimensões, padding, cornerRadius e layoutMode."""
    layout = {}
    bbox = node.get("absoluteBoundingBox") or node.get("size")
    if bbox:
        layout["width"] = round(bbox.get("width", 0))
        layout["height"] = round(bbox.get("height", 0))

    for key in ("paddingTop", "paddingRight", "paddingBottom", "paddingLeft",
                "itemSpacing", "cornerRadius", "layoutMode",
                "primaryAxisAlignItems", "counterAxisAlignItems"):
        if key in node:
            layout[key] = node[key]

    # cornerRadius por canto
    radii = node.get("rectangleCornerRadii")
    if radii:
        layout["cornerRadii"] = radii

    return layout


def _extract_effects(node: dict) -> list:
    """Extrai sombras e blur como lista estruturada."""
    effects = []
    for fx in node.get("effects", []):
        if not fx.get("visible", True):
            continue
        entry = {"type": fx.get("type")}
        if "color" in fx:
            c = fx["color"]
            entry["color"] = _rgba_to_hex(c.get("r", 0), c.get("g", 0), c.get("b", 0))
            entry["color_opacity"] = round(c.get("a", 1.0), 3)
        for key in ("offset", "radius", "spread"):
            if key in fx:
                entry[key] = fx[key]
        effects.append(entry)
    return effects


def _extract_node(node: dict, depth: int = 0) -> dict:
    """Extrai todas as propriedades relevantes de um node (recursivo até depth 2)."""
    colors = _extract_colors(node)
    result = {
        "node_id": node.get("id"),
        "node_type": node.get("type"),
        "name": node.get("name"),
        "colors": colors,
        "raw_hex_values": list(dict.fromkeys(c["hex"] for c in colors)),
        "typography": _extract_typography(node),
        "layout": _extract_layout(node),
        "effects": _extract_effects(node),
    }

    # Texto literal em nodes do tipo TEXT
    if node.get("type") == "TEXT":
        result["text_content"] = node.get("characters", "")

    # Extrai children até profundidade 2 (frame/component interno)
    if depth < 2:
        children = []
        for child in node.get("children", []):
            extracted = _extract_node(child, depth + 1)
            children.append(extracted)
            # Agrega hex dos filhos no nível raiz
            for h in extracted["raw_hex_values"]:
                if h not in result["raw_hex_values"]:
                    result["raw_hex_values"].append(h)
        if children:
            result["children"] = children

    return result


# ---------------------------------------------------------------------------
# Função pública principal
# ---------------------------------------------------------------------------

def read_node(file_key: str, node_id: str) -> dict:
    """
    Lê um node do Figma e retorna propriedades estruturadas.

    Args:
        file_key: ID do arquivo Figma (da URL: figma.com/file/<file_key>/...)
        node_id:  ID do node (da URL: ?node-id=<node_id>, com ':' ou '-')

    Returns dict com: node_id, node_type, name, colors, raw_hex_values,
                      typography, layout, effects, children (até 2 níveis)
    """
    # Figma aceita node_id com ':' ou '-'; normaliza para ':'
    normalized_id = node_id.replace("-", ":")
    encoded_id = urllib.parse.quote(normalized_id, safe="")

    data = _figma_get(f"/files/{file_key}/nodes?ids={encoded_id}")

    nodes = data.get("nodes", {})
    # A API retorna a chave com o id original ou normalizado
    node_data = nodes.get(normalized_id) or nodes.get(node_id)
    if not node_data:
        available = list(nodes.keys())[:5]
        raise ValueError(
            f"Node '{node_id}' não encontrado. Disponíveis: {available}"
        )

    document_node = node_data.get("document", {})
    return _extract_node(document_node)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Uso: python scripts/figma_reader.py <file_key> <node_id>")
        print("Ex:  python scripts/figma_reader.py ABC123xyz 123:456")
        sys.exit(1)

    result = read_node(sys.argv[1], sys.argv[2])
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"\n📐 Cores encontradas: {result['raw_hex_values']}")
    print(f"📝 Tipografia: {result['typography']}")
    print(f"📦 Layout: {result['layout']}")
