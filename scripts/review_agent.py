"""
Q4 — Agente de Revisão por IA.
Avalia contribuições externas contra RAG de Referência e de Decisão.
"""
import os, json
import anthropic
from dotenv import load_dotenv

load_dotenv()
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))


def review_contribution(component_name: str, description: str,
                        proposed_by: str, use_rag: bool = True) -> dict:
    """
    Avalia uma proposta de componente externo.
    Retorna: approved, score, issues, recommendations, reasoning.
    """
    ref_ctx, dec_ctx = "[]", "[]"

    if use_rag:
        try:
            from scripts.query import query_reference, query_decisions
            ref = query_reference(f"{component_name}: {description}", top_k=5)
            dec = query_decisions(f"{component_name}: {description}", top_k=3)
            ref_ctx = json.dumps(
                [{"nome": r["name"], "tipo": r["type"], "resumo": r["content"][:300]}
                 for r in ref], ensure_ascii=False
            )
            dec_ctx = json.dumps(
                [{"adr": f"ADR-{d['adr_number']:03d}",
                  "decisao": d["decision"][:300],
                  "alternativas": d.get("alternatives", "")[:200]}
                 for d in dec], ensure_ascii=False
            )
        except Exception as e:
            print(f"⚠️  RAG indisponível ({e}), avaliando sem contexto histórico.")

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=3000,
        system=(
            "Você é o Agente de Revisão do Design System. "
            "Avalie contribuições externas com rigor. "
            "Retorne APENAS JSON válido, sem markdown."
        ),
        messages=[{"role": "user", "content": (
            f"Componente proposto: {component_name}\n"
            f"Descrição: {description}\n"
            f"Proposto por: {proposed_by}\n\n"
            f"Estado atual do DS (RAG Referência): {ref_ctx}\n"
            f"Decisões anteriores (RAG Decisão): {dec_ctx}\n\n"
            "Avalie e retorne JSON:\n"
            "{ approved: bool, score: 0-100, "
            "issues: [{severity, category, description}], "
            "recommendations: [string], reasoning: string, "
            "suggested_next_step: string }\n\n"
            "Bloqueie se: duplica componente com >80% similaridade, "
            "contradiz ADR em vigor, viola hierarquia Atomic Design, "
            "não atende WCAG AA."
        )}]
    )

    import re as _re
    raw = response.content[0].text.strip()
    raw = _re.sub(r"^```[a-z]*\n?", "", raw)
    raw = _re.sub(r"\n?```$", "", raw).strip()

    result = None
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        # Fallback: extrai o primeiro objeto JSON completo da resposta
        m = _re.search(r"\{.*\}", raw, _re.DOTALL)
        if m:
            try:
                result = json.loads(m.group(0))
            except json.JSONDecodeError:
                pass

    if result is None:
        result = {"approved": False, "score": 0, "issues": [],
                  "recommendations": [], "reasoning": "Resposta do modelo não pôde ser parseada"}

    result.update({"component": component_name, "proposed_by": proposed_by})
    return result


def format_report(review: dict) -> str:
    status = "✅ APROVADO" if review.get("approved") else "❌ BLOQUEADO"
    score = review.get("score", 0)
    bar = "█" * (score // 10) + "░" * (10 - score // 10)
    lines = [
        f"## Q4 — Revisão: {review.get('component', '?')}",
        f"**Status:** {status} | **Score:** {score}/100 [{bar}]",
        f"**Proposto por:** {review.get('proposed_by', '?')}",
        f"\n**Análise:** {review.get('reasoning', '')}",
    ]
    if review.get("issues"):
        lines.append("\n**Problemas:**")
        for issue in review["issues"]:
            sev = {"blocker": "🔴", "warning": "🟡", "info": "🔵"}.get(issue.get("severity", "info"), "🔵")
            lines.append(f"{sev} {issue.get('description', '')}")
    if review.get("recommendations"):
        lines.append("\n**Recomendações:**")
        for rec in review["recommendations"]:
            lines.append(f"• {rec}")
    lines.append(f"\n**Próximo passo:** {review.get('suggested_next_step', 'N/A')}")
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    print("🔄 Avaliando proposta (sem RAG)...")
    result = review_contribution(
        component_name=sys.argv[1] if len(sys.argv) > 1 else "Badge de Status",
        description="Componente para indicar estados (sucesso, erro, alerta) em listas",
        proposed_by="Time de Produto",
        use_rag=False,
    )
    print(format_report(result))
