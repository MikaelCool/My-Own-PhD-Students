<p align="center">
  <img src="../image/logo.png" width="700" alt="AutoResearchClaw Logo">
</p>

<h2 align="center"><b>Idee besprechen. Paper erhalten. Vollautomatisch & selbstentwickelnd.</b></h2>



<p align="center">
  <b><i><font size="5">Einfach mit <a href="#-openclaw-integration">OpenClaw</a> chatten: "Research X" 鈫?erledigt.</font></i></b>
</p>

<p align="center">
  <img src="../image/framework_v2.png" width="100%" alt="AutoResearchClaw Framework">
</p>


<p align="center">
  <a href="../LICENSE"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="MIT License"></a>
  <a href="https://python.org"><img src="https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white" alt="Python 3.11+"></a>
  <a href="#testing"><img src="https://img.shields.io/badge/Tests-1823%20passed-brightgreen?logo=pytest&logoColor=white" alt="1823 Tests Passed"></a>
  <a href="https://github.com/MikaelCool/My-Own-PhD-Students"><img src="https://img.shields.io/badge/GitHub-My_Own_PhD_Students-181717?logo=github" alt="GitHub"></a>
  <a href="#-openclaw-integration"><img src="https://img.shields.io/badge/OpenClaw-Compatible-ff4444?logo=data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCI+PHBhdGggZD0iTTEyIDJDNi40OCAyIDIgNi40OCAyIDEyczQuNDggMTAgMTAgMTAgMTAtNC40OCAxMC0xMFMxNy41MiAyIDEyIDJ6IiBmaWxsPSJ3aGl0ZSIvPjwvc3ZnPg==" alt="OpenClaw Compatible"></a>
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
  <a href="showcase/SHOWCASE.md">馃弳 Paper-Showcase</a> 路 <a href="integration-guide.md">馃摉 Integrationsanleitung</a> 路 <a href="https://discord.gg/u4ksqW5P">馃挰 Discord-Community</a>
</p>

---

<table>
<tr>
<td width="18%">
<a href="showcase/SHOWCASE.md"><img src="showcase/thumbnails/paper_I_random_matrix-01.png" width="120" alt="Sample Paper"/></a>
</td>
<td valign="middle">
<b>馃弳 Showcase generierter Paper</b><br><br>
<b>8 Paper aus 8 Disziplinen</b> 鈥?Mathematik, Statistik, Biologie, Informatik, NLP, RL, Vision, Robustheit 鈥?vollstaendig autonom generiert ohne menschliches Eingreifen.<br><br>
<a href="showcase/SHOWCASE.md"><img src="https://img.shields.io/badge/View_Full_Showcase_鈫?All_8_Papers-d73a49?style=for-the-badge" alt="View Showcase"></a>
</td>
</tr>
</table>

---

> **馃И Wir suchen Tester!** Teste die Pipeline mit deiner eigenen Forschungsidee 鈥?aus jedem Fachgebiet 鈥?und [sag uns, was du denkst](TESTER_GUIDE.md). Dein Feedback beeinflusst direkt die naechste Version. **[鈫?Testing Guide](TESTER_GUIDE.md)** | **[鈫?涓枃娴嬭瘯鎸囧崡](TESTER_GUIDE_CN.md)** | **[鈫?鏃ユ湰瑾炪儐銈广儓銈偆銉塢(TESTER_GUIDE_JA.md)**

---

## 馃敟 News
- **[03/22/2026]** [v0.3.2](https://github.com/MikaelCool/My-Own-PhD-Students/releases/tag/v0.3.2) 鈥?**Plattformuebergreifende Unterstuetzung + grosse Stabilitaet** 鈥?AutoResearchClaw laeuft jetzt mit jedem ACP-kompatiblen Agenten-Backend (Claude Code, Codex CLI, Copilot CLI, Gemini CLI, Kimi CLI) und unterstuetzt Messaging-Plattformen (Discord, Telegram, Lark, WeChat) ueber die OpenClaw-Bruecke. Neues CLI-Agent-Code-Generierungs-Backend delegiert Stages 10 und 13 an externe CLI-Agenten mit Budgetkontrolle und Timeout-Management. Enthaelt Anti-Fabrication-System (VerifiedRegistry + Experiment-Diagnose- und Reparaturschleife), 100+ Bugfixes, modulares Executor-Refactoring, `--resume` Auto-Erkennung, LLM-Retry-Haertung und Community-Fixes.
- **[03/18/2026]** [v0.3.1](https://github.com/MikaelCool/My-Own-PhD-Students/releases/tag/v0.3.1) 鈥?**OpenCode Beast Mode + Community Contributions** 鈥?New "Beast Mode" routes complex code generation to [OpenCode](https://github.com/anomalyco/opencode) with automatic complexity scoring and graceful fallback. Added Novita AI provider support, thread-safety hardening, improved LLM output parsing robustness, and 20+ bug fixes from community PRs and internal audit.
- **[03/17/2026]** [v0.3.0](https://github.com/MikaelCool/My-Own-PhD-Students/releases/tag/v0.3.0) 鈥?**MetaClaw Integration** 鈥?AutoResearchClaw now supports [MetaClaw](https://github.com/aiming-lab/MetaClaw) cross-run learning: pipeline failures 鈫?structured lessons 鈫?reusable skills, injected into all 23 stages. **+18.3%** robustness in controlled experiments. Opt-in (`metaclaw_bridge.enabled: true`), fully backward-compatible. See [Integration Guide](#-metaclaw-integration).
- **[03/16/2026]** [v0.2.0](https://github.com/MikaelCool/My-Own-PhD-Students/releases/tag/v0.2.0) 鈥?Three multi-agent subsystems (CodeAgent, BenchmarkAgent, FigureAgent), hardened Docker sandbox with network-policy-aware execution, 4-round paper quality audit (AI-slop detection, 7-dim review scoring, NeurIPS checklist), and 15+ bug fixes from production runs.
- **[03/15/2026]** [v0.1.0](https://github.com/MikaelCool/My-Own-PhD-Students/releases/tag/v0.1.0) 鈥?We release AutoResearchClaw: a fully autonomous 23-stage research pipeline that turns a single research idea into a conference-ready paper. No human intervention required.

---

## 鈿?Ein Befehl. Ein Paper.

```bash
pip install -e . && researchclaw setup && researchclaw init && researchclaw run --topic "Your research idea here" --auto-approve
```


---

## 馃 Was ist das?

**Du denkst es. AutoResearchClaw schreibt es.**

Gib ein Forschungsthema ein 鈥?erhalte ein vollstaendiges wissenschaftliches Paper mit echter Literatur von OpenAlex, Semantic Scholar und arXiv, hardwarebewussten Sandbox-Experimenten (automatische GPU/MPS/CPU-Erkennung), statistischer Analyse, Multi-Agenten-Peer-Review und konferenzfertigem LaTeX fuer NeurIPS/ICML/ICLR. Kein Babysitting. Kein Kopieren. Keine halluzinierten Referenzen.

<table>
<tr><td>馃搫</td><td><code>paper_draft.md</code></td><td>Vollstaendiges wissenschaftliches Paper (Einleitung, Verwandte Arbeiten, Methode, Experimente, Ergebnisse, Fazit)</td></tr>
<tr><td>馃搻</td><td><code>paper.tex</code></td><td>Konferenzfertiges LaTeX (NeurIPS / ICLR / ICML Templates)</td></tr>
<tr><td>馃摎</td><td><code>references.bib</code></td><td>Echte BibTeX-Referenzen von OpenAlex, Semantic Scholar und arXiv 鈥?automatisch bereinigt, um Inline-Zitationen zu entsprechen</td></tr>
<tr><td>馃攳</td><td><code>verification_report.json</code></td><td>4-Schicht-Zitationsintegritaets- und Relevanzpruefung (arXiv, CrossRef, DataCite, LLM)</td></tr>
<tr><td>馃И</td><td><code>experiment runs/</code></td><td>Generierter Code + Sandbox-Ergebnisse + strukturierte JSON-Metriken</td></tr>
<tr><td>馃搳</td><td><code>charts/</code></td><td>Automatisch generierte Vergleichsdiagramme mit Fehlerbalken und Konfidenzintervallen</td></tr>
<tr><td>馃摑</td><td><code>reviews.md</code></td><td>Multi-Agenten-Peer-Review mit Methodik-Evidenz-Konsistenzpruefungen</td></tr>
<tr><td>馃К</td><td><code>evolution/</code></td><td>Selbstlernende Erkenntnisse aus jedem Durchlauf</td></tr>
<tr><td>馃摝</td><td><code>deliverables/</code></td><td>Alle finalen Ergebnisse in einem Ordner 鈥?kompilierbereit fuer Overleaf</td></tr>
</table>

Die Pipeline laeuft **vollstaendig ohne menschliches Eingreifen**. Wenn Experimente fehlschlagen, repariert sie sich selbst. Wenn Hypothesen nicht bestaetigt werden, schwenkt sie um. Wenn Zitationen gefaelscht sind, entfernt sie diese.

馃實 **Ueberall ausfuehrbar.** AutoResearchClaw ist nicht an eine einzelne Plattform gebunden. Nutzen Sie es eigenstaendig ueber die CLI, verbinden Sie es mit [OpenClaw](https://github.com/openclaw/openclaw), oder integrieren Sie es mit jedem ACP-kompatiblen AI-Agenten 鈥?馃 Claude Code, 馃捇 Codex CLI, 馃悪 Copilot CLI, 鈾?Gemini CLI, 馃寵 Kimi CLI und mehr. Dank der Messaging-Bruecke von OpenClaw koennen Sie eine komplette Forschung von 馃挰 Discord, 鉁堬笍 Telegram, 馃惁 Lark (椋炰功), 馃挌 WeChat oder jeder anderen Plattform starten, die Ihr Team bereits nutzt. Ein Thema rein, ein Paper raus 鈥?egal wo Sie tippen.

---

## 馃殌 Schnellstart

```bash
# 1. Klonen & installieren
git clone https://github.com/MikaelCool/My-Own-PhD-Students.git
cd My-Own-PhD-Students
python3 -m venv .venv && source .venv/bin/activate
pip install -e .

# 2. Setup (interaktiv 鈥?installiert OpenCode Beast Mode, prueft Docker/LaTeX)
researchclaw setup

# 3. Konfigurieren
researchclaw init          # Interaktiv: LLM-Anbieter waehlen, erstellt config.arc.yaml
# Oder manuell: cp config.researchclaw.example.yaml config.arc.yaml

# 4. Ausfuehren
export OPENAI_API_KEY="sk-..."
researchclaw run --config config.arc.yaml --topic "Your research idea" --auto-approve
```

Ausgabe 鈫?`artifacts/rc-YYYYMMDD-HHMMSS-<hash>/deliverables/` 鈥?kompilierfertiges LaTeX, BibTeX, Experimentcode, Diagramme.

<details>
<summary>馃摑 Minimale erforderliche Konfiguration</summary>

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

## 馃 Was macht es anders

| Faehigkeit | Funktionsweise |
|-----------|---------------|
| **馃攧 PIVOT / REFINE Schleife** | Stufe 15 entscheidet autonom: PROCEED, REFINE (Parameter anpassen) oder PIVOT (neue Richtung). Artefakte automatisch versioniert. |
| **馃 Multi-Agenten-Debatte** | Hypothesengenerierung, Ergebnisanalyse und Peer-Review verwenden jeweils strukturierte Multi-Perspektiven-Debatten. |
| **馃К Selbstlernen** | Erkenntnisse pro Durchlauf extrahiert (Entscheidungsbegruendungen, Laufzeitwarnungen, Metrikanaomalien) mit 30-Tage-Zeitabklingung. Zukuenftige Durchlaeufe lernen aus vergangenen Fehlern. |
| **馃摎 Wissensdatenbank** | Jeder Durchlauf baut eine strukturierte KB ueber 6 Kategorien auf (Entscheidungen, Experimente, Ergebnisse, Literatur, Fragen, Reviews). |
| **馃洝锔?Sentinel Watchdog** | Hintergrund-Qualitaetsmonitor: NaN/Inf-Erkennung, Paper-Evidenz-Konsistenz, Zitationsrelevanz-Bewertung, Anti-Fabrikationsschutz. |

---

## 馃 OpenClaw-Integration

<table>
<tr>

**AutoResearchClaw ist ein [OpenClaw](https://github.com/openclaw/openclaw)-kompatibler Dienst.** Installiere es in OpenClaw und starte autonome Forschung mit einer einzigen Nachricht 鈥?oder verwende es eigenstaendig ueber CLI, Claude Code oder jeden anderen KI-Coding-Assistenten.

</tr>
</table>

### 馃殌 Verwendung mit OpenClaw (empfohlen)

Wenn du bereits [OpenClaw](https://github.com/openclaw/openclaw) als KI-Assistenten nutzt:

```
1锔忊儯  Teile die GitHub-Repo-URL mit OpenClaw
2锔忊儯  OpenClaw liest automatisch RESEARCHCLAW_AGENTS.md 鈫?versteht die Pipeline
3锔忊儯  Sage: "Research [dein Thema]"
4锔忊儯  Fertig 鈥?OpenClaw klont, installiert, konfiguriert, fuehrt aus und liefert Ergebnisse
```

**Das war's.** OpenClaw uebernimmt `git clone`, `pip install`, Konfiguration und Pipeline-Ausfuehrung automatisch. Du chattest einfach.

<details>
<summary>馃挕 Was unter der Haube passiert</summary>

1. OpenClaw liest `RESEARCHCLAW_AGENTS.md` 鈫?lernt die Forschungs-Orchestrator-Rolle
2. OpenClaw liest `README.md` 鈫?versteht Installation und Pipeline-Struktur
3. OpenClaw kopiert `config.researchclaw.example.yaml` 鈫?`config.yaml`
4. Fragt nach deinem LLM-API-Schluessel (oder verwendet deine Umgebungsvariable)
5. Fuehrt `pip install -e .` + `researchclaw run --topic "..." --auto-approve` aus
6. Liefert Paper, LaTeX, Experimente und Zitationen zurueck

</details>

### 馃攲 OpenClaw Bridge (Fortgeschritten)

Fuer tiefere Integration enthaelt AutoResearchClaw ein **Bridge-Adapter-System** mit 6 optionalen Faehigkeiten:

```yaml
# config.arc.yaml
openclaw_bridge:
  use_cron: true              # 鈴?Geplante Forschungsdurchlaeufe
  use_message: true           # 馃挰 Fortschrittsbenachrichtigungen (Discord/Slack/Telegram)
  use_memory: true            # 馃 Sitzungsuebergreifende Wissenspersistenz
  use_sessions_spawn: true    # 馃攢 Parallele Sub-Sessions fuer gleichzeitige Stufen
  use_web_fetch: true         # 馃寪 Live-Websuche waehrend der Literaturrecherche
  use_browser: false          # 馃枼锔?Browserbasierte Paper-Sammlung
```

Jedes Flag aktiviert ein typisiertes Adapter-Protokoll. Wenn OpenClaw diese Faehigkeiten bereitstellt, nutzen die Adapter sie ohne Codeaenderungen. Siehe [`integration-guide.md`](integration-guide.md) fuer vollstaendige Details.

### ACP (Agent Client Protocol)

AutoResearchClaw kann **jeden ACP-kompatiblen Coding-Agenten** als LLM-Backend verwenden 鈥?keine API-Schluessel erforderlich. Der Agent kommuniziert ueber [acpx](https://github.com/openclaw/acpx) und haelt eine einzige persistente Sitzung ueber alle 23 Pipeline-Stufen aufrecht.

| Agent | Befehl | Hinweise |
|-------|--------|----------|
| Claude Code | `claude` | Anthropic |
| Codex CLI | `codex` | OpenAI |
| Copilot CLI | `gh` | GitHub |
| Gemini CLI | `gemini` | Google |
| OpenCode | `opencode` | SST |
| Kimi CLI | `kimi` | Moonshot |

```yaml
# config.yaml 鈥?ACP-Beispiel
llm:
  provider: "acp"
  acp:
    agent: "claude"   # Jeder ACP-kompatible Agent-CLI-Befehl
    cwd: "."          # Arbeitsverzeichnis fuer den Agenten
  # Kein base_url oder api_key noetig 鈥?der Agent verwaltet seine eigene Authentifizierung.
```

```bash
# Einfach ausfuehren 鈥?der Agent verwendet seine eigenen Anmeldedaten
researchclaw run --config config.yaml --topic "Your research idea" --auto-approve
```

### 馃洜锔?Weitere Ausfuehrungsmoeglichkeiten

| Methode | Anleitung |
|---------|-----------|
| **Standalone CLI** | `researchclaw setup` 鈫?`researchclaw init` 鈫?`researchclaw run --topic "..." --auto-approve` |
| **Python API** | `from researchclaw.pipeline import Runner; Runner(config).run()` |
| **Claude Code** | Liest `RESEARCHCLAW_CLAUDE.md` 鈥?sage einfach *"Run research on [Thema]"* |
| **Copilot CLI** | `researchclaw run --topic "..."` mit `llm.acp.agent: "gh"` |
| **OpenCode** | Liest `.claude/skills/` 鈥?gleiche natuerliche Sprachschnittstelle |
| **Jeder KI-CLI** | Uebergib `RESEARCHCLAW_AGENTS.md` als Kontext 鈫?Agent bootstrappt automatisch |

---

## 馃敩 Pipeline: 23 Stufen, 8 Phasen

```
Phase A: Forschungsplanung            Phase E: Experimentausfuehrung
  1. TOPIC_INIT                          12. EXPERIMENT_RUN
  2. PROBLEM_DECOMPOSE                   13. ITERATIVE_REFINE  鈫?Selbstheilung

Phase B: Literaturrecherche            Phase F: Analyse & Entscheidung
  3. SEARCH_STRATEGY                     14. RESULT_ANALYSIS    鈫?Multi-Agent
  4. LITERATURE_COLLECT  鈫?echte API     15. RESEARCH_DECISION  鈫?PIVOT/REFINE
  5. LITERATURE_SCREEN   [Gate]
  6. KNOWLEDGE_EXTRACT                   Phase G: Papiererstellung
                                         16. PAPER_OUTLINE
Phase C: Wissenssynthese                 17. PAPER_DRAFT
  7. SYNTHESIS                           18. PEER_REVIEW        鈫?Evidenzpruefung
  8. HYPOTHESIS_GEN    鈫?Debatte         19. PAPER_REVISION

Phase D: Experimentdesign             Phase H: Finalisierung
  9. EXPERIMENT_DESIGN   [Gate]          20. QUALITY_GATE      [Gate]
 10. CODE_GENERATION                     21. KNOWLEDGE_ARCHIVE
 11. RESOURCE_PLANNING                   22. EXPORT_PUBLISH     鈫?LaTeX
                                         23. CITATION_VERIFY    鈫?Relevanzpruefung
```

> **Gate-Stufen** (5, 9, 20) pausieren fuer menschliche Genehmigung oder werden mit `--auto-approve` automatisch genehmigt. Bei Ablehnung wird die Pipeline zurueckgesetzt.

> **Entscheidungsschleifen**: Stufe 15 kann REFINE (鈫?Stufe 13) oder PIVOT (鈫?Stufe 8) ausloesen, mit automatischer Artefakt-Versionierung.

<details>
<summary>馃搵 Was jede Phase bewirkt</summary>

| Phase | Beschreibung |
|-------|-------------|
| **A: Planung** | LLM zerlegt das Thema in einen strukturierten Problembaum mit Forschungsfragen |
| **A+: Hardware** | Automatische GPU-Erkennung (NVIDIA CUDA / Apple MPS / nur CPU), Warnung bei eingeschraenkter Hardware, Codegenerierung wird entsprechend angepasst |
| **B: Literatur** | Multi-Source-Suche (OpenAlex 鈫?Semantic Scholar 鈫?arXiv) nach echten Papern, Relevanzscreening, Extraktion von Wissenskarten |
| **C: Synthese** | Clustering der Ergebnisse, Identifizierung von Forschungsluecken, Generierung testbarer Hypothesen via Multi-Agenten-Debatte |
| **D: Design** | Experimentplan entwerfen, hardwarebewussten ausfuehrbaren Python-Code generieren (GPU-Stufe 鈫?Paketauswahl), Ressourcenbedarf schaetzen |
| **E: Ausfuehrung** | Experimente in Sandbox ausfuehren, NaN/Inf und Laufzeitfehler erkennen, Code via gezielter LLM-Reparatur selbst heilen |
| **F: Analyse** | Multi-Agenten-Analyse der Ergebnisse; autonome PROCEED / REFINE / PIVOT Entscheidung mit Begruendung |
| **G: Schreiben** | Gliederung 鈫?abschnittsweises Verfassen (5.000-6.500 Woerter) 鈫?Peer-Review (mit Methodik-Evidenz-Konsistenz) 鈫?Revision mit Laengenpruefung |
| **H: Finalisierung** | Qualitaets-Gate, Wissensarchivierung, LaTeX-Export mit Konferenztemplate, Zitationsintegritaets- und Relevanzpruefung |

</details>

---

## 鉁?Hauptfunktionen

| Funktion | Beschreibung |
|----------|-------------|
| **馃摎 Multi-Source-Literatur** | Echte Paper von OpenAlex, Semantic Scholar und arXiv 鈥?Abfrageerweiterung, Deduplizierung, Circuit Breaker mit Graceful Degradation |
| **馃攳 4-Schicht-Zitationsverifikation** | arXiv-ID-Pruefung 鈫?CrossRef/DataCite-DOI 鈫?Semantic-Scholar-Titelabgleich 鈫?LLM-Relevanzbewertung. Halluzinierte Refs automatisch entfernt. |
| **馃枼锔?Hardwarebewusste Ausfuehrung** | Automatische GPU-Erkennung (NVIDIA CUDA / Apple MPS / nur CPU) und Anpassung von Codegenerierung, Imports und Experimentumfang |
| **馃 OpenCode Beast Mode** | Komplexe Experimente werden automatisch an [OpenCode](https://github.com/anomalyco/opencode) weitergeleitet 鈥?generiert Multi-File-Projekte mit individuellen Architekturen, Trainingsschleifen und Ablationsstudien. Installation ueber `researchclaw setup`. |
| **馃И Sandbox-Experimente** | AST-validierter Code, unveraenderlicher Harness, NaN/Inf-Schnellabbruch, selbstheilende Reparatur, iterative Verfeinerung (bis zu 10 Runden), Teilergebnis-Erfassung |
| **馃摑 Konferenzqualitaet** | NeurIPS/ICML/ICLR-Templates, abschnittsweises Verfassen (5.000-6.500 Woerter), Anti-Fabrikationsschutz, Revisions-Laengenschutz, Anti-Disclaimer-Durchsetzung |
| **馃搻 Template-Umschaltung** | `neurips_2025`, `iclr_2026`, `icml_2026` 鈥?Markdown 鈫?LaTeX mit Mathematik, Tabellen, Abbildungen, Querverweisen, `\cite{}` |
| **馃殾 Qualitaets-Gates** | 3 Human-in-the-Loop-Gates (Stufen 5, 9, 20) mit Rollback. Ueberspringen mit `--auto-approve`. |

---

## 馃 MetaClaw-Integration

**AutoResearchClaw + [MetaClaw](https://github.com/aiming-lab/MetaClaw) = Eine Pipeline, die aus jedem Durchlauf lernt.**

MetaClaw fuegt **durchlaufuebergreifenden Wissenstransfer** zu AutoResearchClaw hinzu. Wenn aktiviert, erfasst die Pipeline automatisch Erkenntnisse aus Fehlern und Warnungen, konvertiert sie in wiederverwendbare Skills und injiziert diese Skills in alle 23 Pipeline-Stufen bei nachfolgenden Durchlaeufen 鈥?damit dieselben Fehler nie wiederholt werden.

### Funktionsweise

```
Durchlauf N wird ausgefuehrt 鈫?Fehler/Warnungen als Lektionen erfasst
                      鈫?
          MetaClaw Lektion 鈫?Skill-Konvertierung
                      鈫?
          arc-* Skill-Dateien in ~/.metaclaw/skills/ gespeichert
                      鈫?
Durchlauf N+1 鈫?build_overlay() injiziert Skills in jeden LLM-Prompt
                      鈫?
          LLM vermeidet bekannte Fallstricke 鈫?hoehere Qualitaet, weniger Wiederholungen
```

### Schnelleinrichtung

```bash
# 1. MetaClaw installieren (falls nicht vorhanden)
pip install metaclaw

# 2. In der Konfiguration aktivieren
```

```yaml
# config.arc.yaml
metaclaw_bridge:
  enabled: true
  proxy_url: "http://localhost:30000"        # MetaClaw-Proxy (optional)
  skills_dir: "~/.metaclaw/skills"          # Wo Skills gespeichert werden
  fallback_url: "https://api.openai.com/v1" # Direkter LLM-Fallback
  fallback_api_key: ""                      # API-Schluessel fuer Fallback-URL
  lesson_to_skill:
    enabled: true
    min_severity: "warning"                 # Warnungen + Fehler konvertieren
    max_skills_per_run: 3
```

```bash
# 3. Wie gewohnt ausfuehren 鈥?MetaClaw arbeitet transparent
researchclaw run --config config.arc.yaml --topic "Your idea" --auto-approve
```

Nach jedem Durchlauf kannst du `~/.metaclaw/skills/arc-*/SKILL.md` pruefen, um die erlernten Skills deiner Pipeline zu sehen.

### Experimentergebnisse

In kontrollierten A/B-Experimenten (gleiches Thema, gleiches LLM, gleiche Konfiguration):

| Metrik | Baseline | Mit MetaClaw | Verbesserung |
|--------|----------|--------------|--------------|
| Stufen-Wiederholungsrate | 10.5% | 7.9% | **-24.8%** |
| Anzahl REFINE-Zyklen | 2.0 | 1.2 | **-40.0%** |
| Pipeline-Stufenabschluss | 18/19 | 19/19 | **+5.3%** |
| Gesamtrobustheitswert (Komposit) | 0.714 | 0.845 | **+18.3%** |

> Der Komposit-Robustheitswert ist ein gewichteter Durchschnitt aus Stufenabschlussrate (40%), Wiederholungsreduktion (30%) und REFINE-Zykluseffizienz (30%).

### Abwaertskompatibilitaet

- **Standard: AUS.** Wenn `metaclaw_bridge` fehlt oder `enabled: false`, verhaelt sich die Pipeline exakt wie zuvor.
- **Keine neuen Abhaengigkeiten.** MetaClaw ist optional 鈥?die Kern-Pipeline funktioniert ohne.
- **Alle 1.823 bestehenden Tests bestehen** mit dem Integrationscode.

---

## 鈿欙笍 Konfigurationsreferenz

<details>
<summary>Klicken zum Aufklappen der vollstaendigen Konfigurationsreferenz</summary>

```yaml
# === Projekt ===
project:
  name: "my-research"              # Projektbezeichner
  mode: "docs-first"               # docs-first | semi-auto | full-auto

# === Forschung ===
research:
  topic: "..."                     # Forschungsthema (erforderlich)
  domains: ["ml", "nlp"]           # Forschungsdomaenen fuer Literatursuche
  daily_paper_count: 8             # Ziel-Paperzahl pro Suchabfrage
  quality_threshold: 4.0           # Mindestqualitaetswert fuer Paper

# === Laufzeit ===
runtime:
  timezone: "America/New_York"     # Fuer Zeitstempel
  max_parallel_tasks: 3            # Limit gleichzeitiger Experimente
  approval_timeout_hours: 12       # Gate-Stufen-Timeout
  retry_limit: 2                   # Wiederholungsanzahl bei Stufenfehler

# === LLM ===
llm:
  provider: "openai-compatible"    # openai | openrouter | deepseek | minimax | acp | openai-compatible
  base_url: "https://..."          # API-Endpunkt (erforderlich fuer openai-compatible)
  api_key_env: "OPENAI_API_KEY"    # Umgebungsvariable fuer API-Schluessel (erforderlich fuer openai-compatible)
  api_key: ""                      # Oder Schluessel direkt eintragen
  primary_model: "gpt-4o"          # Primaeres Modell
  fallback_models: ["gpt-4o-mini"] # Fallback-Kette
  s2_api_key: ""                   # Semantic Scholar API-Schluessel (optional, hoehere Rate-Limits)
  acp:                             # Nur verwendet wenn provider: "acp"
    agent: "claude"                # ACP-Agent-CLI-Befehl (claude, codex, gemini, etc.)
    cwd: "."                       # Arbeitsverzeichnis fuer den Agenten

# === Experiment ===
experiment:
  mode: "sandbox"                  # simulated | sandbox | docker | ssh_remote
  time_budget_sec: 300             # Max. Ausfuehrungszeit pro Durchlauf (Standard: 300s)
  max_iterations: 10               # Max. Optimierungsiterationen
  metric_key: "val_loss"           # Primaerer Metrikname
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
    auto_install_deps: true        # Automatische Import-Erkennung 鈫?requirements.txt
  ssh_remote:
    host: ""                       # GPU-Server-Hostname
    gpu_ids: []                    # Verfuegbare GPU-IDs
    remote_workdir: "/tmp/researchclaw_experiments"
  opencode:                          # OpenCode Beast Mode (auto-installiert ueber `researchclaw setup`)
    enabled: true                    # Hauptschalter (Standard: true)
    auto: true                       # Auto-Ausloesung ohne Bestaetigung (Standard: true)
    complexity_threshold: 0.2        # 0.0-1.0 鈥?hoeher = nur bei komplexen Experimenten ausloesen
    model: ""                        # Modell ueberschreiben (leer = llm.primary_model verwenden)
    timeout_sec: 600                 # Max. Sekunden fuer OpenCode-Generierung
    max_retries: 1                   # Wiederholungsanzahl bei Fehler
    workspace_cleanup: true          # Temporaeren Workspace nach Sammlung entfernen

# === Export ===
export:
  target_conference: "neurips_2025"  # neurips_2025 | iclr_2026 | icml_2026
  authors: "Anonymous"
  bib_file: "references"

# === Prompts ===
prompts:
  custom_file: ""                  # Pfad zur benutzerdefinierten Prompts-YAML (leer = Standardwerte)

# === Sicherheit ===
security:
  hitl_required_stages: [5, 9, 20] # Stufen, die menschliche Genehmigung erfordern
  allow_publish_without_approval: false
  redact_sensitive_logs: true

# === Wissensdatenbank ===
knowledge_base:
  backend: "markdown"              # markdown | obsidian
  root: "docs/kb"

# === Benachrichtigungen ===
notifications:
  channel: "console"               # console | discord | slack
  target: ""

# === MetaClaw Bridge (Optional) ===
metaclaw_bridge:
  enabled: false                   # Auf true setzen fuer durchlaufuebergreifendes Lernen
  proxy_url: "http://localhost:30000"  # MetaClaw-Proxy-URL
  skills_dir: "~/.metaclaw/skills" # Wo arc-* Skills gespeichert werden
  fallback_url: ""                 # Direkter LLM-Fallback wenn Proxy nicht erreichbar
  fallback_api_key: ""             # API-Schluessel fuer Fallback-Endpunkt
  lesson_to_skill:
    enabled: true                  # Lektionen automatisch in Skills konvertieren
    min_severity: "warning"        # Mindestschwere fuer Konvertierung
    max_skills_per_run: 3          # Max. neue Skills pro Pipeline-Durchlauf

# === OpenClaw Bridge ===
openclaw_bridge:
  use_cron: false                  # Geplante Forschungsdurchlaeufe
  use_message: false               # Fortschrittsbenachrichtigungen
  use_memory: false                # Sitzungsuebergreifende Wissenspersistenz
  use_sessions_spawn: false        # Parallele Sub-Sessions starten
  use_web_fetch: false             # Live-Websuche
  use_browser: false               # Browserbasierte Paper-Sammlung
```

</details>

---

## 馃檹 Danksagungen

Inspiriert von:

- 馃敩 [AI Scientist](https://github.com/SakanaAI/AI-Scientist) (Sakana AI) 鈥?Pionier der automatisierten Forschung
- 馃 [AutoResearch](https://github.com/karpathy/autoresearch) (Andrej Karpathy) 鈥?End-to-End-Forschungsautomatisierung
- 馃寪 [FARS](https://analemma.ai/blog/introducing-fars/) (Analemma) 鈥?Fully Automated Research System

---

## 馃搫 Lizenz

MIT 鈥?siehe [LICENSE](../LICENSE) fuer Details.

---

## 馃搶 Zitation

Wenn du AutoResearchClaw nuetzlich findest, zitiere bitte:

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
  <sub>Gebaut mit 馃 vom AutoResearchClaw-Team</sub>
</p>
