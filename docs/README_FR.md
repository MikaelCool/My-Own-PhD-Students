<p align="center">
  <img src="../image/logo.png" width="700" alt="AutoResearchClaw Logo">
</p>

<h2 align="center"><b>Discutez une idee. Obtenez un article. Entierement autonome & auto-evolutif.</b></h2>



<p align="center">
  <b><i><font size="5">Discutez avec <a href="#-integration-openclaw">OpenClaw</a> : "Recherche X" 鈫?termine.</font></i></b>
</p>

<p align="center">
  <img src="../image/framework_v2.png" width="100%" alt="AutoResearchClaw Framework">
</p>


<p align="center">
  <a href="../LICENSE"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="MIT License"></a>
  <a href="https://python.org"><img src="https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white" alt="Python 3.11+"></a>
  <a href="#testing"><img src="https://img.shields.io/badge/Tests-1823%20passed-brightgreen?logo=pytest&logoColor=white" alt="1823 Tests Passed"></a>
  <a href="https://github.com/MikaelCool/My-Own-PhD-Students"><img src="https://img.shields.io/badge/GitHub-My_Own_PhD_Students-181717?logo=github" alt="GitHub"></a>
  <a href="#-integration-openclaw"><img src="https://img.shields.io/badge/OpenClaw-Compatible-ff4444?logo=data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCI+PHBhdGggZD0iTTEyIDJDNi40OCAyIDIgNi40OCAyIDEyczQuNDggMTAgMTAgMTAgMTAtNC40OCAxMC0xMFMxNy41MiAyIDEyIDJ6IiBmaWxsPSJ3aGl0ZSIvPjwvc3ZnPg==" alt="OpenClaw Compatible"></a>
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
  <a href="showcase/SHOWCASE.md">馃弳 Vitrine des articles</a> 路 <a href="integration-guide.md">馃摉 Guide d'integration</a> 路 <a href="https://discord.gg/u4ksqW5P">馃挰 Communaute Discord</a>
</p>

---

<table>
<tr>
<td width="18%">
<a href="showcase/SHOWCASE.md"><img src="showcase/thumbnails/paper_I_random_matrix-01.png" width="120" alt="Sample Paper"/></a>
</td>
<td valign="middle">
<b>馃弳 Vitrine des articles generes</b><br><br>
<b>8 articles couvrant 8 domaines</b> 鈥?mathematiques, statistiques, biologie, informatique, NLP, RL, vision, robustesse 鈥?generes de maniere entierement autonome sans aucune intervention humaine.<br><br>
<a href="showcase/SHOWCASE.md"><img src="https://img.shields.io/badge/View_Full_Showcase_鈫?All_8_Papers-d73a49?style=for-the-badge" alt="View Showcase"></a>
</td>
</tr>
</table>

---

> **馃И Nous recherchons des testeurs !** Essayez le pipeline avec votre propre idee de recherche 鈥?dans n'importe quel domaine 鈥?et [dites-nous ce que vous en pensez](TESTER_GUIDE.md). Vos retours faconnent directement la prochaine version. **[鈫?Testing Guide](TESTER_GUIDE.md)** | **[鈫?涓枃娴嬭瘯鎸囧崡](TESTER_GUIDE_CN.md)** | **[鈫?鏃ユ湰瑾炪儐銈广儓銈偆銉塢(TESTER_GUIDE_JA.md)**

---

## 馃敟 News
- **[03/22/2026]** [v0.3.2](https://github.com/MikaelCool/My-Own-PhD-Students/releases/tag/v0.3.2) 鈥?**Support multiplateforme + stabilite majeure** 鈥?AutoResearchClaw fonctionne desormais avec tout agent compatible ACP (Claude Code, Codex CLI, Copilot CLI, Gemini CLI, Kimi CLI) et supporte les plateformes de messagerie (Discord, Telegram, Lark, WeChat) via le pont OpenClaw. Nouveau backend de generation de code CLI-agent qui delegue les Stages 10 et 13 a des agents CLI externes avec controle de budget et gestion des timeouts. Inclut le systeme anti-fabrication (VerifiedRegistry + boucle diagnostic/reparation), 100+ corrections de bugs, refactoring modulaire de l'executor, auto-detection `--resume`, renforcement des retries LLM, et corrections communautaires.
- **[03/18/2026]** [v0.3.1](https://github.com/MikaelCool/My-Own-PhD-Students/releases/tag/v0.3.1) 鈥?**OpenCode Beast Mode + Community Contributions** 鈥?New "Beast Mode" routes complex code generation to [OpenCode](https://github.com/anomalyco/opencode) with automatic complexity scoring and graceful fallback. Added Novita AI provider support, thread-safety hardening, improved LLM output parsing robustness, and 20+ bug fixes from community PRs and internal audit.
- **[03/17/2026]** [v0.3.0](https://github.com/MikaelCool/My-Own-PhD-Students/releases/tag/v0.3.0) 鈥?**MetaClaw Integration** 鈥?AutoResearchClaw now supports [MetaClaw](https://github.com/aiming-lab/MetaClaw) cross-run learning: pipeline failures 鈫?structured lessons 鈫?reusable skills, injected into all 23 stages. **+18.3%** robustness in controlled experiments. Opt-in (`metaclaw_bridge.enabled: true`), fully backward-compatible. See [Integration Guide](#-integration-metaclaw).
- **[03/16/2026]** [v0.2.0](https://github.com/MikaelCool/My-Own-PhD-Students/releases/tag/v0.2.0) 鈥?Three multi-agent subsystems (CodeAgent, BenchmarkAgent, FigureAgent), hardened Docker sandbox with network-policy-aware execution, 4-round paper quality audit (AI-slop detection, 7-dim review scoring, NeurIPS checklist), and 15+ bug fixes from production runs.
- **[03/15/2026]** [v0.1.0](https://github.com/MikaelCool/My-Own-PhD-Students/releases/tag/v0.1.0) 鈥?We release AutoResearchClaw: a fully autonomous 23-stage research pipeline that turns a single research idea into a conference-ready paper. No human intervention required.

---

## 鈿?Une commande. Un article.

```bash
pip install -e . && researchclaw setup && researchclaw init && researchclaw run --topic "Your research idea here" --auto-approve
```


---

## 馃 De quoi s'agit-il ?

**Vous y pensez. AutoResearchClaw l'ecrit.**

Donnez un sujet de recherche 鈥?recevez un article academique complet avec de la vraie litterature provenant d'OpenAlex, Semantic Scholar et arXiv, des experiences en sandbox adaptees au materiel (detection automatique GPU/MPS/CPU), une analyse statistique, une relecture multi-agents, et du LaTeX pret pour les conferences ciblant NeurIPS/ICML/ICLR. Aucune supervision. Aucun copier-coller. Aucune reference hallucinee.

<table>
<tr><td>馃搫</td><td><code>paper_draft.md</code></td><td>Article academique complet (Introduction, Travaux connexes, Methode, Experiences, Resultats, Conclusion)</td></tr>
<tr><td>馃搻</td><td><code>paper.tex</code></td><td>LaTeX pret pour les conferences (templates NeurIPS / ICLR / ICML)</td></tr>
<tr><td>馃摎</td><td><code>references.bib</code></td><td>References BibTeX reelles provenant d'OpenAlex, Semantic Scholar et arXiv 鈥?auto-elaguees pour correspondre aux citations dans le texte</td></tr>
<tr><td>馃攳</td><td><code>verification_report.json</code></td><td>Verification d'integrite et de pertinence des citations sur 4 couches (arXiv, CrossRef, DataCite, LLM)</td></tr>
<tr><td>馃И</td><td><code>experiment runs/</code></td><td>Code genere + resultats sandbox + metriques JSON structurees</td></tr>
<tr><td>馃搳</td><td><code>charts/</code></td><td>Graphiques de comparaison de conditions auto-generes avec barres d'erreur et intervalles de confiance</td></tr>
<tr><td>馃摑</td><td><code>reviews.md</code></td><td>Relecture multi-agents avec verification de coherence methodologie-preuves</td></tr>
<tr><td>馃К</td><td><code>evolution/</code></td><td>Lecons d'auto-apprentissage extraites de chaque execution</td></tr>
<tr><td>馃摝</td><td><code>deliverables/</code></td><td>Tous les livrables finaux dans un seul dossier 鈥?pret a compiler pour Overleaf</td></tr>
</table>

Le pipeline s'execute **de bout en bout sans intervention humaine**. Quand les experiences echouent, il s'auto-repare. Quand les hypotheses ne tiennent pas, il pivote. Quand les citations sont fausses, il les supprime.

馃實 **Utilisable partout.** AutoResearchClaw n'est pas verrouille sur une seule plateforme. Utilisez-le en CLI autonome, connectez-le a [OpenClaw](https://github.com/openclaw/openclaw), ou integrez-le avec n'importe quel agent compatible ACP 鈥?馃 Claude Code, 馃捇 Codex CLI, 馃悪 Copilot CLI, 鈾?Gemini CLI, 馃寵 Kimi CLI, et bien d'autres. Grace au pont de messagerie d'OpenClaw, vous pouvez lancer une recherche complete depuis 馃挰 Discord, 鉁堬笍 Telegram, 馃惁 Lark (椋炰功), 馃挌 WeChat, ou la plateforme que votre equipe utilise deja. Un sujet en entree, un article en sortie 鈥?peu importe d'ou vous l'envoyez.

---

## 馃殌 Demarrage rapide

```bash
# 1. Cloner & installer
git clone https://github.com/MikaelCool/My-Own-PhD-Students.git
cd My-Own-PhD-Students
python3 -m venv .venv && source .venv/bin/activate
pip install -e .

# 2. Setup (interactif 鈥?installe OpenCode beast mode, verifie Docker/LaTeX)
researchclaw setup

# 3. Configurer
researchclaw init          # Interactif : choisir le fournisseur LLM, cree config.arc.yaml
# Ou manuellement : cp config.researchclaw.example.yaml config.arc.yaml

# 4. Executer
export OPENAI_API_KEY="sk-..."
researchclaw run --config config.arc.yaml --topic "Your research idea" --auto-approve
```

Sortie 鈫?`artifacts/rc-YYYYMMDD-HHMMSS-<hash>/deliverables/` 鈥?LaTeX pret a compiler, BibTeX, code d'experience, graphiques.

<details>
<summary>馃摑 Configuration minimale requise</summary>

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

## 馃 Ce qui le distingue

| Capacite | Fonctionnement |
|----------|---------------|
| **馃攧 Boucle PIVOT / REFINE** | L'etape 15 decide de maniere autonome : PROCEED, REFINE (ajuster les parametres) ou PIVOT (nouvelle direction). Artefacts auto-versionnes. |
| **馃 Debat multi-agents** | La generation d'hypotheses, l'analyse de resultats et la relecture par les pairs utilisent chacune un debat structure multi-perspectives. |
| **馃К Auto-apprentissage** | Lecons extraites a chaque execution (justification des decisions, avertissements d'execution, anomalies de metriques) avec decroissance temporelle a 30 jours. Les executions futures apprennent des erreurs passees. |
| **馃摎 Base de connaissances** | Chaque execution construit une KB structuree couvrant 6 categories (decisions, experiences, resultats, litterature, questions, relectures). |
| **馃洝锔?Sentinel Watchdog** | Moniteur de qualite en arriere-plan : detection NaN/Inf, coherence article-preuves, score de pertinence des citations, protection anti-fabrication. |

---

## 馃 Integration OpenClaw

<table>
<tr>

**AutoResearchClaw est un service compatible [OpenClaw](https://github.com/openclaw/openclaw).** Installez-le dans OpenClaw et lancez une recherche autonome avec un seul message 鈥?ou utilisez-le de maniere autonome via CLI, Claude Code, ou tout assistant de codage IA.

</tr>
</table>

### 馃殌 Utilisation avec OpenClaw (recommande)

Si vous utilisez deja [OpenClaw](https://github.com/openclaw/openclaw) comme assistant IA :

```
1锔忊儯  Partagez l'URL du depot GitHub avec OpenClaw
2锔忊儯  OpenClaw lit automatiquement RESEARCHCLAW_AGENTS.md 鈫?comprend le pipeline
3锔忊儯  Dites : "Research [votre sujet]"
4锔忊儯  C'est fait 鈥?OpenClaw clone, installe, configure, execute et renvoie les resultats
```

**C'est tout.** OpenClaw gere `git clone`, `pip install`, la configuration et l'execution du pipeline automatiquement. Vous n'avez qu'a discuter.

<details>
<summary>馃挕 Ce qui se passe en coulisses</summary>

1. OpenClaw lit `RESEARCHCLAW_AGENTS.md` 鈫?apprend le role d'orchestrateur de recherche
2. OpenClaw lit `README.md` 鈫?comprend l'installation et la structure du pipeline
3. OpenClaw copie `config.researchclaw.example.yaml` 鈫?`config.yaml`
4. Demande votre cle API LLM (ou utilise votre variable d'environnement)
5. Execute `pip install -e .` + `researchclaw run --topic "..." --auto-approve`
6. Renvoie l'article, le LaTeX, les experiences et les citations

</details>

### 馃攲 Pont OpenClaw (avance)

Pour une integration plus poussee, AutoResearchClaw inclut un **systeme d'adaptateurs pont** avec 6 fonctionnalites optionnelles :

```yaml
# config.arc.yaml
openclaw_bridge:
  use_cron: true              # 鈴?Executions de recherche planifiees
  use_message: true           # 馃挰 Notifications de progression (Discord/Slack/Telegram)
  use_memory: true            # 馃 Persistance des connaissances inter-sessions
  use_sessions_spawn: true    # 馃攢 Lancement de sous-sessions paralleles pour les etapes concurrentes
  use_web_fetch: true         # 馃寪 Recherche web en direct pendant la revue de litterature
  use_browser: false          # 馃枼锔?Collecte d'articles via navigateur
```

Chaque option active un protocole d'adaptateur type. Quand OpenClaw fournit ces fonctionnalites, les adaptateurs les consomment sans modification de code. Voir [`integration-guide.md`](integration-guide.md) pour tous les details.

### ACP (Agent Client Protocol)

AutoResearchClaw peut utiliser **n'importe quel agent de codage compatible ACP** comme backend LLM 鈥?sans cle API requise. L'agent communique via [acpx](https://github.com/openclaw/acpx), en maintenant une session persistante unique a travers les 23 etapes du pipeline.

| Agent | Commande | Notes |
|-------|----------|-------|
| Claude Code | `claude` | Anthropic |
| Codex CLI | `codex` | OpenAI |
| Copilot CLI | `gh` | GitHub |
| Gemini CLI | `gemini` | Google |
| OpenCode | `opencode` | SST |
| Kimi CLI | `kimi` | Moonshot |

```yaml
# config.yaml 鈥?exemple ACP
llm:
  provider: "acp"
  acp:
    agent: "claude"   # N'importe quel agent CLI compatible ACP
    cwd: "."          # Repertoire de travail pour l'agent
  # Pas besoin de base_url ou api_key 鈥?l'agent gere sa propre authentification.
```

```bash
# Executez simplement 鈥?l'agent utilise ses propres identifiants
researchclaw run --config config.yaml --topic "Your research idea" --auto-approve
```

### 馃洜锔?Autres methodes d'execution

| Methode | Comment |
|---------|---------|
| **CLI autonome** | `researchclaw setup` 鈫?`researchclaw init` 鈫?`researchclaw run --topic "..." --auto-approve` |
| **API Python** | `from researchclaw.pipeline import Runner; Runner(config).run()` |
| **Claude Code** | Lit `RESEARCHCLAW_CLAUDE.md` 鈥?dites simplement *"Run research on [sujet]"* |
| **Copilot CLI** | `researchclaw run --topic "..."` avec `llm.acp.agent: "gh"` |
| **OpenCode** | Lit `.claude/skills/` 鈥?meme interface en langage naturel |
| **Tout CLI IA** | Fournissez `RESEARCHCLAW_AGENTS.md` comme contexte 鈫?l'agent s'auto-initialise |

---

## 馃敩 Pipeline : 23 etapes, 8 phases

```
Phase A : Cadrage de la recherche     Phase E : Execution des experiences
  1. TOPIC_INIT                         12. EXPERIMENT_RUN
  2. PROBLEM_DECOMPOSE                  13. ITERATIVE_REFINE  鈫?auto-reparation

Phase B : Decouverte de litterature   Phase F : Analyse et decision
  3. SEARCH_STRATEGY                    14. RESULT_ANALYSIS    鈫?multi-agents
  4. LITERATURE_COLLECT  鈫?API reelle   15. RESEARCH_DECISION  鈫?PIVOT/REFINE
  5. LITERATURE_SCREEN   [porte]
  6. KNOWLEDGE_EXTRACT                  Phase G : Redaction de l'article
                                        16. PAPER_OUTLINE
Phase C : Synthese des connaissances    17. PAPER_DRAFT
  7. SYNTHESIS                          18. PEER_REVIEW        鈫?verif. preuves
  8. HYPOTHESIS_GEN    鈫?debat          19. PAPER_REVISION

Phase D : Conception experimentale    Phase H : Finalisation
  9. EXPERIMENT_DESIGN   [porte]        20. QUALITY_GATE      [porte]
 10. CODE_GENERATION                    21. KNOWLEDGE_ARCHIVE
 11. RESOURCE_PLANNING                  22. EXPORT_PUBLISH     鈫?LaTeX
                                        23. CITATION_VERIFY    鈫?verif. pertinence
```

> **Etapes de validation** (5, 9, 20) : pause pour approbation humaine ou approbation automatique avec `--auto-approve`. En cas de rejet, le pipeline revient en arriere.

> **Boucles de decision** : l'etape 15 peut declencher REFINE (鈫?etape 13) ou PIVOT (鈫?etape 8), avec versionnement automatique des artefacts.

<details>
<summary>馃搵 Ce que fait chaque phase</summary>

| Phase | Ce qui se passe |
|-------|-----------------|
| **A : Cadrage** | Le LLM decompose le sujet en un arbre de problemes structure avec des questions de recherche |
| **A+ : Materiel** | Detection automatique du GPU (NVIDIA CUDA / Apple MPS / CPU uniquement), avertissement si le materiel local est limite, adaptation de la generation de code en consequence |
| **B : Litterature** | Recherche multi-sources (OpenAlex 鈫?Semantic Scholar 鈫?arXiv) de vrais articles, filtrage par pertinence, extraction de fiches de connaissances |
| **C : Synthese** | Regroupement des resultats, identification des lacunes de recherche, generation d'hypotheses testables via debat multi-agents |
| **D : Conception** | Conception du plan experimental, generation de Python executable adapte au materiel (niveau GPU 鈫?selection de packages), estimation des besoins en ressources |
| **E : Execution** | Execution des experiences en sandbox, detection de NaN/Inf et bugs d'execution, auto-reparation du code via reparation ciblee par LLM |
| **F : Analyse** | Analyse multi-agents des resultats ; decision autonome PROCEED / REFINE / PIVOT avec justification |
| **G : Redaction** | Plan 鈫?redaction section par section (5 000-6 500 mots) 鈫?relecture (avec verification de coherence methodologie-preuves) 鈫?revision avec controle de longueur |
| **H : Finalisation** | Porte qualite, archivage des connaissances, export LaTeX avec template de conference, verification d'integrite et de pertinence des citations |

</details>

---

## 鉁?Fonctionnalites cles

| Fonctionnalite | Description |
|----------------|------------|
| **馃摎 Litterature multi-sources** | Vrais articles depuis OpenAlex, Semantic Scholar et arXiv 鈥?expansion de requetes, deduplication, disjoncteur avec degradation gracieuse |
| **馃攳 Verification des citations en 4 couches** | Verification arXiv ID 鈫?DOI CrossRef/DataCite 鈫?correspondance de titre Semantic Scholar 鈫?score de pertinence LLM. References hallucin茅es auto-supprimees. |
| **馃枼锔?Execution adaptee au materiel** | Detection automatique du GPU (NVIDIA CUDA / Apple MPS / CPU uniquement) et adaptation de la generation de code, des imports et de l'echelle experimentale |
| **馃 OpenCode Beast Mode** | Les experiences complexes sont automatiquement dirigees vers [OpenCode](https://github.com/anomalyco/opencode) 鈥?genere des projets multi-fichiers avec architectures personnalisees, boucles d'entrainement et etudes d'ablation. Installation via `researchclaw setup`. |
| **馃И Experiences en sandbox** | Code valide par AST, harnais immuable, echec rapide NaN/Inf, reparation auto-guerison, raffinement iteratif (jusqu'a 10 tours), capture de resultats partiels |
| **馃摑 Redaction de qualite conference** | Templates NeurIPS/ICML/ICLR, redaction section par section (5 000-6 500 mots), protection anti-fabrication, controle de longueur en revision, application anti-clause de non-responsabilite |
| **馃搻 Changement de template** | `neurips_2025`, `iclr_2026`, `icml_2026` 鈥?Markdown 鈫?LaTeX avec formules, tableaux, figures, references croisees, `\cite{}` |
| **馃殾 Portes qualite** | 3 portes avec intervention humaine possible (etapes 5, 9, 20) avec retour en arriere. A passer avec `--auto-approve`. |

---

## 馃 Integration MetaClaw

**AutoResearchClaw + [MetaClaw](https://github.com/aiming-lab/MetaClaw) = Un pipeline qui apprend de chaque execution.**

MetaClaw ajoute le **transfert de connaissances inter-executions** a AutoResearchClaw. Lorsqu'il est active, le pipeline capture automatiquement les lecons des echecs et avertissements, les convertit en competences reutilisables, et injecte ces competences dans les 23 etapes du pipeline lors des executions suivantes 鈥?pour ne jamais repeter les memes erreurs.

### Fonctionnement

```
Execution N s'execute 鈫?echecs/avertissements captures comme Lecons
                      鈫?
          MetaClaw Lecon 鈫?conversion en Competence
                      鈫?
          Fichiers de competences arc-* stockes dans ~/.metaclaw/skills/
                      鈫?
Execution N+1 鈫?build_overlay() injecte les competences dans chaque prompt LLM
                      鈫?
          Le LLM evite les pieges connus 鈫?meilleure qualite, moins de tentatives
```

### Configuration rapide

```bash
# 1. Installer MetaClaw (si ce n'est pas deja fait)
pip install metaclaw

# 2. Activer dans votre configuration
```

```yaml
# config.arc.yaml
metaclaw_bridge:
  enabled: true
  proxy_url: "http://localhost:30000"        # Proxy MetaClaw (optionnel)
  skills_dir: "~/.metaclaw/skills"          # Ou les competences sont stockees
  fallback_url: "https://api.openai.com/v1" # Repli direct vers le LLM
  fallback_api_key: ""                      # Cle API pour l'URL de repli
  lesson_to_skill:
    enabled: true
    min_severity: "warning"                 # Convertir avertissements + erreurs
    max_skills_per_run: 3
```

```bash
# 3. Executez comme d'habitude 鈥?MetaClaw fonctionne de maniere transparente
researchclaw run --config config.arc.yaml --topic "Your idea" --auto-approve
```

Apres chaque execution, verifiez `~/.metaclaw/skills/arc-*/SKILL.md` pour voir les competences que votre pipeline a apprises.

### Resultats experimentaux

Dans des experiences controlees A/B (meme sujet, meme LLM, meme configuration) :

| Metrique | Reference | Avec MetaClaw | Amelioration |
|----------|-----------|---------------|--------------|
| Taux de relance des etapes | 10.5% | 7.9% | **-24.8%** |
| Nombre de cycles REFINE | 2.0 | 1.2 | **-40.0%** |
| Completion des etapes du pipeline | 18/19 | 19/19 | **+5.3%** |
| Score de robustesse global (composite) | 0.714 | 0.845 | **+18.3%** |

> Le score de robustesse composite est une moyenne ponderee du taux de completion des etapes (40%), de la reduction des tentatives (30%) et de l'efficacite des cycles REFINE (30%).

### Retrocompatibilite

- **Par defaut : DESACTIVE.** Si `metaclaw_bridge` est absent ou `enabled: false`, le pipeline se comporte exactement comme avant.
- **Aucune nouvelle dependance.** MetaClaw est optionnel 鈥?le pipeline de base fonctionne sans.
- **Les 1 823 tests existants passent** avec le code d'integration present.

---

## 鈿欙笍 Reference de configuration

<details>
<summary>Cliquez pour afficher la reference complete de configuration</summary>

```yaml
# === Projet ===
project:
  name: "my-research"              # Identifiant du projet
  mode: "docs-first"               # docs-first | semi-auto | full-auto

# === Recherche ===
research:
  topic: "..."                     # Sujet de recherche (requis)
  domains: ["ml", "nlp"]           # Domaines de recherche pour la revue de litterature
  daily_paper_count: 8             # Nombre cible d'articles par requete de recherche
  quality_threshold: 4.0           # Score qualite minimum pour les articles

# === Execution ===
runtime:
  timezone: "America/New_York"     # Pour les horodatages
  max_parallel_tasks: 3            # Limite d'experiences concurrentes
  approval_timeout_hours: 12       # Timeout des etapes de validation
  retry_limit: 2                   # Nombre de tentatives en cas d'echec d'etape

# === LLM ===
llm:
  provider: "openai-compatible"    # openai | openrouter | deepseek | minimax | acp | openai-compatible
  base_url: "https://..."          # Point d'acces API (requis pour openai-compatible)
  api_key_env: "OPENAI_API_KEY"    # Variable d'env pour la cle API (requis pour openai-compatible)
  api_key: ""                      # Ou cle en dur ici
  primary_model: "gpt-4o"          # Modele principal
  fallback_models: ["gpt-4o-mini"] # Chaine de repli
  s2_api_key: ""                   # Cle API Semantic Scholar (optionnel, limites de debit plus elevees)
  acp:                             # Utilise uniquement quand provider: "acp"
    agent: "claude"                # Commande CLI de l'agent ACP (claude, codex, gemini, etc.)
    cwd: "."                       # Repertoire de travail pour l'agent

# === Experience ===
experiment:
  mode: "sandbox"                  # simulated | sandbox | docker | ssh_remote
  time_budget_sec: 300             # Temps d'execution max par lancement (defaut : 300s)
  max_iterations: 10               # Iterations d'optimisation max
  metric_key: "val_loss"           # Nom de la metrique principale
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
    auto_install_deps: true        # Detection auto des imports 鈫?requirements.txt
  ssh_remote:
    host: ""                       # Nom d'hote du serveur GPU
    gpu_ids: []                    # Identifiants GPU disponibles
    remote_workdir: "/tmp/researchclaw_experiments"
  opencode:                          # OpenCode Beast Mode (auto-installe via `researchclaw setup`)
    enabled: true                    # Interrupteur principal (defaut : true)
    auto: true                       # Declenchement auto sans confirmation (defaut : true)
    complexity_threshold: 0.2        # 0.0-1.0 鈥?plus eleve = ne se declenche que pour les experiences complexes
    model: ""                        # Modele a forcer (vide = utilise llm.primary_model)
    timeout_sec: 600                 # Duree max en secondes pour la generation OpenCode
    max_retries: 1                   # Nombre de tentatives en cas d'echec
    workspace_cleanup: true          # Supprimer l'espace de travail temporaire apres collecte

# === Export ===
export:
  target_conference: "neurips_2025"  # neurips_2025 | iclr_2026 | icml_2026
  authors: "Anonymous"
  bib_file: "references"

# === Prompts ===
prompts:
  custom_file: ""                  # Chemin vers un YAML de prompts personnalises (vide = defauts)

# === Securite ===
security:
  hitl_required_stages: [5, 9, 20] # Etapes necessitant une approbation humaine
  allow_publish_without_approval: false
  redact_sensitive_logs: true

# === Base de connaissances ===
knowledge_base:
  backend: "markdown"              # markdown | obsidian
  root: "docs/kb"

# === Notifications ===
notifications:
  channel: "console"               # console | discord | slack
  target: ""

# === Pont MetaClaw (Optionnel) ===
metaclaw_bridge:
  enabled: false                   # Mettre a true pour activer l'apprentissage inter-executions
  proxy_url: "http://localhost:30000"  # URL du proxy MetaClaw
  skills_dir: "~/.metaclaw/skills" # Ou les competences arc-* sont stockees
  fallback_url: ""                 # Repli direct vers le LLM quand le proxy est indisponible
  fallback_api_key: ""             # Cle API pour le point d'acces de repli
  lesson_to_skill:
    enabled: true                  # Conversion automatique des lecons en competences
    min_severity: "warning"        # Severite minimum pour la conversion
    max_skills_per_run: 3          # Max de nouvelles competences par execution

# === Pont OpenClaw ===
openclaw_bridge:
  use_cron: false                  # Executions de recherche planifiees
  use_message: false               # Notifications de progression
  use_memory: false                # Persistance des connaissances inter-sessions
  use_sessions_spawn: false        # Lancement de sous-sessions paralleles
  use_web_fetch: false             # Recherche web en direct
  use_browser: false               # Collecte d'articles via navigateur
```

</details>

---

## 馃檹 Remerciements

Inspire par :

- 馃敩 [AI Scientist](https://github.com/SakanaAI/AI-Scientist) (Sakana AI) 鈥?Pionnier de la recherche automatisee
- 馃 [AutoResearch](https://github.com/karpathy/autoresearch) (Andrej Karpathy) 鈥?Automatisation de la recherche de bout en bout
- 馃寪 [FARS](https://analemma.ai/blog/introducing-fars/) (Analemma) 鈥?Systeme de recherche entierement automatise

---

## 馃搫 Licence

MIT 鈥?voir [LICENSE](../LICENSE) pour les details.

---

## 馃搶 Citation

Si vous trouvez AutoResearchClaw utile, veuillez citer :

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
  <sub>Construit avec 馃 par l'equipe AutoResearchClaw</sub>
</p>
