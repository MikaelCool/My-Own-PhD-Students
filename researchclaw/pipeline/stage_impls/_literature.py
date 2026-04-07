"""Stages 3-6: Search strategy, literature collection, screening, and knowledge extraction."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

import yaml

from researchclaw.adapters import AdapterBundle
from researchclaw.config import RCConfig
from researchclaw.knowledge.source_ingest import load_obsidian_notes, load_zotero_items
from researchclaw.llm.client import LLMClient
from researchclaw.pipeline._helpers import (
    StageResult,
    _build_fallback_queries,
    _chat_with_prompt,
    _extract_topic_keywords,
    _extract_yaml_block,
    _get_evolution_overlay,
    _load_baseline_briefing,
    _parse_jsonl_rows,
    _read_prior_artifact,
    _safe_filename,
    _safe_json_loads,
    _utcnow_iso,
    _write_jsonl,
)
from researchclaw.pipeline.stages import Stage, StageStatus
from researchclaw.prompts import PromptManager

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Local helpers
# ---------------------------------------------------------------------------


def _expand_search_queries(queries: list[str], topic: str) -> list[str]:
    """Expand search queries for broader literature coverage.

    Generates additional queries by extracting key phrases from the topic
    and creating focused sub-queries. This ensures we find papers even when
    the original queries are too narrow or specific for arXiv.
    """
    expanded = list(queries)  # keep originals
    seen = {q.lower().strip() for q in queries}

    # Extract key phrases from topic by splitting on common delimiters
    # e.g. "Comparing A, B, and C on X with Y" → ["A", "B", "C", "X", "Y"]
    topic_words = topic.split()

    # Generate shorter, broader queries from the topic
    if len(topic_words) > 5:
        # First 5 words as a broader query
        broad = " ".join(topic_words[:5])
        if broad.lower().strip() not in seen:
            expanded.append(broad)
            seen.add(broad.lower().strip())

        # Last 5 words as another perspective
        tail = " ".join(topic_words[-5:])
        if tail.lower().strip() not in seen:
            expanded.append(tail)
            seen.add(tail.lower().strip())

    # Add "survey" and "benchmark" variants of the topic
    for suffix in ("survey", "benchmark", "comparison"):
        # Take first 4 content words + suffix
        short_topic = " ".join(topic_words[:4])
        variant = f"{short_topic} {suffix}"
        if variant.lower().strip() not in seen:
            expanded.append(variant)
            seen.add(variant.lower().strip())

    return expanded


def _resolve_seed_files(
    entries: tuple[str, ...],
    *,
    exts: tuple[str, ...],
    max_files: int,
) -> list[Path]:
    resolved: list[Path] = []
    seen: set[str] = set()
    for entry in entries:
        if not entry:
            continue
        path = Path(entry).expanduser()
        if not path.is_absolute():
            path = Path.cwd() / path
        candidates: list[Path] = []
        if path.is_file() and path.suffix.lower() in exts:
            candidates = [path]
        elif path.is_dir():
            for ext in exts:
                candidates.extend(sorted(path.rglob(f"*{ext}")))
        for candidate in candidates:
            key = str(candidate.resolve()) if candidate.exists() else str(candidate)
            if key not in seen:
                seen.add(key)
                resolved.append(candidate)
            if len(resolved) >= max_files:
                return resolved
    return resolved


def _extract_note_title(text: str, fallback: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip() or fallback
        if stripped:
            return stripped[:120]
    return fallback


def _read_seed_notes(paths: list[Path], *, max_chars: int = 6000) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        text = text.strip()
        # Short structured notes are still valuable seeds for retrieval/screening.
        if len(text) < 20:
            continue
        rows.append(
            {
                "id": f"note-{_safe_filename(path.stem)}",
                "title": _extract_note_title(text, path.stem),
                "source": "local_note",
                "url": str(path),
                "year": 0,
                "abstract": re.sub(r"\s+", " ", text[:900]),
                "full_text_excerpt": re.sub(r"\s+", " ", text[:max_chars]),
                "collected_at": _utcnow_iso(),
                "source_path": str(path),
            }
        )
    return rows


def _read_seed_pdfs(paths: list[Path], *, max_docs: int = 8) -> list[dict[str, Any]]:
    if not paths:
        return []
    try:
        from researchclaw.web.pdf_extractor import PDFExtractor
    except Exception:  # noqa: BLE001
        return []

    extractor = PDFExtractor(max_pages=4, extract_sections=False)
    rows: list[dict[str, Any]] = []
    for path in paths[:max_docs]:
        pdf = extractor.extract(path)
        if not pdf.success or not pdf.has_content:
            continue
        title = pdf.title.strip() or path.stem
        authors = [{"name": name} for name in pdf.authors[:6] if name]
        rows.append(
            {
                "id": f"pdf-{_safe_filename(path.stem)}",
                "title": title,
                "source": "local_pdf",
                "url": str(path),
                "year": 0,
                "abstract": re.sub(r"\s+", " ", (pdf.abstract or pdf.text[:900]).strip()),
                "authors": authors,
                "collected_at": _utcnow_iso(),
                "source_path": str(path),
            }
        )
    return rows


def _dedupe_seed_candidates(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        title = str(row.get("title", "")).strip().lower()
        source_path = str(row.get("source_path", "")).strip().lower()
        url = str(row.get("url", "")).strip().lower()
        source = str(row.get("source", "")).strip().lower()
        key = "||".join((source, title, source_path or url))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def _collect_seed_inputs(
    config: RCConfig,
    *,
    max_seed_docs: int,
) -> tuple[list[Path], list[Path], list[dict[str, Any]], dict[str, int]]:
    pdf_seed_files = _resolve_seed_files(
        getattr(config.research, "literature_seed_paths", ()),
        exts=(".pdf",),
        max_files=max_seed_docs,
    )
    note_seed_files = _resolve_seed_files(
        getattr(config.research, "note_seed_paths", ()),
        exts=(".md", ".txt"),
        max_files=max_seed_docs,
    )
    zotero_items = load_zotero_items(
        getattr(config.research, "zotero_library_path", ""),
        attachment_root=getattr(config.research, "zotero_attachment_root", ""),
        collection_filters=getattr(config.research, "zotero_collection_filters", ()),
        max_items=max(1, int(getattr(config.research, "max_zotero_items", max_seed_docs))),
    )
    obsidian_notes = load_obsidian_notes(
        getattr(config.knowledge_base, "obsidian_vault", ""),
        max_notes=max(1, int(getattr(config.research, "max_obsidian_notes", max_seed_docs))),
    )
    local_note_candidates = _read_seed_notes(note_seed_files, max_chars=5000)
    local_pdf_candidates = _read_seed_pdfs(pdf_seed_files, max_docs=max_seed_docs)
    seed_candidates = _dedupe_seed_candidates(
        zotero_items + obsidian_notes + local_note_candidates + local_pdf_candidates
    )
    source_mix: dict[str, int] = {}
    for row in seed_candidates:
        source = str(row.get("source", "seed"))
        source_mix[source] = source_mix.get(source, 0) + 1
    return pdf_seed_files, note_seed_files, seed_candidates, source_mix


def _build_seed_digest(
    *,
    topic: str,
    baseline_briefing: str,
    seed_candidates: list[dict[str, Any]],
) -> str:
    lines = [
        "# Baseline Digest",
        "",
        f"- Topic: {topic}",
        f"- Seed documents loaded: {len(seed_candidates)}",
        "",
    ]
    source_counter: dict[str, int] = {}
    for row in seed_candidates:
        source = str(row.get("source", "seed"))
        source_counter[source] = source_counter.get(source, 0) + 1
    if source_counter:
        lines.append(
            "- Seed source mix: "
            + ", ".join(f"{name}={count}" for name, count in sorted(source_counter.items()))
        )
        lines.append("")
    if baseline_briefing.strip():
        lines.extend(
            [
                "## Baseline Briefing Excerpt",
                baseline_briefing[:2200],
                "",
            ]
        )
    if seed_candidates:
        lines.append("## Seed Literature / Notes")
        for row in seed_candidates[:8]:
            title = str(row.get("title", "Untitled"))
            source = str(row.get("source", "seed"))
            excerpt = str(row.get("abstract", "") or row.get("full_text_excerpt", "")).strip()
            lines.append(f"- **{title}** [{source}]")
            if excerpt:
                lines.append(f"  - {excerpt[:280]}")
        lines.append("")
    lines.extend(
        [
            "## Usage",
            "- Prioritize these seed sources before broad web expansion.",
            "- Reuse their terminology for shortlist screening and novelty positioning.",
            "",
        ]
    )
    return "\n".join(lines)


def _build_literature_shortlist_md(shortlist: list[dict[str, Any]]) -> str:
    lines = [
        "# Literature Shortlist",
        "",
        f"- Papers retained: {len(shortlist)}",
        "",
    ]
    for idx, row in enumerate(shortlist[:20], start=1):
        title = str(row.get("title", f"Paper {idx}"))
        year = row.get("year", "")
        source = row.get("source", "")
        reason = str(row.get("keep_reason", "")).strip()
        relevance = row.get("relevance_score", "")
        quality = row.get("quality_score", "")
        lines.append(f"## {idx}. {title}")
        lines.append(f"- Year: {year}")
        lines.append(f"- Source: {source}")
        if relevance != "":
            lines.append(f"- Relevance: {relevance}")
        if quality != "":
            lines.append(f"- Quality: {quality}")
        if reason:
            lines.append(f"- Keep reason: {reason}")
        abstract = str(row.get("abstract", "")).strip()
        if abstract:
            abstract_snippet = re.sub(r"\s+", " ", abstract)[:320]
            lines.append(f"- Abstract snippet: {abstract_snippet}")
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Stage executors
# ---------------------------------------------------------------------------


def _execute_search_strategy(
    stage_dir: Path,
    run_dir: Path,
    config: RCConfig,
    adapters: AdapterBundle,
    *,
    llm: LLMClient | None = None,
    prompts: PromptManager | None = None,
) -> StageResult:
    problem_tree = _read_prior_artifact(run_dir, "problem_tree.md") or ""
    topic = config.research.topic
    max_seed_docs = max(1, int(getattr(config.research, "max_seed_docs", 12)))
    pdf_seed_files, note_seed_files, seed_candidates, _source_mix = _collect_seed_inputs(
        config,
        max_seed_docs=max_seed_docs,
    )
    baseline_briefing = _load_baseline_briefing(config)
    local_seed_sources: list[dict[str, Any]] = []
    if getattr(config.research, "zotero_library_path", "").strip():
        local_seed_sources.append(
            {
                "id": "zotero-library",
                "name": "Zotero Library",
                "type": "zotero_library",
                "url": config.research.zotero_library_path,
                "status": "configured",
                "query": "zotero_library",
                "verified_at": _utcnow_iso(),
            }
        )
    if getattr(config.knowledge_base, "obsidian_vault", "").strip():
        local_seed_sources.append(
            {
                "id": "obsidian-vault",
                "name": "Obsidian Vault",
                "type": "obsidian_vault",
                "url": config.knowledge_base.obsidian_vault,
                "status": "configured",
                "query": "obsidian_vault",
                "verified_at": _utcnow_iso(),
            }
        )
    for entry in config.research.literature_seed_paths:
        local_seed_sources.append(
            {
                "id": f"local-literature-{_safe_filename(Path(entry).name or 'seed')}",
                "name": f"Local Literature Seed: {entry}",
                "type": "local_seed",
                "url": entry,
                "status": "configured",
                "query": "local_pdf_seed",
                "verified_at": _utcnow_iso(),
            }
        )
    for entry in config.research.note_seed_paths:
        local_seed_sources.append(
            {
                "id": f"local-note-{_safe_filename(Path(entry).name or 'note')}",
                "name": f"Local Note Seed: {entry}",
                "type": "local_note",
                "url": entry,
                "status": "configured",
                "query": "local_note_seed",
                "verified_at": _utcnow_iso(),
            }
        )
    plan: dict[str, Any] | None = None
    sources: list[dict[str, Any]] | None = None
    if llm is not None:
        _pm = prompts or PromptManager()
        _overlay = _get_evolution_overlay(run_dir, "search_strategy")
        sp = _pm.for_stage("search_strategy", evolution_overlay=_overlay, topic=topic, problem_tree=problem_tree)
        resp = _chat_with_prompt(
            llm,
            sp.system,
            sp.user,
            json_mode=sp.json_mode,
            max_tokens=sp.max_tokens,
        )
        payload = _safe_json_loads(resp.content, {})
        if isinstance(payload, dict):
            yaml_text = str(payload.get("search_plan_yaml", "")).strip()
            if yaml_text:
                try:
                    parsed = yaml.safe_load(_extract_yaml_block(yaml_text))
                except yaml.YAMLError:
                    parsed = None
                if isinstance(parsed, dict):
                    plan = parsed
            src = payload.get("sources", [])
            if isinstance(src, list):
                sources = [item for item in src if isinstance(item, dict)]
    if plan is None:
        # Build smart fallback queries by extracting key terms from topic
        # instead of using the raw (often very long) topic string.
        _fallback_queries = _build_fallback_queries(topic)
        plan = {
            "topic": topic,
            "generated": _utcnow_iso(),
            "search_strategies": [
                {
                    "name": "keyword_core",
                    "queries": _fallback_queries[:5],
                    "sources": ["arxiv", "semantic_scholar", "openreview"],
                    "max_results_per_query": 60,
                },
                {
                    "name": "backward_forward_citation",
                    "queries": _fallback_queries[5:10] or _fallback_queries[:3],
                    "sources": ["semantic_scholar", "google_scholar"],
                    "depth": 1,
                },
            ],
            "filters": {
                "min_year": 2020,
                "language": ["en"],
                "peer_review_preferred": True,
            },
            "deduplication": {"method": "title_doi_hash", "fuzzy_threshold": 0.9},
        }
    if not sources:
        sources = local_seed_sources + [
            {
                "id": "arxiv",
                "name": "arXiv",
                "type": "api",
                "url": "https://export.arxiv.org/api/query",
                "status": "available",
                "query": topic,
                "verified_at": _utcnow_iso(),
            },
            {
                "id": "semantic_scholar",
                "name": "Semantic Scholar",
                "type": "api",
                "url": "https://api.semanticscholar.org/graph/v1/paper/search",
                "status": "available",
                "query": topic,
                "verified_at": _utcnow_iso(),
            },
        ]
    elif local_seed_sources:
        sources = local_seed_sources + sources
    if config.openclaw_bridge.use_web_fetch:
        for src in sources:
            try:
                response = adapters.web_fetch.fetch(str(src.get("url", "")))
                src["status"] = (
                    "verified"
                    if response.status_code in (200, 301, 302, 405)
                    else "unreachable"
                )
                src["http_status"] = response.status_code
            except Exception:  # noqa: BLE001
                src["status"] = "unknown"
    (stage_dir / "search_plan.yaml").write_text(
        yaml.dump(plan, default_flow_style=False, allow_unicode=True),
        encoding="utf-8",
    )
    (stage_dir / "sources.json").write_text(
        json.dumps(
            {"sources": sources, "count": len(sources), "generated": _utcnow_iso()},
            indent=2,
        ),
        encoding="utf-8",
    )

    # F1.5: Extract queries from plan for Stage 4 real literature search
    queries_list: list[str] = []
    year_min = 2020
    if isinstance(plan, dict):
        strategies = plan.get("search_strategies", [])
        if isinstance(strategies, list):
            for strat in strategies:
                if isinstance(strat, dict):
                    qs = strat.get("queries", [])
                    if isinstance(qs, list):
                        queries_list.extend(str(q) for q in qs if q)
        filters = plan.get("filters", {})
        if isinstance(filters, dict) and filters.get("min_year"):
            try:
                year_min = int(filters["min_year"])
            except (ValueError, TypeError):
                pass

    # --- Sanitize queries: shorten overly long queries ---
    # LLMs often produce the full topic title as a query, which is too long for
    # arXiv and Semantic Scholar (they work best with 3-8 keyword queries).
    _stop = {
        "a", "an", "the", "of", "for", "in", "on", "and", "or", "with",
        "to", "by", "from", "its", "is", "are", "was", "be", "as", "at",
        "via", "using", "based", "study", "analysis", "empirical",
        "towards", "toward", "into", "exploring", "comparison", "tasks",
        "effectiveness", "investigation", "comprehensive", "novel",
    }

    def _extract_keywords(text: str) -> list[str]:
        """Extract meaningful keywords from text, removing stop words."""
        return [
            w for w in re.split(r"[^a-zA-Z0-9]+", text)
            if w.lower() not in _stop and len(w) > 1
        ]

    _MAX_QUERY_LEN = 60  # characters — beyond this, shorten to keywords
    _SEARCH_SUFFIXES = ["benchmark", "survey", "seminal", "state of the art"]

    def _shorten_query(q: str, max_kw: int = 6) -> str:
        """Shorten a query to *max_kw* keywords, preserving any trailing suffix."""
        q_stripped = q.strip()
        # Check if query ends with a known search suffix
        suffix = ""
        q_core = q_stripped
        for sfx in _SEARCH_SUFFIXES:
            if q_stripped.lower().endswith(sfx):
                suffix = sfx
                q_core = q_stripped[: -len(sfx)].strip()
                break
        # Extract keywords from the core part
        kws = _extract_keywords(q_core)
        shortened = " ".join(kws[:max_kw])
        if suffix:
            shortened = f"{shortened} {suffix}"
        return shortened

    if queries_list:
        sanitized: list[str] = []
        for q in queries_list:
            if len(q) > _MAX_QUERY_LEN:
                shortened = _shorten_query(q)
                if shortened.strip():
                    sanitized.append(shortened)
            else:
                sanitized.append(q)
        queries_list = sanitized

    if not queries_list:
        # Build diverse keyword queries from the topic
        _words = _extract_keywords(topic)
        kw_primary = " ".join(_words[:6])
        kw_short = " ".join(_words[:4])
        queries_list = [
            kw_primary,
            f"{kw_short} benchmark",
            f"{kw_short} survey",
        ]

    # Ensure minimum query diversity — if dedup leaves too few, add variants
    _all_kw = _extract_keywords(topic)
    _seen_q: set[str] = set()
    unique_queries: list[str] = []
    for q in queries_list:
        q_lower = q.strip().lower()
        if q_lower and q_lower not in _seen_q:
            _seen_q.add(q_lower)
            unique_queries.append(q.strip())
    # If we have fewer than 5 unique queries, generate supplemental keyword variants
    if len(unique_queries) < 5 and len(_all_kw) >= 3:
        supplements = [
            " ".join(_all_kw[:4]) + " survey",
            " ".join(_all_kw[:4]) + " benchmark",
            " ".join(_all_kw[1:5]),  # shifted window for diversity
            " ".join(_all_kw[:3]) + " comparison",
            " ".join(_all_kw[:3]) + " deep learning",
            " ".join(_all_kw[2:6]),  # another shifted window
        ]
        for s in supplements:
            s_lower = s.strip().lower()
            if s_lower not in _seen_q:
                _seen_q.add(s_lower)
                unique_queries.append(s.strip())
            if len(unique_queries) >= 8:
                break
    queries_list = unique_queries
    (stage_dir / "queries.json").write_text(
        json.dumps({"queries": queries_list, "year_min": year_min}, indent=2),
        encoding="utf-8",
    )
    return StageResult(
        stage=Stage.SEARCH_STRATEGY,
        status=StageStatus.DONE,
        artifacts=("search_plan.yaml", "sources.json", "queries.json"),
        evidence_refs=(
            "stage-03/search_plan.yaml",
            "stage-03/sources.json",
            "stage-03/queries.json",
        ),
    )


def _execute_literature_collect(
    stage_dir: Path,
    run_dir: Path,
    config: RCConfig,
    adapters: AdapterBundle,
    *,
    llm: LLMClient | None = None,
    prompts: PromptManager | None = None,
) -> StageResult:
    """Stage 4: Collect literature — prefer real APIs, fallback to LLM."""
    topic = config.research.topic
    max_seed_docs = max(1, int(getattr(config.research, "max_seed_docs", 12)))
    pdf_seed_files, note_seed_files, seed_candidates, source_mix = _collect_seed_inputs(
        config,
        max_seed_docs=max_seed_docs,
    )
    baseline_briefing = _load_baseline_briefing(config)

    # Read queries.json from Stage 3 (F1.5 output)
    queries_text = _read_prior_artifact(run_dir, "queries.json")
    queries_data = _safe_json_loads(queries_text or "{}", {})
    queries: list[str] = queries_data.get("queries", [topic])
    year_min: int = queries_data.get("year_min", 2020)

    # --- Try real API search first ---
    candidates: list[dict[str, Any]] = list(seed_candidates)
    bibtex_entries: list[str] = []
    real_search_succeeded = False

    try:
        from researchclaw.literature.search import (
            search_papers_multi_query,
            papers_to_bibtex,
        )

        # Expand queries for broader coverage
        expanded_queries = _expand_search_queries(queries, config.research.topic)
        logger.info(
            "[literature] Searching %d queries (expanded from %d) "
            "across OpenAlex → S2 → arXiv…",
            len(expanded_queries),
            len(queries),
        )
        papers = search_papers_multi_query(
            expanded_queries,
            limit_per_query=40,
            year_min=year_min,
            s2_api_key=config.llm.s2_api_key,
        )
        if papers:
            real_search_succeeded = True
            # Count by source
            src_counts: dict[str, int] = {}
            for p in papers:
                src_counts[p.source] = src_counts.get(p.source, 0) + 1
                d = p.to_dict()
                d["collected_at"] = _utcnow_iso()
                candidates.append(d)
                bibtex_entries.append(p.to_bibtex())
            src_str = ", ".join(f"{s}: {n}" for s, n in src_counts.items())
            logger.info(
                "[literature] Found %d papers (%s)", len(papers), src_str
            )
    except Exception:  # noqa: BLE001
        logger.warning(
            "[rate-limit] Literature search failed — falling back to LLM",
            exc_info=True,
        )

    # --- Inject foundational/seminal papers ---
    try:
        from researchclaw.data import load_seminal_papers
        seminal = load_seminal_papers(topic)
        if seminal:
            _existing_titles = {c.get("title", "").lower() for c in candidates}
            _injected = 0
            for sp in seminal:
                if sp.get("title", "").lower() not in _existing_titles:
                    candidates.append({
                        "id": f"seminal-{sp.get('cite_key', '')}",
                        "title": sp.get("title", ""),
                        "source": "seminal_library",
                        "url": "",
                        "year": sp.get("year", 2020),
                        "abstract": f"Foundational paper on {', '.join(sp.get('keywords', [])[:3])}.",
                        "authors": [{"name": sp.get("authors", "")}],
                        "cite_key": sp.get("cite_key", ""),
                        "venue": sp.get("venue", ""),
                        "collected_at": _utcnow_iso(),
                    })
                    _injected += 1
            if _injected:
                logger.info("Stage 4: Injected %d seminal papers from seed library", _injected)
    except Exception:  # noqa: BLE001
        logger.debug("Seminal paper injection skipped", exc_info=True)

    # --- Fallback: LLM-generated candidates ---
    if not candidates and llm is not None:
        plan_text = _read_prior_artifact(run_dir, "search_plan.yaml") or ""
        _pm = prompts or PromptManager()
        _overlay = _get_evolution_overlay(run_dir, "literature_collect")
        sp = _pm.for_stage("literature_collect", evolution_overlay=_overlay, topic=topic, plan_text=plan_text)
        resp = _chat_with_prompt(
            llm,
            sp.system,
            sp.user,
            json_mode=sp.json_mode,
            max_tokens=sp.max_tokens,
        )
        payload = _safe_json_loads(resp.content, {})
        if isinstance(payload, dict) and isinstance(payload.get("candidates"), list):
            candidates = [row for row in payload["candidates"] if isinstance(row, dict)]

    # --- Web search augmentation (Tavily/DDG + Google Scholar + Crawl4AI) ---
    web_context_parts: list[str] = []
    if config.web_search.enabled:
        try:
            from researchclaw.web.agent import WebSearchAgent
            import os

            tavily_key = config.web_search.tavily_api_key or os.environ.get(
                config.web_search.tavily_api_key_env, ""
            )
            web_agent = WebSearchAgent(
                tavily_api_key=tavily_key,
                enable_scholar=config.web_search.enable_scholar,
                enable_crawling=config.web_search.enable_crawling,
                enable_pdf=config.web_search.enable_pdf_extraction,
                max_web_results=config.web_search.max_web_results,
                max_scholar_results=config.web_search.max_scholar_results,
                max_crawl_urls=config.web_search.max_crawl_urls,
            )
            web_result = web_agent.search_and_extract(
                topic, search_queries=queries,
            )

            # Convert Google Scholar papers into candidates
            for sp in web_result.scholar_papers:
                _existing_titles = {
                    str(c.get("title", "")).lower().strip() for c in candidates
                }
                if sp.title.lower().strip() not in _existing_titles:
                    lit_paper = sp.to_literature_paper()
                    d = lit_paper.to_dict()
                    d["collected_at"] = _utcnow_iso()
                    candidates.append(d)
                    bibtex_entries.append(lit_paper.to_bibtex())

            # Save web search context for downstream stages
            web_context = web_result.to_context_string(max_length=20_000)
            if web_context.strip():
                (stage_dir / "web_context.md").write_text(
                    web_context, encoding="utf-8"
                )
                web_context_parts.append(web_context)

            # Save full web search metadata
            (stage_dir / "web_search_result.json").write_text(
                json.dumps(web_result.to_dict(), indent=2, default=str),
                encoding="utf-8",
            )

            logger.info(
                "[web-search] Added %d scholar papers, %d web results, %d crawled pages",
                len(web_result.scholar_papers),
                len(web_result.web_results),
                len(web_result.crawled_pages),
            )
        except Exception:  # noqa: BLE001
            logger.warning(
                "[web-search] Web search augmentation failed — continuing with academic APIs only",
                exc_info=True,
            )

    # --- Ultimate fallback: placeholder data ---
    # BUG-L2: Do NOT overwrite real_search_succeeded here — it was already
    # set correctly in the search block above. Overwriting would mislabel
    # LLM-hallucinated or seminal papers as "real search" results.
    if not candidates:
        logger.warning("Stage 4: All literature searches failed — using placeholder papers")
        candidates = [
            {
                "id": f"candidate-{idx + 1}",
                "title": f"[Placeholder] Study {idx + 1} on {topic}",
                "source": "arxiv" if idx % 2 == 0 else "semantic_scholar",
                "url": f"https://example.org/{_safe_filename(topic.lower())}/{idx + 1}",
                "year": 2024,
                "abstract": f"This candidate investigates {topic} and reports preliminary findings.",
                "collected_at": _utcnow_iso(),
                "is_placeholder": True,
            }
            for idx in range(max(20, config.research.daily_paper_count or 20))
        ]

    # Write candidates
    out = stage_dir / "candidates.jsonl"
    _write_jsonl(out, candidates)

    # BUG-50 fix: Generate BibTeX from candidates when real search failed
    # (LLM/placeholder fallback paths don't populate bibtex_entries)
    if not bibtex_entries and candidates:
        for c in candidates:
            if c.get("is_placeholder"):
                continue
            _ck = c.get("cite_key", "")
            if not _ck:
                # Derive cite_key from first author surname + year
                _authors = c.get("authors", [])
                _surname = "unknown"
                if isinstance(_authors, list) and _authors:
                    _a0 = _authors[0] if isinstance(_authors[0], str) else (_authors[0].get("name", "") if isinstance(_authors[0], dict) else "")
                    _surname = _a0.split()[-1].lower() if _a0.strip() else "unknown"
                _yr = c.get("year", 2024)
                _title_word = "".join(
                    w[0] for w in str(c.get("title", "study")).split()[:3]
                ).lower()
                _ck = f"{_surname}{_yr}{_title_word}"
            _title = c.get("title", "Untitled")
            _year = c.get("year", 2024)
            _author_str = ""
            _raw_authors = c.get("authors", [])
            if isinstance(_raw_authors, list):
                _names = []
                for _a in _raw_authors:
                    if isinstance(_a, str):
                        _names.append(_a)
                    elif isinstance(_a, dict):
                        _names.append(_a.get("name", ""))
                _author_str = " and ".join(n for n in _names if n)
            bibtex_entries.append(
                f"@article{{{_ck},\n"
                f"  title={{{_title}}},\n"
                f"  author={{{_author_str or 'Unknown'}}},\n"
                f"  year={{{_year}}},\n"
                f"  url={{{c.get('url', '')}}},\n"
                f"}}"
            )
        logger.info(
            "Stage 4: Generated %d BibTeX entries from candidates (fallback)",
            len(bibtex_entries),
        )

    # Write references.bib (F2.4)
    artifacts = ["candidates.jsonl"]
    if seed_candidates or baseline_briefing.strip():
        baseline_digest = _build_seed_digest(
            topic=topic,
            baseline_briefing=baseline_briefing,
            seed_candidates=seed_candidates,
        )
        (stage_dir / "baseline_digest.md").write_text(
            baseline_digest,
            encoding="utf-8",
        )
        (stage_dir / "local_seed_manifest.json").write_text(
            json.dumps(
                {
                    "pdf_seed_files": [str(p) for p in pdf_seed_files],
                    "note_seed_files": [str(p) for p in note_seed_files],
                    "zotero_library_path": getattr(config.research, "zotero_library_path", ""),
                    "obsidian_vault": getattr(config.knowledge_base, "obsidian_vault", ""),
                    "priority_order": ["zotero", "obsidian", "local_seed"],
                    "source_mix": source_mix,
                    "seed_candidates": len(seed_candidates),
                    "generated": _utcnow_iso(),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        artifacts.extend(["baseline_digest.md", "local_seed_manifest.json"])
    if web_context_parts:
        artifacts.append("web_context.md")
    if (stage_dir / "web_search_result.json").exists():
        artifacts.append("web_search_result.json")
    if bibtex_entries:
        bib_content = "\n\n".join(bibtex_entries) + "\n"
        (stage_dir / "references.bib").write_text(bib_content, encoding="utf-8")
        artifacts.append("references.bib")
        logger.info(
            "Stage 4: Wrote %d BibTeX entries to references.bib", len(bibtex_entries)
        )

    # Write search metadata
    (stage_dir / "search_meta.json").write_text(
        json.dumps(
            {
                "real_search": real_search_succeeded,
                "queries_used": queries,
                "year_min": year_min,
                "seed_candidates": len(seed_candidates),
                "total_candidates": len(candidates),
                "bibtex_entries": len(bibtex_entries),
                "ts": _utcnow_iso(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    artifacts.append("search_meta.json")

    return StageResult(
        stage=Stage.LITERATURE_COLLECT,
        status=StageStatus.DONE,
        artifacts=tuple(artifacts),
        evidence_refs=tuple(f"stage-04/{a}" for a in artifacts),
    )


def _execute_literature_screen(
    stage_dir: Path,
    run_dir: Path,
    config: RCConfig,
    adapters: AdapterBundle,
    *,
    llm: LLMClient | None = None,
    prompts: PromptManager | None = None,
) -> StageResult:
    candidates_text = _read_prior_artifact(run_dir, "candidates.jsonl") or ""

    # --- P1-1: keyword relevance pre-filter ---
    # Before LLM screening, drop papers whose title+abstract share no keywords
    # with the research topic.  This catches cross-domain noise cheaply.
    topic_keywords = _extract_topic_keywords(
        config.research.topic, config.research.domains
    )
    filtered_rows: list[dict[str, Any]] = []
    dropped_count = 0
    for raw_line in candidates_text.strip().splitlines():
        row = _safe_json_loads(raw_line, {})
        if not isinstance(row, dict):
            continue
        title = str(row.get("title", "")).lower()
        abstract = str(row.get("abstract", "")).lower()
        text_blob = f"{title} {abstract}"
        overlap = sum(1 for kw in topic_keywords if kw in text_blob)
        # T2.2: Relaxed from ≥2 to ≥1 keyword hit — previous threshold was
        # too aggressive (94% rejection rate).  Single-keyword matches are
        # still screened by the LLM in the next step.
        if overlap >= 1:
            row["keyword_overlap"] = overlap
            filtered_rows.append(row)
        else:
            dropped_count += 1
    # If pre-filter dropped everything, fall back to original (safety valve)
    if not filtered_rows:
        filtered_rows = _parse_jsonl_rows(candidates_text)
    # Rebuild candidates_text from filtered rows
    candidates_text = "\n".join(
        json.dumps(r, ensure_ascii=False) for r in filtered_rows
    )
    logger.info(
        "Domain pre-filter: kept %d, dropped %d (keywords: %s)",
        len(filtered_rows),
        dropped_count,
        topic_keywords[:8],
    )

    shortlist: list[dict[str, Any]] = []
    if llm is not None:
        _pm = prompts or PromptManager()
        _overlay = _get_evolution_overlay(run_dir, "literature_screen")
        sp = _pm.for_stage(
            "literature_screen",
            evolution_overlay=_overlay,
            topic=config.research.topic,
            domains=", ".join(config.research.domains)
            if config.research.domains
            else "general",
            quality_threshold=config.research.quality_threshold,
            candidates_text=candidates_text,
        )
        resp = _chat_with_prompt(
            llm,
            sp.system,
            sp.user,
            json_mode=sp.json_mode,
            max_tokens=sp.max_tokens,
        )
        payload = _safe_json_loads(resp.content, {})
        if isinstance(payload, dict) and isinstance(payload.get("shortlist"), list):
            shortlist = [row for row in payload["shortlist"] if isinstance(row, dict)]
    # T2.2: Ensure minimum shortlist size of 15 for adequate related work
    _MIN_SHORTLIST = 15
    if not shortlist:
        rows = (
            filtered_rows[:_MIN_SHORTLIST]
            if filtered_rows
            else _parse_jsonl_rows(candidates_text)[:_MIN_SHORTLIST]
        )
        for idx, item in enumerate(rows):
            item["relevance_score"] = round(0.75 - idx * 0.02, 3)
            item["quality_score"] = round(0.72 - idx * 0.015, 3)
            item["keep_reason"] = "Template screened entry"
            shortlist.append(item)
    elif len(shortlist) < _MIN_SHORTLIST:
        # T2.2: LLM returned too few — supplement from filtered candidates
        existing_titles = {
            str(s.get("title", "")).lower().strip() for s in shortlist
        }
        for row in filtered_rows:
            if len(shortlist) >= _MIN_SHORTLIST:
                break
            title_lower = str(row.get("title", "")).lower().strip()
            if title_lower and title_lower not in existing_titles:
                row.setdefault("relevance_score", 0.5)
                row.setdefault("quality_score", 0.5)
                row.setdefault("keep_reason", "Supplemented to meet minimum shortlist")
                shortlist.append(row)
                existing_titles.add(title_lower)
        logger.info(
            "Stage 5: Supplemented shortlist to %d papers (minimum: %d)",
            len(shortlist), _MIN_SHORTLIST,
        )
    out = stage_dir / "shortlist.jsonl"
    _write_jsonl(out, shortlist)
    (stage_dir / "literature_shortlist.md").write_text(
        _build_literature_shortlist_md(shortlist),
        encoding="utf-8",
    )
    return StageResult(
        stage=Stage.LITERATURE_SCREEN,
        status=StageStatus.DONE,
        artifacts=("shortlist.jsonl", "literature_shortlist.md"),
        evidence_refs=("stage-05/shortlist.jsonl", "stage-05/literature_shortlist.md"),
    )


def _execute_knowledge_extract(
    stage_dir: Path,
    run_dir: Path,
    config: RCConfig,
    adapters: AdapterBundle,
    *,
    llm: LLMClient | None = None,
    prompts: PromptManager | None = None,
) -> StageResult:
    shortlist = _read_prior_artifact(run_dir, "shortlist.jsonl") or ""
    shortlist_digest = _read_prior_artifact(run_dir, "literature_shortlist.md") or ""

    # Inject web context from Stage 4 if available
    web_context = _read_prior_artifact(run_dir, "web_context.md") or ""
    if shortlist_digest:
        shortlist = shortlist_digest + "\n\n--- Shortlist JSONL ---\n" + shortlist[:12_000]
    if web_context:
        shortlist = shortlist + "\n\n--- Web Search Context ---\n" + web_context[:10_000]

    cards_dir = stage_dir / "cards"
    cards_dir.mkdir(parents=True, exist_ok=True)
    cards: list[dict[str, Any]] = []
    if llm is not None:
        _pm = prompts or PromptManager()
        _overlay = _get_evolution_overlay(run_dir, "knowledge_extract")
        sp = _pm.for_stage("knowledge_extract", evolution_overlay=_overlay, shortlist=shortlist)
        resp = _chat_with_prompt(
            llm,
            sp.system,
            sp.user,
            json_mode=sp.json_mode,
            max_tokens=sp.max_tokens,
        )
        payload = _safe_json_loads(resp.content, {})
        if isinstance(payload, dict) and isinstance(payload.get("cards"), list):
            cards = [item for item in payload["cards"] if isinstance(item, dict)]
    if not cards:
        rows = _parse_jsonl_rows(shortlist)
        for idx, paper in enumerate(rows[:6]):
            title = str(paper.get("title", f"Paper {idx + 1}"))
            cards.append(
                {
                    "card_id": f"card-{idx + 1}",
                    "title": title,
                    "problem": f"How to improve {config.research.topic}",
                    "method": "Template method summary",
                    "data": "Template dataset",
                    "metrics": "Template metric",
                    "findings": "Template key finding",
                    "limitations": "Template limitation",
                    "citation": str(paper.get("url", "")),
                    "cite_key": str(paper.get("cite_key", "")),
                }
            )
    for idx, card in enumerate(cards):
        card_id = _safe_filename(str(card.get("card_id", f"card-{idx + 1}")))
        parts = [f"# {card.get('title', card_id)}", ""]
        for key in (
            "cite_key",
            "problem",
            "method",
            "data",
            "metrics",
            "findings",
            "limitations",
            "citation",
        ):
            parts.append(f"## {key.title()}")
            parts.append(str(card.get(key, "")))
            parts.append("")
        (cards_dir / f"{card_id}.md").write_text("\n".join(parts), encoding="utf-8")
    return StageResult(
        stage=Stage.KNOWLEDGE_EXTRACT,
        status=StageStatus.DONE,
        artifacts=("cards/",),
        evidence_refs=("stage-06/cards/",),
    )
