"""
Gerador de ADRs com contexto do RAG.
Q3 consulta RAG antes de gerar. Claude formata o ADR.
"""
import os, json, glob
from datetime import datetime
import anthropic
from dotenv import load_dotenv

load_dotenv()
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))


def _get_next_adr_number() -> int:
    existing = glob.glob("docs/adrs/[0-9]*.md")
    return len(existing) + 1


def _write_adr(adr: dict, component_name: str) -> str:
    """Salva o ADR em Markdown e retorna o filepath."""
    slug = component_name.lower().replace(" ", "-")
    path = f"docs/adrs/{adr['number']:03d}-{slug}.md"
    with open(path, "w") as f:
        f.write(f"# ADR-{adr['number']:03d}: {adr['title']}\n\n")
        f.write(f"**Status:** {adr['status']} | **Data:** {adr['date']}\n")
        f.write(f"**Solicitado por:** {adr.get('requested_by', '')}\n\n")
        for section in ["context", "decision", "rationale", "alternatives", "consequences"]:
            label = {"context": "Contexto", "decision": "Decisão",
                     "rationale": "Justificativa", "alternatives": "Alternativas",
                     "consequences": "Consequências"}.get(section, section.title())
            f.write(f"## {label}\n\n{adr.get(section, '')}\n\n")
        f.write(f"## Componente\n\nComponente: {component_name}\n")
    return path


def _ingest_adr(adr: dict, conn=None):
    """Ingere o ADR no RAG de Decisão (banco vetorial)."""
    # Importação tardia para evitar dependência circular
    from scripts.ingest import ingest_adr, get_embedding
    import psycopg2
    from pgvector.psycopg2 import register_vector

    if conn is None:
        conn = psycopg2.connect(os.getenv("DATABASE_URL"))
        register_vector(conn)
        close_after = True
    else:
        close_after = False

    ingest_adr(
        adr_number=adr["number"],
        title=adr["title"],
        status=adr["status"],
        context=adr.get("context", ""),
        decision=adr.get("decision", ""),
        rationale=adr.get("rationale", ""),
        alternatives=adr.get("alternatives", ""),
        conn=conn,
    )

    if close_after:
        conn.close()


def generate_adr(component_name: str, problem: str,
                 solution: str, requested_by: str,
                 use_rag: bool = True) -> dict:
    """
    Gera um ADR com contexto do RAG (Q3) e Claude (Q4).

    Args:
        use_rag: False para testes sem banco de dados.
    """
    ref_ctx, dec_ctx = "[]", "[]"

    if use_rag:
        try:
            from scripts.query import query_reference, query_decisions
            ref = query_reference(f"{component_name}: {problem}", top_k=5)
            dec = query_decisions(f"{component_name}: {problem}", top_k=3)
            ref_ctx = json.dumps([{"nome": r["name"], "resumo": r["content"][:300]}
                                   for r in ref], ensure_ascii=False)
            dec_ctx = json.dumps([{"adr": f"ADR-{d['adr_number']:03d}",
                                    "decisao": d["decision"][:300]}
                                   for d in dec], ensure_ascii=False)
        except Exception as e:
            print(f"⚠️  RAG indisponível ({e}), gerando ADR sem contexto.")

    next_num = _get_next_adr_number()

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system=(
            "Crie ADRs precisos para Design Systems. "
            "Retorne APENAS JSON válido, sem markdown. "
            "Cada campo deve ter no máximo 120 palavras."
        ),
        messages=[{"role": "user", "content": (
            f"Componente: {component_name}\n"
            f"Problema: {problem}\n"
            f"Solução proposta: {solution}\n"
            f"Solicitado por: {requested_by}\n\n"
            f"Contexto existente no DS: {ref_ctx}\n"
            f"Decisões anteriores relevantes: {dec_ctx}\n\n"
            "Retorne JSON com campos concisos (máx 120 palavras cada):\n"
            "title, context, decision, rationale, alternatives, consequences"
        )}]
    )

    import re as _re
    raw = response.content[0].text.strip()
    raw = _re.sub(r"^```[a-z]*\n?", "", raw)
    raw = _re.sub(r"\n?```$", "", raw).strip()
    adr = json.loads(raw)
    adr.update({
        "number": next_num,
        "status": "proposed",
        "date": datetime.now().strftime("%Y-%m-%d"),
        "requested_by": requested_by,
    })

    path = _write_adr(adr, component_name)
    print(f"✅ ADR gerado: {path}")

    # Ingere no RAG de Decisão (só se banco disponível)
    if use_rag:
        try:
            _ingest_adr(adr)
            print("✅ ADR ingerido no RAG de Decisão")
        except Exception as e:
            print(f"⚠️  ADR salvo em arquivo mas não ingerido no RAG: {e}")

    return adr


if __name__ == "__main__":
    import sys
    print("🔄 Gerando ADR de teste (sem RAG)...")
    result = generate_adr(
        component_name=sys.argv[1] if len(sys.argv) > 1 else "Badge",
        problem="Precisamos comunicar estados de status em listas e tabelas",
        solution="Componente Badge com variantes de cor para cada estado",
        requested_by="Time de Produto",
        use_rag=False,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
