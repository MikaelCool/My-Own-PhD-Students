<p align="center">
  <img src="../image/logo.png" width="700" alt="AutoResearchClaw Logo">
</p>

<h2 align="center"><b>Converse uma ideia. Receba um artigo. Totalmente aut么nomo & autoevolutivo.</b></h2>



<p align="center">
  <b><i><font size="5">Converse com o <a href="#integra莽茫o-openclaw">OpenClaw</a>: "Pesquise X" 鈫?pronto.</font></i></b>
</p>

<p align="center">
  <img src="../image/framework_v2.png" width="100%" alt="AutoResearchClaw Framework">
</p>


<p align="center">
  <a href="../LICENSE"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="MIT License"></a>
  <a href="https://python.org"><img src="https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white" alt="Python 3.11+"></a>
  <a href="#testes"><img src="https://img.shields.io/badge/Tests-1823%20passed-brightgreen?logo=pytest&logoColor=white" alt="1823 Tests Passed"></a>
  <a href="https://github.com/MikaelCool/My-Own-PhD-Students"><img src="https://img.shields.io/badge/GitHub-My_Own_PhD_Students-181717?logo=github" alt="GitHub"></a>
  <a href="#integra莽茫o-openclaw"><img src="https://img.shields.io/badge/OpenClaw-Compatible-ff4444?logo=data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCI+PHBhdGggZD0iTTEyIDJDNi40OCAyIDIgNi40OCAyIDEyczQuNDggMTAgMTAgMTAgMTAtNC40OCAxMC0xMFMxNy41MiAyIDEyIDJ6IiBmaWxsPSJ3aGl0ZSIvPjwvc3ZnPg==" alt="OpenClaw Compatible"></a>
  <a href="https://discord.gg/u4ksqW5P"><img src="https://img.shields.io/badge/Discord-Join%20Community-5865F2?logo=discord&logoColor=white" alt="Discord"></a>
</p>

<p align="center">
  <a href="../README.md">馃嚭馃嚫 English</a> 路
  <a href="README_CN.md">馃嚚馃嚦 涓枃</a> 路
  <a href="README_JA.md">馃嚡馃嚨 鏃ユ湰瑾?/a> 路
  <a href="README_KO.md">馃嚢馃嚪 頃滉淡鞏?/a> 路
  <a href="README_FR.md">馃嚝馃嚪 Fran莽ais</a> 路
  <a href="README_DE.md">馃嚛馃嚜 Deutsch</a> 路
  <a href="README_ES.md">馃嚜馃嚫 Espa帽ol</a> 路
  <a href="README_PT.md">馃嚙馃嚪 Portugu锚s</a> 路
  <a href="README_RU.md">馃嚪馃嚭 袪褍褋褋泻懈泄</a> 路
  <a href="README_AR.md">馃嚫馃嚘 丕賱毓乇亘賷丞</a>
</p>

<p align="center">
  <a href="showcase/SHOWCASE.md">馃弳 Galeria de Artigos</a> 路 <a href="integration-guide.md">馃摉 Guia de Integra莽茫o</a> 路 <a href="https://discord.gg/u4ksqW5P">馃挰 Comunidade Discord</a>
</p>

---

<table>
<tr>
<td width="18%">
<a href="showcase/SHOWCASE.md"><img src="showcase/thumbnails/paper_I_random_matrix-01.png" width="120" alt="Artigo Exemplo"/></a>
</td>
<td valign="middle">
<b>馃弳 Galeria de Artigos Gerados</b><br><br>
<b>8 artigos em 8 dom铆nios</b> 鈥?matem谩tica, estat铆stica, biologia, computa莽茫o, NLP, RL, vis茫o, robustez 鈥?gerados de forma totalmente aut么noma sem interven莽茫o humana.<br><br>
<a href="showcase/SHOWCASE.md"><img src="https://img.shields.io/badge/Ver_Galeria_Completa_鈫?Todos_os_8_Artigos-d73a49?style=for-the-badge" alt="Ver Galeria"></a>
</td>
</tr>
</table>

---

> **馃И Estamos procurando testadores!** Experimente o pipeline com sua pr贸pria ideia de pesquisa 鈥?de qualquer 谩rea 鈥?e [diga-nos o que achou](TESTER_GUIDE.md). Seu feedback molda diretamente a pr贸xima vers茫o. **[鈫?Testing Guide](TESTER_GUIDE.md)** | **[鈫?涓枃娴嬭瘯鎸囧崡](TESTER_GUIDE_CN.md)** | **[鈫?鏃ユ湰瑾炪儐銈广儓銈偆銉塢(TESTER_GUIDE_JA.md)**

---

## 馃敟 News
- **[03/22/2026]** [v0.3.2](https://github.com/MikaelCool/My-Own-PhD-Students/releases/tag/v0.3.2) 鈥?**Suporte multiplataforma + grande estabilidade** 鈥?O AutoResearchClaw agora funciona com qualquer agente compativel com ACP (Claude Code, Codex CLI, Copilot CLI, Gemini CLI, Kimi CLI) e suporta plataformas de mensagens (Discord, Telegram, Lark, WeChat) via ponte OpenClaw. Novo backend de geracao de codigo CLI-agent que delega os Stages 10 e 13 a agentes CLI externos com controle de orcamento e gerenciamento de timeout. Inclui sistema anti-fabricacao (VerifiedRegistry + loop de diagnostico e reparo), 100+ correcoes de bugs, refatoracao modular do executor, auto-deteccao de `--resume`, endurecimento de retries LLM e correcoes da comunidade.
- **[03/18/2026]** [v0.3.1](https://github.com/MikaelCool/My-Own-PhD-Students/releases/tag/v0.3.1) 鈥?**OpenCode Beast Mode + Community Contributions** 鈥?New "Beast Mode" routes complex code generation to [OpenCode](https://github.com/anomalyco/opencode) with automatic complexity scoring and graceful fallback. Added Novita AI provider support, thread-safety hardening, improved LLM output parsing robustness, and 20+ bug fixes from community PRs and internal audit.
- **[03/17/2026]** [v0.3.0](https://github.com/MikaelCool/My-Own-PhD-Students/releases/tag/v0.3.0) 鈥?**MetaClaw Integration** 鈥?AutoResearchClaw now supports [MetaClaw](https://github.com/aiming-lab/MetaClaw) cross-run learning: pipeline failures 鈫?structured lessons 鈫?reusable skills, injected into all 23 stages. **+18.3%** robustness in controlled experiments. Opt-in (`metaclaw_bridge.enabled: true`), fully backward-compatible. See [Integration Guide](#-metaclaw-integration).
- **[03/16/2026]** [v0.2.0](https://github.com/MikaelCool/My-Own-PhD-Students/releases/tag/v0.2.0) 鈥?Three multi-agent subsystems (CodeAgent, BenchmarkAgent, FigureAgent), hardened Docker sandbox with network-policy-aware execution, 4-round paper quality audit (AI-slop detection, 7-dim review scoring, NeurIPS checklist), and 15+ bug fixes from production runs.
- **[03/15/2026]** [v0.1.0](https://github.com/MikaelCool/My-Own-PhD-Students/releases/tag/v0.1.0) 鈥?We release AutoResearchClaw: a fully autonomous 23-stage research pipeline that turns a single research idea into a conference-ready paper. No human intervention required.

---

## 鈿?Um Comando. Um Artigo.

```bash
pip install -e . && researchclaw setup && researchclaw init && researchclaw run --topic "Your research idea here" --auto-approve
```


---

## 馃 O Que 脡 Isto?

**Voc锚 pensa. AutoResearchClaw escreve.**

Forne莽a um t贸pico de pesquisa 鈥?receba de volta um artigo acad锚mico completo com literatura real do OpenAlex, Semantic Scholar & arXiv, experimentos em sandbox com detec莽茫o autom谩tica de hardware (GPU/MPS/CPU), an谩lise estat铆stica, revis茫o por pares multi-agente, e LaTeX pronto para confer锚ncia mirando NeurIPS/ICML/ICLR. Sem bab谩. Sem copiar e colar. Sem refer锚ncias alucinadas.

<table>
<tr><td>馃搫</td><td><code>paper_draft.md</code></td><td>Artigo acad锚mico completo (Introdu莽茫o, Trabalhos Relacionados, M茅todo, Experimentos, Resultados, Conclus茫o)</td></tr>
<tr><td>馃搻</td><td><code>paper.tex</code></td><td>LaTeX pronto para confer锚ncia (templates NeurIPS / ICLR / ICML)</td></tr>
<tr><td>馃摎</td><td><code>references.bib</code></td><td>Refer锚ncias BibTeX reais do OpenAlex, Semantic Scholar e arXiv 鈥?auto-podadas para corresponder 脿s cita莽玫es inline</td></tr>
<tr><td>馃攳</td><td><code>verification_report.json</code></td><td>Verifica莽茫o de integridade + relev芒ncia de cita莽玫es em 4 camadas (arXiv, CrossRef, DataCite, LLM)</td></tr>
<tr><td>馃И</td><td><code>experiment runs/</code></td><td>C贸digo gerado + resultados do sandbox + m茅tricas JSON estruturadas</td></tr>
<tr><td>馃搳</td><td><code>charts/</code></td><td>Gr谩ficos de compara莽茫o de condi莽玫es gerados automaticamente com barras de erro e intervalos de confian莽a</td></tr>
<tr><td>馃摑</td><td><code>reviews.md</code></td><td>Revis茫o por pares multi-agente com verifica莽玫es de consist锚ncia metodologia-evid锚ncia</td></tr>
<tr><td>馃К</td><td><code>evolution/</code></td><td>Li莽玫es de autoaprendizagem extra铆das de cada execu莽茫o</td></tr>
<tr><td>馃摝</td><td><code>deliverables/</code></td><td>Todas as sa铆das finais em uma pasta 鈥?pronto para compilar no Overleaf</td></tr>
</table>

O pipeline roda **de ponta a ponta sem interven莽茫o humana**. Quando experimentos falham, ele se auto-repara. Quando hip贸teses n茫o se sustentam, ele pivota. Quando cita莽玫es s茫o falsas, ele as elimina.

馃實 **Execute em qualquer lugar.** O AutoResearchClaw n茫o est谩 preso a uma 煤nica plataforma. Use-o de forma independente via CLI, conecte-o ao [OpenClaw](https://github.com/openclaw/openclaw), ou integre-o com qualquer agente compat铆vel com ACP 鈥?馃 Claude Code, 馃捇 Codex CLI, 馃悪 Copilot CLI, 鈾?Gemini CLI, 馃寵 Kimi CLI, e muito mais. Gra莽as 脿 ponte de mensagens do OpenClaw, voc锚 pode iniciar uma pesquisa completa pelo 馃挰 Discord, 鉁堬笍 Telegram, 馃惁 Lark (椋炰功), 馃挌 WeChat, ou qualquer plataforma que sua equipe j谩 utiliza. Um t贸pico na entrada, um artigo na sa铆da 鈥?n茫o importa de onde voc锚 digita.

---

## 馃殌 In铆cio R谩pido

```bash
# 1. Clone & instale
git clone https://github.com/MikaelCool/My-Own-PhD-Students.git
cd My-Own-PhD-Students
python3 -m venv .venv && source .venv/bin/activate
pip install -e .

# 2. Setup (interativo 鈥?instala OpenCode beast mode, verifica Docker/LaTeX)
researchclaw setup

# 3. Configure
researchclaw init          # Interativo: escolha provedor LLM, cria config.arc.yaml
# Ou manualmente: cp config.researchclaw.example.yaml config.arc.yaml

# 4. Execute
export OPENAI_API_KEY="sk-..."
researchclaw run --config config.arc.yaml --topic "Your research idea" --auto-approve
```

Sa铆da 鈫?`artifacts/rc-YYYYMMDD-HHMMSS-<hash>/deliverables/` 鈥?LaTeX, BibTeX, c贸digo de experimentos, gr谩ficos prontos para compila莽茫o.

<details>
<summary>馃摑 Configura莽茫o m铆nima necess谩ria</summary>

```yaml
project:
  name: "my-research"

research:
  topic: "Your research topic here"

llm:
  base_url: "https://api.openai.com/v1"
  api_key_env: "OPENAI_API_KEY"
  primary_model: "gpt-4o"
  fallback_models: ["gpt-4o-mini"]

experiment:
  mode: "sandbox"
  sandbox:
    python_path: ".venv/bin/python"
```

</details>

---

## 馃 O Que o Torna Diferente

| Capacidade | Como Funciona |
|-----------|-------------|
| **馃攧 Loop PIVOT / REFINE** | O Est谩gio 15 decide autonomamente: PROCEED, REFINE (ajustar par芒metros) ou PIVOT (nova dire莽茫o). Artefatos versionados automaticamente. |
| **馃 Debate Multi-Agente** | Gera莽茫o de hip贸teses, an谩lise de resultados e revis茫o por pares usam debate estruturado com m煤ltiplas perspectivas. |
| **馃К Autoaprendizagem** | Li莽玫es extra铆das por execu莽茫o (justificativa de decis玫es, avisos de runtime, anomalias em m茅tricas) com decaimento temporal de 30 dias. Execu莽玫es futuras aprendem com erros passados. |
| **馃摎 Base de Conhecimento** | Cada execu莽茫o constr贸i uma KB estruturada com 6 categorias (decis玫es, experimentos, descobertas, literatura, quest玫es, revis玫es). |
| **馃洝锔?Sentinel Watchdog** | Monitor de qualidade em segundo plano: detec莽茫o de NaN/Inf, consist锚ncia artigo-evid锚ncia, pontua莽茫o de relev芒ncia de cita莽玫es, guarda anti-fabrica莽茫o. |

---

## 馃 Integra莽茫o OpenClaw

<table>
<tr>

**AutoResearchClaw 茅 um servi莽o compat铆vel com [OpenClaw](https://github.com/openclaw/openclaw).** Instale-o no OpenClaw e inicie pesquisa aut么noma com uma 煤nica mensagem 鈥?ou use-o de forma independente via CLI, Claude Code ou qualquer assistente de codifica莽茫o IA.

</tr>
</table>

### 馃殌 Usar com OpenClaw (Recomendado)

Se voc锚 j谩 usa o [OpenClaw](https://github.com/openclaw/openclaw) como seu assistente de IA:

```
1锔忊儯  Compartilhe a URL do reposit贸rio GitHub com o OpenClaw
2锔忊儯  O OpenClaw l锚 automaticamente RESEARCHCLAW_AGENTS.md 鈫?entende o pipeline
3锔忊儯  Diga: "Pesquise [seu t贸pico]"
4锔忊儯  Pronto 鈥?o OpenClaw clona, instala, configura, executa e retorna os resultados
```

**脡 isso.** O OpenClaw gerencia `git clone`, `pip install`, configura莽茫o e execu莽茫o do pipeline automaticamente. Voc锚 apenas conversa.

<details>
<summary>馃挕 O que acontece por baixo dos panos</summary>

1. O OpenClaw l锚 `RESEARCHCLAW_AGENTS.md` 鈫?aprende o papel de orquestrador de pesquisa
2. O OpenClaw l锚 `README.md` 鈫?entende a instala莽茫o e estrutura do pipeline
3. O OpenClaw copia `config.researchclaw.example.yaml` 鈫?`config.yaml`
4. Solicita sua chave de API do LLM (ou usa sua vari谩vel de ambiente)
5. Executa `pip install -e .` + `researchclaw run --topic "..." --auto-approve`
6. Retorna o artigo, LaTeX, experimentos e cita莽玫es

</details>

### 馃攲 Bridge OpenClaw (Avan莽ado)

Para integra莽茫o mais profunda, o AutoResearchClaw inclui um **sistema de adaptadores bridge** com 6 capacidades opcionais:

```yaml
# config.arc.yaml
openclaw_bridge:
  use_cron: true              # 鈴?Execu莽玫es de pesquisa agendadas
  use_message: true           # 馃挰 Notifica莽玫es de progresso (Discord/Slack/Telegram)
  use_memory: true            # 馃 Persist锚ncia de conhecimento entre sess玫es
  use_sessions_spawn: true    # 馃攢 Criar sub-sess玫es paralelas para est谩gios concorrentes
  use_web_fetch: true         # 馃寪 Busca web ao vivo durante revis茫o de literatura
  use_browser: false          # 馃枼锔?Coleta de artigos baseada em navegador
```

Cada flag ativa um protocolo de adaptador tipado. Quando o OpenClaw fornece essas capacidades, os adaptadores as consomem sem altera莽玫es no c贸digo. Consulte [`integration-guide.md`](integration-guide.md) para detalhes completos.

### ACP (Agent Client Protocol)

O AutoResearchClaw pode usar **qualquer agente de codifica莽茫o compat铆vel com ACP** como seu backend LLM 鈥?sem necessidade de chaves de API. O agente se comunica via [acpx](https://github.com/openclaw/acpx), mantendo uma 煤nica sess茫o persistente ao longo de todos os 23 est谩gios do pipeline.

| Agente | Comando | Notas |
|-------|---------|-------|
| Claude Code | `claude` | Anthropic |
| Codex CLI | `codex` | OpenAI |
| Copilot CLI | `gh` | GitHub |
| Gemini CLI | `gemini` | Google |
| OpenCode | `opencode` | SST |
| Kimi CLI | `kimi` | Moonshot |

```yaml
# config.yaml 鈥?exemplo ACP
llm:
  provider: "acp"
  acp:
    agent: "claude"   # Qualquer comando CLI de agente compat铆vel com ACP
    cwd: "."          # Diret贸rio de trabalho para o agente
  # Sem base_url ou api_key necess谩rios 鈥?o agente gerencia sua pr贸pria autentica莽茫o.
```

```bash
# Basta executar 鈥?o agente usa suas pr贸prias credenciais
researchclaw run --config config.yaml --topic "Your research idea" --auto-approve
```

### 馃洜锔?Outras Formas de Executar

| M茅todo | Como |
|--------|------|
| **CLI Independente** | `researchclaw setup` 鈫?`researchclaw init` 鈫?`researchclaw run --topic "..." --auto-approve` |
| **API Python** | `from researchclaw.pipeline import Runner; Runner(config).run()` |
| **Claude Code** | L锚 `RESEARCHCLAW_CLAUDE.md` 鈥?basta dizer *"Execute pesquisa sobre [t贸pico]"* |
| **Copilot CLI** | `researchclaw run --topic "..."` com `llm.acp.agent: "gh"` |
| **OpenCode** | L锚 `.claude/skills/` 鈥?mesma interface em linguagem natural |
| **Qualquer CLI de IA** | Forne莽a `RESEARCHCLAW_AGENTS.md` como contexto 鈫?o agente faz bootstrap automaticamente |

---

## 馃敩 Pipeline: 23 Est谩gios, 8 Fases

```
Fase A: Escopo da Pesquisa           Fase E: Execu莽茫o de Experimentos
  1. TOPIC_INIT                        12. EXPERIMENT_RUN
  2. PROBLEM_DECOMPOSE                 13. ITERATIVE_REFINE  鈫?auto-reparo

Fase B: Descoberta de Literatura     Fase F: An谩lise & Decis茫o
  3. SEARCH_STRATEGY                   14. RESULT_ANALYSIS    鈫?multi-agente
  4. LITERATURE_COLLECT  鈫?API real    15. RESEARCH_DECISION  鈫?PIVOT/REFINE
  5. LITERATURE_SCREEN   [gate]
  6. KNOWLEDGE_EXTRACT                 Fase G: Escrita do Artigo
                                       16. PAPER_OUTLINE
Fase C: S铆ntese de Conhecimento       17. PAPER_DRAFT
  7. SYNTHESIS                         18. PEER_REVIEW        鈫?verif. evid锚ncia
  8. HYPOTHESIS_GEN    鈫?debate        19. PAPER_REVISION

Fase D: Design de Experimentos      Fase H: Finaliza莽茫o
  9. EXPERIMENT_DESIGN   [gate]        20. QUALITY_GATE      [gate]
 10. CODE_GENERATION                   21. KNOWLEDGE_ARCHIVE
 11. RESOURCE_PLANNING                 22. EXPORT_PUBLISH     鈫?LaTeX
                                       23. CITATION_VERIFY    鈫?verif. relev芒ncia
```

> **Est谩gios gate** (5, 9, 20) pausam para aprova莽茫o humana ou aprovam automaticamente com `--auto-approve`. Em caso de rejei莽茫o, o pipeline faz rollback.

> **Loops de decis茫o**: O Est谩gio 15 pode acionar REFINE (鈫?Est谩gio 13) ou PIVOT (鈫?Est谩gio 8), com versionamento autom谩tico de artefatos.

<details>
<summary>馃搵 O Que Cada Fase Faz</summary>

| Fase | O Que Acontece |
|------|----------------|
| **A: Escopo** | O LLM decomp玫e o t贸pico em uma 谩rvore de problemas estruturada com quest玫es de pesquisa |
| **A+: Hardware** | Detecta automaticamente GPU (NVIDIA CUDA / Apple MPS / apenas CPU), avisa se o hardware local 茅 limitado, adapta a gera莽茫o de c贸digo adequadamente |
| **B: Literatura** | Busca multi-fonte (OpenAlex 鈫?Semantic Scholar 鈫?arXiv) por artigos reais, triagem por relev芒ncia, extra莽茫o de fichas de conhecimento |
| **C: S铆ntese** | Agrupa descobertas, identifica lacunas de pesquisa, gera hip贸teses test谩veis via debate multi-agente |
| **D: Design** | Projeta plano de experimento, gera Python execut谩vel com consci锚ncia de hardware (tier de GPU 鈫?sele莽茫o de pacotes), estima necessidades de recursos |
| **E: Execu莽茫o** | Executa experimentos em sandbox, detecta NaN/Inf e bugs de runtime, auto-repara c贸digo via reparo direcionado por LLM |
| **F: An谩lise** | An谩lise multi-agente dos resultados; decis茫o aut么noma PROCEED / REFINE / PIVOT com justificativa |
| **G: Escrita** | Outline 鈫?reda莽茫o se莽茫o por se莽茫o (5.000-6.500 palavras) 鈫?revis茫o por pares (com consist锚ncia metodologia-evid锚ncia) 鈫?revis茫o com guarda de tamanho |
| **H: Finaliza莽茫o** | Quality gate, arquivamento de conhecimento, exporta莽茫o LaTeX com template de confer锚ncia, verifica莽茫o de integridade + relev芒ncia de cita莽玫es |

</details>

---

## 鉁?Funcionalidades Principais

| Funcionalidade | Descri莽茫o |
|---------|------------|
| **馃摎 Literatura Multi-Fonte** | Artigos reais do OpenAlex, Semantic Scholar & arXiv 鈥?expans茫o de consultas, deduplica莽茫o, circuit breaker com degrada莽茫o graciosa |
| **馃攳 Verifica莽茫o de Cita莽玫es em 4 Camadas** | Verifica莽茫o de arXiv ID 鈫?CrossRef/DataCite DOI 鈫?correspond锚ncia de t铆tulo no Semantic Scholar 鈫?pontua莽茫o de relev芒ncia por LLM. Refer锚ncias alucinadas removidas automaticamente. |
| **馃枼锔?Execu莽茫o com Consci锚ncia de Hardware** | Detecta automaticamente GPU (NVIDIA CUDA / Apple MPS / apenas CPU) e adapta gera莽茫o de c贸digo, imports e escala de experimentos |
| **馃 OpenCode Beast Mode** | Experimentos complexos roteados automaticamente para o [OpenCode](https://github.com/anomalyco/opencode) 鈥?gera projetos multi-arquivo com arquiteturas customizadas, loops de treinamento e estudos de abla莽茫o. Instale via `researchclaw setup`. |
| **馃И Experimentos em Sandbox** | C贸digo validado por AST, harness imut谩vel, fast-fail para NaN/Inf, reparo auto-repar谩vel, refinamento iterativo (at茅 10 rodadas), captura de resultados parciais |
| **馃摑 Escrita com Qualidade de Confer锚ncia** | Templates NeurIPS/ICML/ICLR, reda莽茫o se莽茫o por se莽茫o (5.000-6.500 palavras), guarda anti-fabrica莽茫o, guarda de tamanho na revis茫o, imposi莽茫o anti-disclaimer |
| **馃搻 Troca de Template** | `neurips_2025`, `iclr_2026`, `icml_2026` 鈥?Markdown 鈫?LaTeX com matem谩tica, tabelas, figuras, refer锚ncias cruzadas, `\cite{}` |
| **馃殾 Quality Gates** | 3 gates com human-in-the-loop (Est谩gios 5, 9, 20) com rollback. Pule com `--auto-approve`. |

---

## 馃 Integra莽茫o MetaClaw

**AutoResearchClaw + [MetaClaw](https://github.com/aiming-lab/MetaClaw) = Um pipeline que aprende com cada execu莽茫o.**

MetaClaw adiciona **transfer锚ncia de conhecimento entre execu莽玫es** ao AutoResearchClaw. Quando ativado, o pipeline captura automaticamente li莽玫es de falhas e avisos, converte-as em habilidades reutiliz谩veis e injeta essas habilidades em todos os 23 est谩gios do pipeline em execu莽玫es subsequentes 鈥?para que os mesmos erros nunca se repitam.

### Como Funciona

```
Run N executa 鈫?falhas/avisos capturados como Lessons
                      鈫?
          MetaClaw Lesson 鈫?convers茫o em Skill
                      鈫?
          Arquivos arc-* Skill armazenados em ~/.metaclaw/skills/
                      鈫?
Run N+1 鈫?build_overlay() injeta skills em cada prompt LLM
                      鈫?
          LLM evita armadilhas conhecidas 鈫?maior qualidade, menos retentativas
```

### Configura莽茫o R谩pida

```bash
# 1. Instale o MetaClaw (se ainda n茫o tiver)
pip install metaclaw

# 2. Ative na sua configura莽茫o
```

```yaml
# config.arc.yaml
metaclaw_bridge:
  enabled: true
  proxy_url: "http://localhost:30000"        # Proxy MetaClaw (opcional)
  skills_dir: "~/.metaclaw/skills"          # Onde as skills s茫o armazenadas
  fallback_url: "https://api.openai.com/v1" # Fallback direto para LLM
  fallback_api_key: ""                      # Chave de API para URL de fallback
  lesson_to_skill:
    enabled: true
    min_severity: "warning"                 # Converte warnings + errors
    max_skills_per_run: 3
```

```bash
# 3. Execute normalmente 鈥?MetaClaw funciona de forma transparente
researchclaw run --config config.arc.yaml --topic "Your idea" --auto-approve
```

Ap贸s cada execu莽茫o, verifique `~/.metaclaw/skills/arc-*/SKILL.md` para ver as skills que seu pipeline aprendeu.

### Resultados dos Experimentos

Em experimentos A/B controlados (mesmo t贸pico, mesmo LLM, mesma configura莽茫o):

| M茅trica | Baseline | Com MetaClaw | Melhoria |
|---------|----------|---------------|----------|
| Taxa de retentativa por est谩gio | 10.5% | 7.9% | **-24.8%** |
| Contagem de ciclos REFINE | 2.0 | 1.2 | **-40.0%** |
| Conclus茫o de est谩gios do pipeline | 18/19 | 19/19 | **+5.3%** |
| Pontua莽茫o de robustez geral (composta) | 0.714 | 0.845 | **+18.3%** |

> A pontua莽茫o composta de robustez 茅 uma m茅dia ponderada da taxa de conclus茫o de est谩gios (40%), redu莽茫o de retentativas (30%) e efici锚ncia de ciclos REFINE (30%).

### Compatibilidade Retroativa

- **Padr茫o: DESATIVADO.** Se `metaclaw_bridge` estiver ausente ou `enabled: false`, o pipeline funciona exatamente como antes.
- **Sem novas depend锚ncias.** MetaClaw 茅 opcional 鈥?o pipeline principal funciona sem ele.
- **Todos os 1.823 testes existentes passam** com o c贸digo de integra莽茫o presente.

---

## 鈿欙笍 Refer锚ncia de Configura莽茫o

<details>
<summary>Clique para expandir a refer锚ncia completa de configura莽茫o</summary>

```yaml
# === Projeto ===
project:
  name: "my-research"              # Identificador do projeto
  mode: "docs-first"               # docs-first | semi-auto | full-auto

# === Pesquisa ===
research:
  topic: "..."                     # T贸pico de pesquisa (obrigat贸rio)
  domains: ["ml", "nlp"]           # Dom铆nios de pesquisa para busca de literatura
  daily_paper_count: 8             # Artigos alvo por consulta de busca
  quality_threshold: 4.0           # Pontua莽茫o m铆nima de qualidade para artigos

# === Runtime ===
runtime:
  timezone: "America/New_York"     # Para timestamps
  max_parallel_tasks: 3            # Limite de experimentos concorrentes
  approval_timeout_hours: 12       # Timeout de est谩gios gate
  retry_limit: 2                   # Contagem de retentativas em falha de est谩gio

# === LLM ===
llm:
  provider: "openai-compatible"    # openai | openrouter | deepseek | minimax | acp | openai-compatible
  base_url: "https://..."          # Endpoint da API (obrigat贸rio para openai-compatible)
  api_key_env: "OPENAI_API_KEY"    # Vari谩vel de ambiente para chave da API (obrigat贸rio para openai-compatible)
  api_key: ""                      # Ou insira a chave diretamente aqui
  primary_model: "gpt-4o"          # Modelo prim谩rio
  fallback_models: ["gpt-4o-mini"] # Cadeia de fallback
  s2_api_key: ""                   # Chave API do Semantic Scholar (opcional, limites de taxa maiores)
  acp:                             # Usado apenas quando provider: "acp"
    agent: "claude"                # Comando CLI do agente ACP (claude, codex, gemini, etc.)
    cwd: "."                       # Diret贸rio de trabalho para o agente

# === Experimento ===
experiment:
  mode: "sandbox"                  # simulated | sandbox | docker | ssh_remote
  time_budget_sec: 300             # Tempo m谩ximo de execu莽茫o por run (padr茫o: 300s)
  max_iterations: 10               # M谩ximo de itera莽玫es de otimiza莽茫o
  metric_key: "val_loss"           # Nome da m茅trica prim谩ria
  metric_direction: "minimize"     # minimize | maximize
  sandbox:
    python_path: ".venv/bin/python"
    gpu_required: false
    allowed_imports: [math, random, json, csv, numpy, torch, sklearn]
    max_memory_mb: 4096
  docker:
    image: "researchclaw/experiment:latest"
    network_policy: "setup_only"   # none | setup_only | pip_only | full
    gpu_enabled: true
    memory_limit_mb: 8192
    auto_install_deps: true        # Detec莽茫o autom谩tica de imports 鈫?requirements.txt
  ssh_remote:
    host: ""                       # Hostname do servidor GPU
    gpu_ids: []                    # IDs de GPU dispon铆veis
    remote_workdir: "/tmp/researchclaw_experiments"
  opencode:                          # OpenCode Beast Mode (auto-instalado via `researchclaw setup`)
    enabled: true                    # Interruptor principal (padr茫o: true)
    auto: true                       # Acionamento autom谩tico sem confirma莽茫o (padr茫o: true)
    complexity_threshold: 0.2        # 0.0-1.0 鈥?maior = s贸 aciona em experimentos complexos
    model: ""                        # Modelo override (vazio = usa llm.primary_model)
    timeout_sec: 600                 # M谩ximo de segundos para gera莽茫o OpenCode
    max_retries: 1                   # Contagem de retentativas em falha
    workspace_cleanup: true          # Remove workspace tempor谩rio ap贸s coleta

# === Exporta莽茫o ===
export:
  target_conference: "neurips_2025"  # neurips_2025 | iclr_2026 | icml_2026
  authors: "Anonymous"
  bib_file: "references"

# === Prompts ===
prompts:
  custom_file: ""                  # Caminho para YAML de prompts customizados (vazio = padr玫es)

# === Seguran莽a ===
security:
  hitl_required_stages: [5, 9, 20] # Est谩gios que requerem aprova莽茫o humana
  allow_publish_without_approval: false
  redact_sensitive_logs: true

# === Base de Conhecimento ===
knowledge_base:
  backend: "markdown"              # markdown | obsidian
  root: "docs/kb"

# === Notifica莽玫es ===
notifications:
  channel: "console"               # console | discord | slack
  target: ""

# === MetaClaw Bridge (Opcional) ===
metaclaw_bridge:
  enabled: false                   # Defina como true para ativar aprendizado entre execu莽玫es
  proxy_url: "http://localhost:30000"  # URL do proxy MetaClaw
  skills_dir: "~/.metaclaw/skills" # Onde as skills arc-* s茫o armazenadas
  fallback_url: ""                 # Fallback direto para LLM quando o proxy est谩 fora
  fallback_api_key: ""             # Chave de API para endpoint de fallback
  lesson_to_skill:
    enabled: true                  # Auto-converter li莽玫es em skills
    min_severity: "warning"        # Severidade m铆nima para converter
    max_skills_per_run: 3          # M谩ximo de novas skills por execu莽茫o do pipeline

# === Bridge OpenClaw ===
openclaw_bridge:
  use_cron: false                  # Execu莽玫es de pesquisa agendadas
  use_message: false               # Notifica莽玫es de progresso
  use_memory: false                # Persist锚ncia de conhecimento entre sess玫es
  use_sessions_spawn: false        # Criar sub-sess玫es paralelas
  use_web_fetch: false             # Busca web ao vivo
  use_browser: false               # Coleta de artigos baseada em navegador
```

</details>

---

## 馃檹 Agradecimentos

Inspirado por:

- 馃敩 [AI Scientist](https://github.com/SakanaAI/AI-Scientist) (Sakana AI) 鈥?Pioneiro em pesquisa automatizada
- 馃 [AutoResearch](https://github.com/karpathy/autoresearch) (Andrej Karpathy) 鈥?Automa莽茫o de pesquisa de ponta a ponta
- 馃寪 [FARS](https://analemma.ai/blog/introducing-fars/) (Analemma) 鈥?Fully Automated Research System

---

## 馃搫 Licen莽a

MIT 鈥?veja [LICENSE](../LICENSE) para detalhes.

---

## 馃搶 Cita莽茫o

Se voc锚 achar o AutoResearchClaw 煤til, por favor cite:

```bibtex
@misc{liu2026autoresearchclaw,
  author       = {Liu, Jiaqi and Xia, Peng and Han, Siwei and Qiu, Shi and Zhang, Letian and Chen, Guiming  and Tu, Haoqin and Yang, Xinyu and and Zhou, Jiawei and Zhu, Hongtu and Li, Yun and Zhou, Yuyin and Zheng, Zeyu and Xie, Cihang and Ding, Mingyu and Yao, Huaxiu},
  title        = {AutoResearchClaw: Fully Autonomous Research from Idea to Paper},
  year         = {2026},
  organization = {GitHub},
  url          = {https://github.com/MikaelCool/My-Own-PhD-Students},
}
```

<p align="center">
  <sub>Constru铆do com 馃 pela equipe AutoResearchClaw</sub>
</p>
