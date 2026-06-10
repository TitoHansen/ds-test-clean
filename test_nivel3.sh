#!/bin/bash
# ============================================================
# Nível 3 — Teste de Integração Figma
#
# Fases:
#   A) Funções puras do figma_reader — sem API, sem token
#   B) Pipeline completo com mock da API Figma
#   C) API real do Figma (requer FIGMA_TOKEN + variáveis de teste)
#   D) Endpoint POST /api/from-figma (requer servidor + Figma real)
#
# Para fase C e D, defina no .env ou exporte:
#   FIGMA_TOKEN=figd_...
#   TEST_FIGMA_FILE_KEY=<file_key>
#   TEST_FIGMA_NODE_ID=<node_id>   (formato 123:456 ou 123-456)
# ============================================================

PASS=0; FAIL=0
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'

ok()   { echo -e "  ${GREEN}✅ $1${NC}"; PASS=$((PASS+1)); }
fail() { echo -e "  ${RED}❌ $1${NC}"; FAIL=$((FAIL+1)); }
skip() { echo -e "  ${YELLOW}⏭  $1${NC}"; }
sep()  { echo ""; echo "──────────────────────────────────────"; }

echo "=================================================="
echo " TESTE NÍVEL 3 — Integração Figma"
echo "=================================================="

# Carrega .env se disponível
[ -f .env ] && export $(grep -v '^#' .env | xargs 2>/dev/null)

# ──────────────────────────────────────────────────────────
# FASE A — Funções puras (sem token, sem rede)
# ──────────────────────────────────────────────────────────
sep
echo "FASE A — Funções puras do figma_reader"
sep

python3 - << 'PYEOF'
import sys
sys.path.insert(0, '.')
from scripts.figma_reader import (
    _rgba_to_hex, _extract_colors, _extract_typography,
    _extract_layout, _extract_effects, _extract_node
)

errors = []

# _rgba_to_hex
cases = [
    ((0, 0, 0), "#000000"),
    ((1, 1, 1), "#FFFFFF"),
    ((0.145, 0.388, 0.922), "#2563EB"),
    ((0.114, 0.306, 0.847), "#1D4ED8"),
    ((0.953, 0.957, 0.965), "#F3F4F6"),
    ((0.067, 0.094, 0.153), "#111827"),
]
for (r, g, b), expected in cases:
    got = _rgba_to_hex(r, g, b)
    if got != expected:
        errors.append(f"_rgba_to_hex({r},{g},{b}) = {got}, want {expected}")
print("_rgba_to_hex:", "OK" if not [e for e in errors if "_rgba_to_hex" in e] else errors)

# _extract_colors — fill + stroke, invisible ignorado
node = {
    "fills":   [
        {"type": "SOLID", "visible": True,  "color": {"r": 0.145, "g": 0.388, "b": 0.922}, "opacity": 1.0},
        {"type": "SOLID", "visible": False, "color": {"r": 1.0,   "g": 0.0,   "b": 0.0},   "opacity": 1.0},
        {"type": "IMAGE"},
    ],
    "strokes": [{"type": "SOLID", "visible": True, "color": {"r": 0.114, "g": 0.306, "b": 0.847}, "opacity": 0.5}],
}
colors = _extract_colors(node)
assert len(colors) == 2, f"_extract_colors: expected 2, got {len(colors)}"
assert colors[0] == {"role": "fill",   "hex": "#2563EB", "opacity": 1.0}
assert colors[1] == {"role": "stroke", "hex": "#1D4ED8", "opacity": 0.5}
print("_extract_colors: OK")

# _extract_typography
node_text = {"style": {
    "fontFamily": "Inter", "fontSize": 14, "fontWeight": 500,
    "lineHeightPx": 20.0, "letterSpacing": 0.1,
}}
typo = _extract_typography(node_text)
assert typo["fontFamily"] == "Inter"
assert typo["fontSize"] == 14
assert typo["lineHeightPx"] == 20.0
assert _extract_typography({}) == {}
print("_extract_typography: OK")

# _extract_layout — bbox, padding, cornerRadius
node_frame = {
    "absoluteBoundingBox": {"width": 120.0, "height": 40.0},
    "paddingTop": 8, "paddingRight": 16, "paddingBottom": 8, "paddingLeft": 16,
    "cornerRadius": 4, "layoutMode": "HORIZONTAL",
    "itemSpacing": 8,
}
layout = _extract_layout(node_frame)
assert layout["width"] == 120
assert layout["height"] == 40
assert layout["paddingLeft"] == 16
assert layout["cornerRadius"] == 4
assert layout["layoutMode"] == "HORIZONTAL"
assert layout["itemSpacing"] == 8
# rectangleCornerRadii
node_radii = {"rectangleCornerRadii": [4, 4, 0, 0]}
assert _extract_layout(node_radii)["cornerRadii"] == [4, 4, 0, 0]
print("_extract_layout: OK")

# _extract_effects — shadow visível + shadow invisível
node_fx = {"effects": [
    {"type": "DROP_SHADOW", "visible": True,
     "color": {"r": 0, "g": 0, "b": 0, "a": 0.15},
     "offset": {"x": 0, "y": 2}, "radius": 4, "spread": 0},
    {"type": "DROP_SHADOW", "visible": False,
     "color": {"r": 1, "g": 0, "b": 0, "a": 1.0}},
]}
effects = _extract_effects(node_fx)
assert len(effects) == 1
assert effects[0]["type"] == "DROP_SHADOW"
assert effects[0]["color"] == "#000000"
assert effects[0]["color_opacity"] == 0.15
assert effects[0]["radius"] == 4
print("_extract_effects: OK")

# _extract_node — agrega hex dos filhos até depth 2
child2 = {
    "id": "3:1", "type": "TEXT", "name": "Label",
    "characters": "Click me",
    "style": {"fontFamily": "Inter", "fontSize": 14, "fontWeight": 500},
    "fills": [{"type": "SOLID", "visible": True,
               "color": {"r": 0.067, "g": 0.094, "b": 0.153}, "opacity": 1.0}],
}
child1 = {
    "id": "2:2", "type": "FRAME", "name": "Inner",
    "fills": [],
    "children": [child2],
}
root = {
    "id": "2:1", "type": "COMPONENT", "name": "Button/Primary",
    "fills": [{"type": "SOLID", "visible": True,
               "color": {"r": 0.145, "g": 0.388, "b": 0.922}, "opacity": 1.0}],
    "absoluteBoundingBox": {"width": 120.0, "height": 40.0},
    "paddingTop": 8, "paddingRight": 16, "paddingBottom": 8, "paddingLeft": 16,
    "cornerRadius": 4, "layoutMode": "HORIZONTAL",
    "children": [child1],
}
extracted = _extract_node(root)
assert extracted["node_type"] == "COMPONENT"
assert extracted["name"] == "Button/Primary"
assert "#2563EB" in extracted["raw_hex_values"]   # raiz
assert "#111827" in extracted["raw_hex_values"]   # filho depth-2 agregado
assert extracted["layout"]["width"] == 120
assert len(extracted["children"]) == 1
assert extracted["children"][0]["children"][0].get("text_content") == "Click me"
print("_extract_node (aggregation + depth): OK")

# Garante que depth 3 NÃO é extraído
grandchild = {"id": "4:1", "type": "RECTANGLE", "name": "deep", "fills": []}
child2["children"] = [grandchild]
extracted2 = _extract_node(root)
assert "children" not in extracted2["children"][0]["children"][0], "depth>2 não deve ter children"
print("_extract_node (depth limit): OK")

if errors:
    print("ERROS:", errors)
    sys.exit(1)
PYEOF

A_EXIT=$?
[ $A_EXIT -eq 0 ] && ok "Fase A — todas as funções puras OK" || fail "Fase A — falhou (ver acima)"

# ──────────────────────────────────────────────────────────
# FASE B — Pipeline completo com mock da API Figma
# ──────────────────────────────────────────────────────────
sep
echo "FASE B — Pipeline com mock (figma_reader → token_mapper)"
sep

python3 - << 'PYEOF'
import sys, json, unittest.mock
sys.path.insert(0, '.')

# Mock de resposta da API Figma para um componente Button
MOCK_FIGMA_RESPONSE = {
    "nodes": {
        "123:456": {
            "document": {
                "id": "123:456",
                "type": "COMPONENT",
                "name": "Button/Primary",
                "fills": [{"type": "SOLID", "visible": True,
                            "color": {"r": 0.145, "g": 0.388, "b": 0.922}, "opacity": 1.0}],
                "strokes": [{"type": "SOLID", "visible": True,
                             "color": {"r": 0.114, "g": 0.306, "b": 0.847}, "opacity": 1.0}],
                "absoluteBoundingBox": {"width": 160.0, "height": 44.0},
                "paddingTop": 10, "paddingRight": 20, "paddingBottom": 10, "paddingLeft": 20,
                "cornerRadius": 6, "layoutMode": "HORIZONTAL", "itemSpacing": 8,
                "effects": [{"type": "DROP_SHADOW", "visible": True,
                             "color": {"r": 0, "g": 0, "b": 0, "a": 0.1},
                             "offset": {"x": 0, "y": 2}, "radius": 4, "spread": 0}],
                "children": [
                    {
                        "id": "123:457", "type": "TEXT", "name": "Label",
                        "characters": "Button",
                        "style": {"fontFamily": "Inter", "fontSize": 14,
                                  "fontWeight": 600, "lineHeightPx": 20.0},
                        "fills": [{"type": "SOLID", "visible": True,
                                   "color": {"r": 1, "g": 1, "b": 1}, "opacity": 1.0}],
                    }
                ],
            }
        }
    }
}

import scripts.figma_reader as fr
with unittest.mock.patch.object(fr, '_figma_get', return_value=MOCK_FIGMA_RESPONSE):
    import os; os.environ.setdefault('FIGMA_TOKEN', 'mock-token')
    result = fr.read_node("MOCKFILE", "123:456")

# Estrutura
assert result["node_type"] == "COMPONENT", f"node_type={result['node_type']}"
assert result["name"] == "Button/Primary"
assert result["layout"]["width"] == 160
assert result["layout"]["height"] == 44
assert result["layout"]["paddingTop"] == 10
assert result["layout"]["cornerRadius"] == 6
assert result["typography"] == {}
assert len(result["effects"]) == 1
assert result["effects"][0]["color"] == "#000000"
print("✓ Estrutura do node extraída corretamente")

# Cores agregadas
assert "#2563EB" in result["raw_hex_values"]
assert "#1D4ED8" in result["raw_hex_values"]
assert "#FFFFFF" in result["raw_hex_values"]
print(f"✓ {len(result['raw_hex_values'])} cores únicas: {result['raw_hex_values']}")

# Children
assert len(result["children"]) == 1
child = result["children"][0]
assert child["node_type"] == "TEXT"
assert child["text_content"] == "Button"
assert child["typography"]["fontFamily"] == "Inter"
assert child["typography"]["fontWeight"] == 600
print("✓ Children com tipografia corretos")

# token_mapper
from scripts.token_mapper import map_hex
for hex_val in result["raw_hex_values"]:
    info = map_hex(hex_val)
    status = f"→ {info['css_var']}" if info["found"] else "sem token"
    print(f"  {hex_val}: {status}")

blue_map = map_hex("#2563EB")
assert blue_map["found"] == True
assert blue_map["css_var"] == "var(--ds-color-action-primary)"
assert blue_map["semantic"] == "color.action.primary"
print("✓ Mapeamento de tokens correto")

mapped   = [h for h in result["raw_hex_values"] if map_hex(h)["found"]]
unmapped = [h for h in result["raw_hex_values"] if not map_hex(h)["found"]]
print(f"✓ Mapeados: {len(mapped)} | Sem token: {len(unmapped)} {unmapped}")

# Normalização de node_id com '-'
with unittest.mock.patch.object(fr, '_figma_get', return_value=MOCK_FIGMA_RESPONSE):
    result_dash = fr.read_node("MOCKFILE", "123-456")
assert result_dash["node_type"] == "COMPONENT", "Normalização 123-456 → 123:456 falhou"
print("✓ Normalização node_id (- → :) OK")

# Token ausente retorna FIGMA_TOKEN vazio → ValueError
import os
orig = os.environ.pop('FIGMA_TOKEN', None)
try:
    fr._cache = None
    fr.read_node("X", "1:1")
    assert False, "Deveria lançar ValueError"
except ValueError as e:
    assert "FIGMA_TOKEN" in str(e)
    print("✓ ValueError quando FIGMA_TOKEN ausente")
finally:
    if orig:
        os.environ['FIGMA_TOKEN'] = orig

print("")
print("Pipeline completo: figma_reader → token_mapper OK")
PYEOF

B_EXIT=$?
[ $B_EXIT -eq 0 ] && ok "Fase B — mock pipeline OK" || fail "Fase B — falhou (ver acima)"

# ──────────────────────────────────────────────────────────
# FASE C — API real do Figma (opcional)
# ──────────────────────────────────────────────────────────
sep
echo "FASE C — API real do Figma"
sep

if [ -z "$FIGMA_TOKEN" ] || [ -z "$TEST_FIGMA_FILE_KEY" ] || [ -z "$TEST_FIGMA_NODE_ID" ]; then
  skip "Pulando — defina FIGMA_TOKEN, TEST_FIGMA_FILE_KEY e TEST_FIGMA_NODE_ID no .env para ativar"
else
  echo "  Token: ${FIGMA_TOKEN:0:10}... | File: $TEST_FIGMA_FILE_KEY | Node: $TEST_FIGMA_NODE_ID"
  python3 - << PYEOF
import sys, json
sys.path.insert(0, '.')
from scripts.figma_reader import read_node
from scripts.token_mapper import map_hex

try:
    result = read_node("$TEST_FIGMA_FILE_KEY", "$TEST_FIGMA_NODE_ID")
except Exception as e:
    print(f"ERRO: {e}")
    sys.exit(1)

print(f"✓ Node lido: [{result['node_type']}] {result['name']}")
print(f"  Layout: {result['layout']}")
print(f"  Tipografia: {result['typography']}")
print(f"  Efeitos: {len(result['effects'])}")
print(f"  Cores brutas: {result['raw_hex_values']}")

mapped   = [map_hex(h) for h in result["raw_hex_values"] if map_hex(h)["found"]]
unmapped = [h for h in result["raw_hex_values"] if not map_hex(h)["found"]]
print(f"  Tokens mapeados: {len(mapped)}")
for m in mapped:
    print(f"    {m['hex']} → {m['css_var']}")
if unmapped:
    print(f"  Sem token ({len(unmapped)}): {unmapped}")

assert result.get("node_id"),   "node_id ausente"
assert result.get("node_type"), "node_type ausente"
assert result.get("name"),      "name ausente"
assert isinstance(result.get("raw_hex_values"), list), "raw_hex_values deve ser lista"
assert isinstance(result.get("layout"), dict),         "layout deve ser dict"
print("✓ Estrutura de resposta válida")
PYEOF

  C_EXIT=$?
  [ $C_EXIT -eq 0 ] && ok "Fase C — API real Figma OK" || fail "Fase C — falhou (ver acima)"
fi

# Pausa entre fases C e D para respeitar rate limit da API Figma
if [ -n "$FIGMA_TOKEN" ] && [ -n "$TEST_FIGMA_FILE_KEY" ]; then
  echo "  ⏳ Aguardando 15s antes da fase D (rate limit Figma)..."
  sleep 15
fi

# ──────────────────────────────────────────────────────────
# FASE D — Endpoint /api/from-figma (requer servidor + Figma real)
# ──────────────────────────────────────────────────────────
sep
echo "FASE D — Endpoint POST /api/from-figma"
sep

SERVER_UP=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/api/health 2>/dev/null)

if [ "$SERVER_UP" != "200" ]; then
  skip "Servidor não está rodando em localhost:8000 — execute: uvicorn web.main:app --port 8000"
elif [ -z "$FIGMA_TOKEN" ] || [ -z "$TEST_FIGMA_FILE_KEY" ] || [ -z "$TEST_FIGMA_NODE_ID" ]; then
  skip "FIGMA_TOKEN / TEST_FIGMA_FILE_KEY / TEST_FIGMA_NODE_ID não definidos — pulando fase D"
else
  python3 - << PYEOF
import sys, json, urllib.request, urllib.error, re

payload = json.dumps({
    "file_key":       "$TEST_FIGMA_FILE_KEY",
    "node_id":        "$TEST_FIGMA_NODE_ID",
    "component_name": "FigmaTest",
    "proposed_by":    "test_nivel3.sh"
}).encode()

try:
    req = urllib.request.Request(
        "http://localhost:8000/api/from-figma",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        d = json.loads(resp.read())
except urllib.error.HTTPError as e:
    body = e.read().decode()
    print(f"HTTP {e.code}: {body[:300]}")
    sys.exit(1)
except Exception as e:
    print(f"ERRO: {e}")
    sys.exit(1)

HEX_RE = re.compile(r'#[0-9A-Fa-f]{6}(?:[0-9A-Fa-f]{2})?\b')

for field in ("tsx_code", "token_mapping", "unmapped_values", "score", "q2_passed"):
    assert field in d, f"Campo ausente: {field}"
print("✓ Campos obrigatórios presentes")

hex_in_tsx = HEX_RE.findall(d.get("tsx_code", ""))
if hex_in_tsx:
    print(f"⚠️  Q2: hex encontrado no TSX: {hex_in_tsx}")
else:
    print("✓ Q2: zero hex hard-coded no TSX gerado")

mapping = d.get("token_mapping", [])
print(f"✓ Tokens mapeados: {len(mapping)}")
for m in mapping:
    print(f"    {m['hex']} → {m['css_var']}")

unmapped = d.get("unmapped_values", [])
if unmapped:
    print(f"  Sem token: {unmapped}")

print(f"✓ Score Q4: {d.get('score')}/100 | Aprovado: {d.get('approved')}")
if d.get("adr_number"):
    print(f"✓ ADR gerado: ADR-{str(d['adr_number']).zfill(3)}")

print(f"✓ TSX: {len(d.get('tsx_code','').splitlines())} linhas")
print(f"✓ Stories: {len(d.get('stories_code','').splitlines())} linhas")
PYEOF

  D_EXIT=$?
  [ $D_EXIT -eq 0 ] && ok "Fase D — endpoint /api/from-figma OK" || fail "Fase D — falhou (ver acima)"
fi

# ──────────────────────────────────────────────────────────
# Resultado final
# ──────────────────────────────────────────────────────────
sep
echo ""
echo "=================================================="
echo " RESULTADO: ${PASS} passou(aram) | ${FAIL} falhou(aram)"
echo "=================================================="
echo ""
echo "Para ativar as fases C e D, adicione ao .env:"
echo "  FIGMA_TOKEN=figd_..."
echo "  TEST_FIGMA_FILE_KEY=<file_key da URL do Figma>"
echo "  TEST_FIGMA_NODE_ID=<node-id da URL do Figma>"
echo ""

[ $FAIL -eq 0 ] && exit 0 || exit 1
