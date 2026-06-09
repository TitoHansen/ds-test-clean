# ADR-001: ADR-001: Introdução do Componente Badge para Indicação de Status

**Status:** proposed | **Data:** 2026-06-08
**Solicitado por:** Time de Produto

## Contexto

O Time de Produto identificou a necessidade de um componente padronizado para comunicar estados de status em listas e tabelas. Atualmente, cada equipe implementa sua própria solução visual para representar estados como sucesso, alerta, erro e informação, resultando em inconsistências visuais e semânticas no produto. A ausência deste componente no Design System força times a criarem soluções ad-hoc, aumentando débito técnico e fragmentando a experiência do usuário.

## Decisão

Criar o componente Badge com quatro variantes semânticas: success (verde), warning (amarelo), error (vermelho) e info (azul). O componente será baseado em elemento HTML span, suportará texto curto descritivo, incluirá ícone opcional e será acessível via atributos ARIA adequados. As variantes serão controladas via prop variant, com tokens de cor provenientes do sistema de tokens existente.

## Justificativa

Padronizar a comunicação de status reduz inconsistências visuais e melhora a experiência do usuário. As quatro variantes cobrem os casos de uso universais de feedback de estado. Utilizar tokens de cor garante consistência com o tema e facilita futuras mudanças de branding. A semântica via ARIA assegura acessibilidade para usuários de tecnologias assistivas. A abordagem baseada em prop única simplifica a API e reduz a curva de aprendizado para desenvolvedores.

## Alternativas

['Usar tags coloridas genéricas sem semântica definida: descartado por não comunicar claramente o significado dos estados e dificultar acessibilidade.', 'Ícones standalone sem texto: descartado por depender exclusivamente de percepção de cor, violando WCAG 1.4.1.', 'Estender componente Chip/Tag existente: não aplicável pois o DS ainda não possui tal componente.', 'Manter implementações por equipe: descartado por perpetuar inconsistências e aumentar débito técnico.']

## Consequências

{'positivas': ['Consistência visual e semântica na comunicação de status em todo o produto.', 'Redução de implementações duplicadas e débito técnico entre times.', 'Acessibilidade garantida desde a concepção com suporte a leitores de tela.', 'Facilidade de manutenção centralizada, permitindo atualizações globais via tokens.'], 'negativas': ['Times precisarão migrar implementações existentes para o novo componente, gerando esforço pontual de refatoração.', 'As quatro variantes podem não cobrir casos de uso futuros muito específicos, exigindo revisão do ADR.', 'Restrição intencional a texto curto pode limitar casos onde descrições mais longas seriam desejadas.']}

## Componente

Componente: Badge
