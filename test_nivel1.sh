#!/bin/bash
# ============================================================
# Nível 1 — Teste do Q2 Token Linter
# Sem Docker, sem API key, sem banco de dados
# Tempo: ~30 segundos
# ============================================================

echo "=================================================="
echo " TESTE NÍVEL 1 — Q2 Token Linter"
echo "=================================================="

# 1. Instala dependências (apenas Python padrão)
echo ""
echo "▶ Instalando dependências..."
pip install python-dotenv --break-system-packages -q

# 2. Cria componente COM violação
echo "▶ Criando componente com hex hard-coded..."
mkdir -p components/BadButton
cat > components/BadButton/BadButton.tsx << 'TSX'
const BadButton = () => (
  <button style={{ backgroundColor: '#FF5733', color: '#FFFFFF' }}>
    Clique aqui
  </button>
);
export default BadButton;
TSX

echo ""
echo "--- TESTE A: Componente COM hex (deve BLOQUEAR) ---"
python3 scripts/token_lint.py
echo "Exit code: $? (esperado: 1)"

# 3. Corrige o componente
echo ""
echo "▶ Corrigindo componente..."
cat > components/BadButton/BadButton.tsx << 'TSX'
const BadButton = () => (
  <button style={{
    backgroundColor: 'var(--ds-color-action-primary)',
    color: 'var(--ds-color-text-inverse)'
  }}>
    Clique aqui
  </button>
);
export default BadButton;
TSX

echo ""
echo "--- TESTE B: Componente SEM hex (deve APROVAR) ---"
python3 scripts/token_lint.py
echo "Exit code: $? (esperado: 0)"

# 4. Limpa
rm -rf components/BadButton
echo ""
echo "=================================================="
echo " Nível 1 concluído."
echo "=================================================="
