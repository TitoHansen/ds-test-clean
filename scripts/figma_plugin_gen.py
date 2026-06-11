"""
Figma Plugin Generator — gera um snippet JavaScript (Figma Plugin API)
que o designer cola no console do Figma para criar o componente visualmente.

Fluxo:
  1. Extrai tokens CSS usados no TSX (var(--ds-*))
  2. Mapeia tokens → hex via token_mapper reverso
  3. Infere layout do TSX (padding, radius, direction)
  4. Gera JS que cria COMPONENT + AUTO LAYOUT + fills no Figma
"""
import re, json, glob
from pathlib import Path

CSS_VAR_RE = re.compile(r"var\(--ds-([a-z0-9-]+)\)")
PADDING_RE  = re.compile(r"padding[:\s]+([0-9]+)px\s+([0-9]+)px", re.IGNORECASE)
RADIUS_RE   = re.compile(r"border[Rr]adius[:\s\"']+([0-9]+)", re.IGNORECASE)
FLEX_DIR_RE = re.compile(r"flex[Dd]irection[:\s\"']+([a-z]+)", re.IGNORECASE)
WIDTH_RE    = re.compile(r"width[:\s\"']+([0-9]+)", re.IGNORECASE)
HEIGHT_RE   = re.compile(r"height[:\s\"']+([0-9]+)", re.IGNORECASE)
TEXT_RE     = re.compile(r">([A-Za-z][^<>{}\n]{1,40})<", re.IGNORECASE)
BASE        = Path(__file__).parent.parent


def _flatten_dash(data: dict, prefix: str = "") -> dict:
    """Achata JSON de tokens em {'color-blue-500': meta}."""
    result = {}
    for key, value in data.items():
        full_key = f"{prefix}-{key}" if prefix else key
        if isinstance(value, dict) and "value" in value:
            result[full_key] = value
        elif isinstance(value, dict):
            result.update(_flatten_dash(value, full_key))
    return result


def _token_to_hex_map() -> dict:
    """Constrói mapa reverso: 'color-action-primary' → '#2563EB'."""
    prim_flat, sem_flat = {}, {}
    for f in glob.glob(str(BASE / "tokens" / "primitive" / "*.json")):
        prim_flat.update(_flatten_dash(json.load(open(f))))
    for f in glob.glob(str(BASE / "tokens" / "semantic" / "*.json")):
        sem_flat.update(_flatten_dash(json.load(open(f))))

    hex_map = {k: v["value"] for k, v in prim_flat.items()
               if isinstance(v.get("value"), str) and v["value"].startswith("#")}

    for k, v in sem_flat.items():
        ref = v.get("value", "")
        if isinstance(ref, str) and ref.startswith("{") and ref.endswith("}"):
            prim_key = ref[1:-1].replace(".", "-")
            if prim_key in hex_map:
                hex_map[k] = hex_map[prim_key]
    return hex_map


def _hex_to_rgb(hex_val: str) -> dict:
    h = hex_val.lstrip("#")
    return {"r": round(int(h[0:2], 16) / 255, 4),
            "g": round(int(h[2:4], 16) / 255, 4),
            "b": round(int(h[4:6], 16) / 255, 4)}


def _extract_layout(tsx: str) -> dict:
    layout = {"paddingV": 8, "paddingH": 16, "radius": 4,
               "direction": "HORIZONTAL", "width": 0, "height": 0}
    m = PADDING_RE.search(tsx)
    if m:
        layout["paddingV"] = int(m.group(1))
        layout["paddingH"] = int(m.group(2))
    m = RADIUS_RE.search(tsx)
    if m:
        layout["radius"] = int(m.group(1))
    m = FLEX_DIR_RE.search(tsx)
    if m and "column" in m.group(1).lower():
        layout["direction"] = "VERTICAL"
    m = WIDTH_RE.search(tsx)
    if m:
        layout["width"] = int(m.group(1))
    m = HEIGHT_RE.search(tsx)
    if m:
        layout["height"] = int(m.group(1))
    return layout


def generate_plugin_js(component_name: str, tsx_code: str) -> str:
    """
    Retorna um snippet JS pronto para colar no console do Figma:
      Plugins → Development → Open Console → colar → Enter
    """
    hex_map  = _token_to_hex_map()
    layout   = _extract_layout(tsx_code)

    tokens_used = list(dict.fromkeys(CSS_VAR_RE.findall(tsx_code)))
    fills, strokes = [], []
    for tk in tokens_used:
        hx = hex_map.get(tk)
        if not hx:
            continue
        entry = {"token": tk, "hex": hx, "rgb": _hex_to_rgb(hx)}
        if any(x in tk for x in ("border", "stroke", "outline")):
            strokes.append(entry)
        elif not fills:
            fills.append(entry)

    texts = list(dict.fromkeys(TEXT_RE.findall(tsx_code)))[:3] or [component_name]

    fill_js = ""
    if fills:
        c = fills[0]["rgb"]
        fill_js = f"comp.fills = [{{type:'SOLID',color:{{r:{c['r']},g:{c['g']},b:{c['b']}}}}}];"

    stroke_js = ""
    if strokes:
        c = strokes[0]["rgb"]
        stroke_js = (f"comp.strokes = [{{type:'SOLID',color:{{r:{c['r']},g:{c['g']},b:{c['b']}}}}}];\n"
                     f"  comp.strokeWeight = 1; comp.strokeAlign = 'INSIDE';")

    size_js = (f"comp.resize({layout['width']}, {layout['height']});"
               if layout["width"] and layout["height"]
               else "comp.layoutSizingHorizontal = 'HUG'; comp.layoutSizingVertical = 'HUG';")

    texts_js = "\n".join(
        f"""  const t{i} = figma.createText();
  await figma.loadFontAsync({{family:'Inter',style:'Regular'}});
  t{i}.characters = {json.dumps(txt)};
  t{i}.fontSize = 14;
  comp.appendChild(t{i});"""
        for i, txt in enumerate(texts)
    )

    token_comments = "\n".join(f"  // {d['token']} → {d['hex']}" for d in fills + strokes)

    return f"""// ──────────────────────────────────────────────────────────
// Componente: {component_name}
// Gerado pelo Design System AI
// Cole em: Plugins → Development → Open Console → Enter
// ──────────────────────────────────────────────────────────
(async () => {{
  // Tokens mapeados:
{token_comments}

  const comp = figma.createComponent();
  comp.name = {json.dumps(component_name)};
  comp.layoutMode   = '{layout["direction"]}';
  comp.paddingTop   = {layout["paddingV"]};
  comp.paddingBottom= {layout["paddingV"]};
  comp.paddingLeft  = {layout["paddingH"]};
  comp.paddingRight = {layout["paddingH"]};
  comp.itemSpacing  = 8;
  comp.cornerRadius = {layout["radius"]};
  comp.clipsContent = true;
  {size_js}
  {fill_js}
  {stroke_js}

{texts_js}

  figma.currentPage.appendChild(comp);
  figma.viewport.scrollAndZoomIntoView([comp]);
  figma.notify('✅ {component_name} criado!');
}})();""".strip()


if __name__ == "__main__":
    import sys
    name = sys.argv[1] if len(sys.argv) > 1 else "Button"
    tsx  = open(sys.argv[2]).read() if len(sys.argv) > 2 else \
           f"<button style={{{{color:'var(--ds-color-action-primary)'}}}}>{name}</button>"
    print(generate_plugin_js(name, tsx))
