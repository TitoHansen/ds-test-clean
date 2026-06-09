# Design System com IA — Contexto do projeto

## O que é este projeto
Sistema de governança e geração de componentes para Design System operado por IA.
Stack: Python 3.9 · pgvector · FastAPI · Anthropic API · OpenAI API · Docker

## O que já está construído e funcionando
- scripts/token_lint.py — Q2 gate determinístico (detecta hex hard-coded)
- scripts/ingest.py — ingere tokens e regras no RAG (pgvector)
- scripts/query.py — consulta RAG de Referência e de Decisão
- scripts/review_agent.py — Q4 agente de revisão via Claude API
- scripts/adr_generator.py — gera ADRs automaticamente
- web/main.py — FastAPI com /api/review, /api/query, /api/health
- web/index.html — painel para designers no browser
- docker-compose.yml — PostgreSQL 16 + pgvector

## Modelo Claude disponível nesta conta
claude-sonnet-4-6

## O que precisa ser construído agora (em ordem)
1. scripts/token_mapper.py — mapeia hex para tokens via pgvector
2. POST /api/transform em web/main.py — refatora componente legado
3. POST /api/generate em web/main.py — gera componente novo
4. scripts/figma_reader.py — lê node do Figma via REST API
5. POST /api/from-figma em web/main.py — gera componente a partir do Figma
6. Novos formulários em web/index.html para as 3 capacidades

## Arquitetura das 3 capacidades
Capacidade 1 — POST /api/generate
  Input: { name, description, variants[], a11y, proposed_by }
  Fluxo: Q3 busca duplicatas → Claude gera TSX+Stories → Q2 valida → Q4 avalia → ADR gerado
  Output: { tsx_code, stories_code, tokens_used, adr_number, score, approved }

Capacidade 2 — POST /api/transform
  Input: { component_name, component_code }
  Fluxo: Q2 lista violações → token_mapper mapeia hex→token → Claude refatora → Q2 valida
  Output: { transformed_code, violations_found, violations_fixed, tokens_mapped, diff }

Capacidade 3 — POST /api/from-figma
  Input: { file_key, node_id, component_name, proposed_by }
  Fluxo: figma_reader extrai propriedades → token_mapper mapeia → Q3 contexto → Claude gera → Q2+Q4
  Output: { tsx_code, token_mapping, unmapped_values, score, adr_number }

## Regras de implementação
- Zero hex hard-coded em qualquer output
- Sempre consultar o RAG antes de gerar (Q3)
- Sempre validar com token_lint depois de gerar (Q2)
- Modelo: claude-sonnet-4-6
- DATABASE_URL: postgresql://ds_user:ds_pass@localhost:5432/design_system

## Começar por
scripts/token_mapper.py — é a dependência das 3 capacidades
