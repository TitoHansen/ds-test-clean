"""
Consulta ao RAG de Referência e de Decisão.
Usado por todos os agentes antes de tomar ação.
"""
import os, json
import psycopg2
from pgvector.psycopg2 import register_vector
from dotenv import load_dotenv

load_dotenv()

def _get_conn():
    conn = psycopg2.connect(os.getenv("DATABASE_URL", ""))
    register_vector(conn)
    return conn

def _get_embedding(text: str) -> list:
    """Gera embedding via OpenAI text-embedding-3-small."""
    import openai
    client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    resp = client.embeddings.create(model="text-embedding-3-small", input=text[:8000])
    return resp.data[0].embedding

def query_reference(question: str, doc_type: str = None, top_k: int = 5) -> list:
    """Consulta o RAG de Referência. Retorna top_k documentos similares."""
    embedding = _get_embedding(question)
    conn = _get_conn()
    with conn.cursor() as cur:
        if doc_type:
            cur.execute(
                """SELECT name, content, metadata, type,
                          1 - (embedding <=> %s::vector) AS similarity
                   FROM ds_reference WHERE type = %s
                   ORDER BY embedding <=> %s::vector LIMIT %s""",
                (embedding, doc_type, embedding, top_k)
            )
        else:
            cur.execute(
                """SELECT name, content, metadata, type,
                          1 - (embedding <=> %s::vector) AS similarity
                   FROM ds_reference
                   ORDER BY embedding <=> %s::vector LIMIT %s""",
                (embedding, embedding, top_k)
            )
        rows = cur.fetchall()
    conn.close()
    return [{"name": r[0], "content": r[1], "metadata": r[2],
             "type": r[3], "similarity": float(r[4])} for r in rows]

def query_decisions(question: str, top_k: int = 3) -> list:
    """Consulta o RAG de Decisão (ADRs). Retorna ADRs mais relevantes."""
    embedding = _get_embedding(question)
    conn = _get_conn()
    with conn.cursor() as cur:
        cur.execute(
            """SELECT adr_number, title, status, context, decision,
                      rationale, alternatives,
                      1 - (embedding <=> %s::vector) AS similarity
               FROM ds_decisions WHERE status != 'deprecated'
               ORDER BY embedding <=> %s::vector LIMIT %s""",
            (embedding, embedding, top_k)
        )
        rows = cur.fetchall()
    conn.close()
    return [{"adr_number": r[0], "title": r[1], "status": r[2],
             "context": r[3], "decision": r[4], "rationale": r[5],
             "alternatives": r[6], "similarity": float(r[7])} for r in rows]
