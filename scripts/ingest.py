"""
Ingestão de documentos no RAG de Referência e de Decisão.
Suporta: .json (tokens), .md (regras, ADRs).
"""
import os, json, glob
import psycopg2
from pgvector.psycopg2 import register_vector
from dotenv import load_dotenv

load_dotenv()


def flatten(data: dict, prefix: str = "") -> list:
    """Achata tokens JSON aninhados em lista plana de (nome, dados)."""
    result = []
    for key, value in data.items():
        full_key = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict) and "value" in value:
            result.append((full_key, value))
        elif isinstance(value, dict):
            result.extend(flatten(value, full_key))
    return result


def get_embedding(text: str) -> list:
    """Gera embedding via OpenAI text-embedding-3-small."""
    import openai
    client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    resp = client.embeddings.create(
        model="text-embedding-3-small",
        input=text[:8000]
    )
    return resp.data[0].embedding


def ingest_token_file(filepath: str, conn) -> int:
    """Ingere um arquivo JSON de tokens no RAG de Referência."""
    with open(filepath) as fp:
        data = json.load(fp)
    count = 0
    with conn.cursor() as cur:
        for name, token_data in flatten(data):
            content = (
                f"Token: {name}\n"
                f"Valor: {token_data.get('value', '')}\n"
                f"Tipo: {token_data.get('type', '')}"
            )
            embedding = get_embedding(content)
            cur.execute(
                """INSERT INTO ds_reference (type, name, content, metadata, embedding)
                   VALUES (%s, %s, %s, %s, %s)
                   ON CONFLICT DO NOTHING""",
                ("token", name, content, json.dumps(token_data), embedding)
            )
            count += 1
    conn.commit()
    return count


def ingest_markdown(filepath: str, doc_type: str, conn) -> int:
    """Ingere um arquivo Markdown (regra, guideline, ADR)."""
    with open(filepath) as fp:
        content = fp.read()
    name = os.path.basename(filepath).replace(".md", "")
    embedding = get_embedding(content[:4000])
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO ds_reference (type, name, content, metadata, embedding)
               VALUES (%s, %s, %s, %s, %s)
               ON CONFLICT DO NOTHING""",
            (doc_type, name, content, json.dumps({"filepath": filepath}), embedding)
        )
    conn.commit()
    return 1


def ingest_adr(adr_number: int, title: str, status: str, context: str,
               decision: str, rationale: str, alternatives: str, conn):
    """Ingere um ADR na tabela ds_decisions."""
    content = f"{title}\n{context}\n{decision}\n{rationale}"
    embedding = get_embedding(content)
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO ds_decisions
               (adr_number, title, status, context, decision, rationale, alternatives, embedding)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (adr_number) DO UPDATE
               SET title=%s, status=%s, decision=%s, embedding=%s""",
            (adr_number, title, status, context, decision, rationale,
             alternatives or "", embedding,
             title, status, decision, embedding)
        )
    conn.commit()


def ingest_all():
    """Ingere todos os documentos do projeto no RAG."""
    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    register_vector(conn)
    total = 0

    # Tokens
    for f in glob.glob("tokens/**/*.json", recursive=True):
        n = ingest_token_file(f, conn)
        print(f"  ✅ Tokens: {f} → {n} registros")
        total += n

    # Regras (agents/)
    for f in glob.glob("agents/**/*.md", recursive=True):
        n = ingest_markdown(f, "rule", conn)
        print(f"  ✅ Regra: {f}")
        total += n

    # ADRs
    for f in glob.glob("docs/adrs/*.md", recursive=True):
        n = ingest_markdown(f, "adr", conn)
        print(f"  ✅ ADR: {f}")
        total += n

    conn.close()
    print(f"\nTotal ingerido: {total} documentos")


if __name__ == "__main__":
    print("🔄 Ingestão iniciando...")
    ingest_all()
