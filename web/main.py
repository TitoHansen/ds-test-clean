from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import sys, os, re, json, difflib
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import anthropic
from dotenv import load_dotenv
load_dotenv()

_claude = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))
_HEX_RE = re.compile(r"#[0-9A-Fa-f]{6}(?:[0-9A-Fa-f]{2})?\b")

app = FastAPI(title="Design System — Painel de Governança")

class ContributionRequest(BaseModel):
    component_name: str
    description: str
    proposed_by: str

class QueryRequest(BaseModel):
    question: str

class TransformRequest(BaseModel):
    component_name: str
    component_code: str

class GenerateRequest(BaseModel):
    name: str
    description: str
    variants: list = []
    a11y: str = ""
    proposed_by: str

class FigmaRequest(BaseModel):
    file_key: str
    node_id: str
    component_name: str
    proposed_by: str

@app.get("/", response_class=HTMLResponse)
async def root():
    try:
        with open(os.path.join(os.path.dirname(__file__), "index.html")) as f:
            return f.read()
    except FileNotFoundError:
        return "<h1>Design System — Painel de Governança</h1><p>index.html não encontrado.</p>"

@app.post("/api/review")
async def review(req: ContributionRequest):
    try:
        from scripts.review_agent import review_contribution
        result = review_contribution(
            req.component_name, req.description, req.proposed_by, use_rag=True)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/query")
async def query(req: QueryRequest):
    try:
        from scripts.query import query_reference, query_decisions
        return {
            "reference": query_reference(req.question, top_k=5),
            "decisions": query_decisions(req.question, top_k=3),
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"RAG indisponível: {e}")

@app.post("/api/generate")
async def generate(req: GenerateRequest):
    """
    Capacidade 1 — Gera componente novo (TSX + Stories).
    Fluxo: Q3 duplicatas → Claude gera → Q2 valida → Q4 avalia → ADR gerado.
    """
    # Q3 — busca duplicatas e contexto no RAG
    rag_duplicates = []
    rag_context = ""
    try:
        from scripts.query import query_reference, query_decisions
        ref = query_reference(f"{req.name}: {req.description}", top_k=5)
        dec = query_decisions(f"{req.name}: {req.description}", top_k=3)
        rag_duplicates = [
            {"name": r["name"], "similarity": round(r["similarity"], 3),
             "summary": r["content"][:200]}
            for r in ref if r["similarity"] > 0.85
        ]
        rag_context = json.dumps({
            "referencia": [{"nome": r["name"], "resumo": r["content"][:300]}
                           for r in ref],
            "decisoes": [{"adr": f"ADR-{d['adr_number']:03d}",
                          "decisao": d["decision"][:300]}
                         for d in dec],
        }, ensure_ascii=False)
    except Exception as e:
        rag_context = "{}"
        print(f"⚠️  RAG indisponível ({e}), gerando sem contexto histórico.")

    variants_str = ", ".join(req.variants) if req.variants else "default"

    prompt = (
        f"Você é o agente gerador do Design System.\n\n"
        f"Componente: {req.name}\n"
        f"Descrição: {req.description}\n"
        f"Variantes: {variants_str}\n"
        f"Acessibilidade: {req.a11y or 'WCAG AA obrigatório'}\n"
        f"Proposto por: {req.proposed_by}\n\n"
        f"Contexto do DS (RAG): {rag_context}\n\n"
        f"REGRAS ABSOLUTAS:\n"
        f"- ZERO hex hard-coded — use SOMENTE var(--ds-*) para cores\n"
        f"- Tokens de espaçamento: var(--ds-spacing-*)\n"
        f"- Tokens tipográficos: var(--ds-font-*)\n"
        f"- Componente deve ser acessível (aria-label, role, keyboard nav)\n"
        f"- TSX com TypeScript tipado (interface Props)\n\n"
        f"Retorne APENAS JSON válido (sem markdown) com dois campos:\n"
        f'{{"tsx_code": "<código TSX completo>", '
        f'"stories_code": "<código Storybook CSF3 completo>"}}'
    )

    try:
        response = _claude.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=6000,
            system=(
                "Você é especialista em Design Systems e gera componentes React/TypeScript. "
                "Retorne APENAS JSON válido com os campos tsx_code e stories_code. "
                "Sem blocos markdown, sem texto fora do JSON."
            ),
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
        generated = json.loads(raw)
        tsx_code = generated.get("tsx_code", "")
        stories_code = generated.get("stories_code", "")
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=502,
                            detail=f"Claude retornou JSON inválido: {e}")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Claude indisponível: {e}")

    # Q2 — valida hex no TSX gerado
    remaining_hex = _HEX_RE.findall(tsx_code)
    q2_passed = len(remaining_hex) == 0

    # Extrai tokens usados no TSX
    tokens_used = sorted(set(re.findall(r"var\(--ds-[a-z0-9-]+\)", tsx_code)))

    # Q4 — avalia o componente gerado (inclui TSX para avaliação real)
    score, approved, q4_issues = 0, False, []
    try:
        from scripts.review_agent import review_contribution
        tsx_preview = tsx_code[:2000] if tsx_code else ""
        review = review_contribution(
            component_name=req.name,
            description=(
                f"{req.description} | Variantes: {variants_str}\n"
                f"Q2 aprovado: {q2_passed} | Tokens usados: {len(tokens_used)}\n"
                f"Implementação TSX gerada (prévia):\n{tsx_preview}"
            ),
            proposed_by=req.proposed_by,
            use_rag=False,  # RAG já foi consultado acima
        )
        score = review.get("score", 0)
        approved = review.get("approved", False)
        q4_issues = review.get("issues", [])
    except Exception as e:
        print(f"⚠️  Q4 indisponível ({e}), aprovação pendente.")

    # ADR — gerado apenas se Q4 aprovado ou score >= 60
    adr_number = None
    if approved or score >= 60:
        try:
            from scripts.adr_generator import generate_adr
            adr = generate_adr(
                component_name=req.name,
                problem=req.description,
                solution=f"Componente {req.name} com variantes: {variants_str}",
                requested_by=req.proposed_by,
                use_rag=False,
            )
            adr_number = adr.get("number")
        except Exception as e:
            print(f"⚠️  ADR não gerado ({e}).")

    return {
        "tsx_code": tsx_code,
        "stories_code": stories_code,
        "tokens_used": tokens_used,
        "adr_number": adr_number,
        "score": score,
        "approved": approved,
        "q2_passed": q2_passed,
        "q2_remaining_hex": remaining_hex,
        "q4_issues": q4_issues,
        "rag_duplicates": rag_duplicates,
    }


@app.post("/api/from-figma")
async def from_figma(req: FigmaRequest):
    """
    Capacidade 3 — Gera componente TSX a partir de um node do Figma.
    Fluxo: figma_reader → token_mapper → Q3 → Claude gera → Q2 + Q4 → ADR.
    """
    # figma_reader — extrai propriedades do node
    try:
        from scripts.figma_reader import read_node
        figma_props = read_node(req.file_key, req.node_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=f"Figma API: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"figma_reader: {e}")

    # token_mapper — mapeia cada hex extraído do Figma
    from scripts.token_mapper import map_hex
    token_mapping = []
    unmapped_values = []
    for hex_val in figma_props.get("raw_hex_values", []):
        result = map_hex(hex_val)
        if result["found"]:
            token_mapping.append(result)
        else:
            unmapped_values.append(hex_val)

    # Q3 — contexto RAG para evitar duplicatas e respeitar decisões anteriores
    rag_context = "{}"
    rag_duplicates = []
    try:
        from scripts.query import query_reference, query_decisions
        ref = query_reference(f"{req.component_name}: componente Figma", top_k=5)
        dec = query_decisions(f"{req.component_name}", top_k=3)
        rag_duplicates = [
            {"name": r["name"], "similarity": round(r["similarity"], 3),
             "summary": r["content"][:200]}
            for r in ref if r["similarity"] > 0.85
        ]
        rag_context = json.dumps({
            "referencia": [{"nome": r["name"], "resumo": r["content"][:300]}
                           for r in ref],
            "decisoes": [{"adr": f"ADR-{d['adr_number']:03d}",
                          "decisao": d["decision"][:300]}
                         for d in dec],
        }, ensure_ascii=False)
    except Exception as e:
        print(f"⚠️  RAG indisponível ({e}), gerando sem contexto histórico.")

    # Monta descrição das propriedades Figma para o prompt
    layout = figma_props.get("layout", {})
    typo = figma_props.get("typography", {})
    effects = figma_props.get("effects", [])

    mapping_lines = "\n".join(
        f"  {m['hex']} → {m['css_var']}  ({m['semantic'] or m['primitive']})"
        for m in token_mapping
    )
    unmapped_lines = "\n".join(f"  {h}  (sem token — parametrize via prop)" for h in unmapped_values)

    prompt = (
        f"Você é o agente gerador do Design System.\n\n"
        f"Componente Figma: {req.component_name}\n"
        f"Tipo de node: {figma_props.get('node_type')}\n"
        f"Nome no Figma: {figma_props.get('name')}\n\n"
        f"PROPRIEDADES EXTRAÍDAS DO FIGMA:\n"
        f"Layout: {json.dumps(layout)}\n"
        f"Tipografia: {json.dumps(typo)}\n"
        f"Efeitos: {json.dumps(effects)}\n\n"
        f"MAPEAMENTO DE CORES (use os tokens abaixo):\n{mapping_lines or '  (nenhum mapeado)'}\n\n"
        + (f"CORES SEM TOKEN (parametrize como prop ou CSS var customizada):\n{unmapped_lines}\n\n"
           if unmapped_values else "")
        + f"Contexto do DS (RAG): {rag_context}\n\n"
        f"REGRAS ABSOLUTAS:\n"
        f"- ZERO hex hard-coded no output — use os tokens mapeados acima\n"
        f"- Respeite fielmente as dimensões e espaçamentos do Figma\n"
        f"- Componente acessível: aria-label, role, suporte a teclado\n"
        f"- TSX com TypeScript tipado (interface Props)\n"
        f"- Proposto por: {req.proposed_by}\n\n"
        f"Retorne APENAS JSON válido (sem markdown):\n"
        f'{{"tsx_code": "<código TSX completo>", '
        f'"stories_code": "<código Storybook CSF3 completo>"}}'
    )

    try:
        response = _claude.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=6000,
            system=(
                "Você é especialista em Design Systems. Converte especificações Figma em "
                "componentes React/TypeScript usando tokens de design. "
                "Retorne APENAS JSON com tsx_code e stories_code. Sem markdown."
            ),
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
        generated = json.loads(raw)
        tsx_code = generated.get("tsx_code", "")
        stories_code = generated.get("stories_code", "")
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=502,
                            detail=f"Claude retornou JSON inválido: {e}")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Claude indisponível: {e}")

    # Q2 — valida hex no TSX gerado
    remaining_hex = _HEX_RE.findall(tsx_code)
    q2_passed = len(remaining_hex) == 0
    tokens_used = sorted(set(re.findall(r"var\(--ds-[a-z0-9-]+\)", tsx_code)))

    # Q4 — avalia componente gerado
    score, approved, q4_issues = 0, False, []
    try:
        from scripts.review_agent import review_contribution
        tsx_preview_fig = tsx_code[:2000] if tsx_code else ""
        review = review_contribution(
            component_name=req.component_name,
            description=(
                f"Gerado a partir do Figma node {req.node_id}.\n"
                f"Layout: {json.dumps(layout)} | Q2: {q2_passed} | Tokens: {len(tokens_used)}\n"
                f"Implementação TSX gerada (prévia):\n{tsx_preview_fig}"
            ),
            proposed_by=req.proposed_by,
            use_rag=False,
        )
        score = review.get("score", 0)
        approved = review.get("approved", False)
        q4_issues = review.get("issues", [])
    except Exception as e:
        print(f"⚠️  Q4 indisponível ({e}), aprovação pendente.")

    # ADR — gerado se Q4 aprovado ou score >= 60
    adr_number = None
    if approved or score >= 60:
        try:
            from scripts.adr_generator import generate_adr
            adr = generate_adr(
                component_name=req.component_name,
                problem=f"Implementar componente a partir do Figma node {req.node_id}",
                solution=f"TSX gerado com {len(token_mapping)} tokens mapeados do Figma",
                requested_by=req.proposed_by,
                use_rag=False,
            )
            adr_number = adr.get("number")
        except Exception as e:
            print(f"⚠️  ADR não gerado ({e}).")

    return {
        "tsx_code": tsx_code,
        "stories_code": stories_code,
        "token_mapping": token_mapping,
        "unmapped_values": unmapped_values,
        "tokens_used": tokens_used,
        "figma_props": {
            "node_type": figma_props.get("node_type"),
            "name": figma_props.get("name"),
            "layout": layout,
            "typography": typo,
            "effects": effects,
        },
        "score": score,
        "approved": approved,
        "adr_number": adr_number,
        "q2_passed": q2_passed,
        "q2_remaining_hex": remaining_hex,
        "q4_issues": q4_issues,
        "rag_duplicates": rag_duplicates,
    }


@app.post("/api/transform")
async def transform(req: TransformRequest):
    """
    Capacidade 2 — Refatora componente legado substituindo hex por tokens.
    Fluxo: Q2 detecta violações → token_mapper substitui → Claude refatora → Q2 valida.
    """
    try:
        from scripts.token_mapper import map_all_hex
    except ImportError as e:
        raise HTTPException(status_code=500, detail=f"token_mapper indisponível: {e}")

    original_code = req.component_code

    # Q2 — detecta violações no código de entrada
    violations_found = [
        {"line": i + 1, "hex": h, "hint": "Substitua por token semântico"}
        for i, line in enumerate(original_code.splitlines())
        for h in _HEX_RE.findall(line.split("//")[0])
    ]

    # token_mapper — substitui hex conhecidos por CSS vars
    mapped = map_all_hex(original_code)
    partially_fixed = mapped["code"]

    # Claude — refatora o código com contexto completo
    prompt = (
        f"Você é o agente de refatoração do Design System.\n"
        f"Componente: {req.component_name}\n\n"
        f"REGRAS ABSOLUTAS:\n"
        f"- ZERO valores hex hard-coded no output\n"
        f"- Use SOMENTE tokens CSS: var(--ds-*)\n"
        f"- Preserve toda a lógica e estrutura do componente\n"
        f"- Retorne APENAS o código TSX refatorado, sem explicações\n\n"
        f"Tokens já substituídos automaticamente:\n"
        + "\n".join(f"  {m['hex']} → {m['css_var']}" for m in mapped["mapped"])
        + (f"\n\nValores sem token mapeado (você DEVE comentar ou parametrizar):\n"
           + "\n".join(f"  {h}" for h in mapped["unmapped"])
           if mapped["unmapped"] else "")
        + f"\n\nCódigo após substituição automática:\n```tsx\n{partially_fixed}\n```\n\n"
        f"Refatore para garantir conformidade total. Retorne apenas o bloco TSX final."
    )

    try:
        response = _claude.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=(
                "Você é especialista em Design Systems. "
                "Retorne APENAS código TSX válido, sem blocos markdown, sem explicações."
            ),
            messages=[{"role": "user", "content": prompt}],
        )
        transformed_code = response.content[0].text.strip()
        # Remove fences se o modelo as incluir mesmo com a instrução
        if transformed_code.startswith("```"):
            transformed_code = re.sub(r"^```[a-z]*\n?", "", transformed_code)
            transformed_code = re.sub(r"\n?```$", "", transformed_code)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Claude indisponível: {e}")

    # Q2 — valida output (hex restantes = violações não corrigidas)
    remaining_hex = _HEX_RE.findall(transformed_code)
    violations_fixed = len(violations_found) - len(remaining_hex)
    q2_passed = len(remaining_hex) == 0

    # Diff unificado entre original e transformado
    diff = "\n".join(difflib.unified_diff(
        original_code.splitlines(),
        transformed_code.splitlines(),
        fromfile=f"{req.component_name}.original.tsx",
        tofile=f"{req.component_name}.transformed.tsx",
        lineterm="",
    ))

    return {
        "transformed_code": transformed_code,
        "violations_found": violations_found,
        "violations_fixed": violations_fixed,
        "tokens_mapped": mapped["mapped"],
        "unmapped_values": mapped["unmapped"],
        "diff": diff,
        "q2_passed": q2_passed,
        "q2_remaining": [{"hex": h} for h in remaining_hex],
    }


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "Design System Governance Panel"}
