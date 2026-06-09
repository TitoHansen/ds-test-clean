# Design System com IA — Como testar

## Nível 1 — Linter apenas (sem dependências externas)

**Tempo:** 30 segundos | **Requer:** Python 3.11+

```bash
bash test_nivel1.sh
```

O que testa:
- Detecta hex hard-coded em componentes (deve bloquear)
- Detecta tokens desconhecidos (aviso)
- Detecta componentes sem ADR (aviso)
- Confirma que componente correto é aprovado (exit 0)

---

## Nível 2 — Sistema completo (com banco e API)

**Tempo:** ~5 minutos | **Requer:** Docker + chaves de API

1. Configure o `.env`:
```bash
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
DATABASE_URL=postgresql://ds_user:ds_pass@localhost:5432/design_system
FIGMA_ACCESS_TOKEN=figd_...
FIGMA_FILE_KEY=seu-file-key
```

2. Execute:
```bash
bash test_nivel2.sh
```

O que testa:
- pgvector sobe e responde
- Ingestão de tokens e regras no RAG
- Consulta ao RAG com similarity score
- Q4 avalia proposta de componente via Claude API
- Interface web responde em localhost:8000

---

## Iniciando apenas a interface web

```bash
# Sobe banco
docker-compose up -d postgres

# Popula o RAG (necessário apenas uma vez)
python3 scripts/ingest.py

# Inicia a interface para designers
uvicorn web.main:app --host 0.0.0.0 --port 8000
```

Acesse em: **http://localhost:8000**

Os designers podem propor componentes e consultar o DS pelo browser, sem terminal.
