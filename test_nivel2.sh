#!/bin/bash
# ============================================================
# Nível 2 — Teste completo com pgvector + Claude API
# Requer: Docker Desktop rodando + chaves de API no .env
# ============================================================
set -e

echo "=================================================="
echo " TESTE NÍVEL 2 — Sistema Completo"
echo "=================================================="

# Carrega .env
if [ -f .env ]; then
  export $(grep -v '^#' .env | xargs)
else
  echo "❌ Arquivo .env não encontrado."
  echo "   Execute: cp .env.template .env"
  echo "   Depois preencha as chaves de API no arquivo .env"
  exit 1
fi

# Verifica pré-requisitos
echo ""
echo "▶ Verificando pré-requisitos..."
command -v docker >/dev/null 2>&1 || {
  echo "❌ Docker não encontrado. Instale em: docker.com/products/docker-desktop"
  exit 1
}
docker info >/dev/null 2>&1 || {
  echo "❌ Docker não está rodando. Abra o Docker Desktop e aguarde inicializar."
  exit 1
}
[ -n "$ANTHROPIC_API_KEY" ] || { echo "❌ ANTHROPIC_API_KEY não definida no .env"; exit 1; }
[ -n "$OPENAI_API_KEY" ]    || { echo "❌ OPENAI_API_KEY não definida no .env"; exit 1; }
echo "✅ Pré-requisitos OK"

# 1. Instala dependências Python
echo ""
echo "▶ Instalando dependências Python..."
pip3 install -r requirements.txt --quiet 2>/dev/null || \
pip install -r requirements.txt --quiet 2>/dev/null || {
  echo "Tentando com virtualenv..."
  python3 -m venv venv && source venv/bin/activate
  pip install -r requirements.txt --quiet
}
echo "✅ Dependências instaladas"

# 2. Sobe banco pgvector
echo ""
echo "▶ Subindo PostgreSQL + pgvector..."
docker-compose up -d postgres
echo "▶ Aguardando banco ficar pronto..."
until docker-compose exec -T postgres pg_isready -U ds_user -d design_system >/dev/null 2>&1; do
  printf "."
  sleep 2
done
echo ""
echo "✅ Banco pronto"

# 3. Ingere documentos no RAG
echo ""
echo "▶ Ingerindo documentos no RAG (tokens, regras, ADRs)..."
python3 scripts/ingest.py
echo "✅ RAG populado"

# 4. Testa consulta ao RAG
echo ""
echo "▶ Testando consulta ao RAG..."
python3 - << 'PYEOF'
import sys, os
sys.path.insert(0, '.')
from scripts.query import query_reference
results = query_reference('cor de ação primária', top_k=3)
if results:
    print(f"✅ RAG respondendo — {len(results)} resultado(s)")
    for r in results:
        print(f"   {r['name']} ({r['type']}) — similaridade: {r['similarity']:.2f}")
else:
    print("⚠️  RAG sem resultados. Verifique a ingestão.")
    sys.exit(1)
PYEOF

# 5. Testa agente de revisão Q4
echo ""
echo "▶ Testando Q4 — Agente de Revisão (Claude API)..."
python3 - << 'PYEOF'
import sys, os
sys.path.insert(0, '.')
from scripts.review_agent import review_contribution, format_report
result = review_contribution(
    component_name='Badge de Status',
    description='Componente para indicar estados (sucesso, erro, alerta) em listas e tabelas',
    proposed_by='Time de Produto',
    use_rag=True
)
status = '✅ Aprovado' if result.get('approved') else '⚠️  Bloqueado'
print(f"{status} | Score: {result.get('score', 0)}/100")
print(f"Reasoning: {result.get('reasoning', '')[:300]}")
PYEOF

# 6. Sobe interface web
echo ""
echo "▶ Iniciando interface web para designers..."
python3 -m uvicorn web.main:app --host 0.0.0.0 --port 8000 &
WEB_PID=$!
sleep 4
HTTP=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/api/health 2>/dev/null)
if [ "$HTTP" = "200" ]; then
  echo "✅ Interface web no ar!"
  echo ""
  echo "=================================================="
  echo " TODOS OS TESTES PASSARAM"
  echo ""
  echo " Abra no browser: http://localhost:8000"
  echo " Para encerrar o servidor: Ctrl+C"
  echo "=================================================="
  wait $WEB_PID
else
  echo "⚠️  Interface retornou status $HTTP"
  kill $WEB_PID 2>/dev/null
fi
