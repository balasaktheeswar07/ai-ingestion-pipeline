import json
import logging
import re
from datetime import UTC, datetime
from difflib import SequenceMatcher
from pathlib import Path

from models.schemas import EntityMapping

logger = logging.getLogger(__name__)

_SUFFIXES = re.compile(
    r"\b(incorporated|inc\.?|llc\.?|ltd\.?|limited|corp\.?|corporation|co\.?|company|pbc|technologies|tech|labs)\b",
    re.I,
)


def normalize_name(name: str) -> str:
    """Deterministic normalization: lowercase, strip punctuation and legal entity suffixes."""
    if not name:
        return ""
    cleaned = re.sub(r"[^\w\s]+", " ", name)
    cleaned = _SUFFIXES.sub("", cleaned)
    cleaned = re.sub(r"[^a-z0-9]+", " ", cleaned.lower())
    return " ".join(cleaned.split())


def load_entities(path: Path = Path("config/entities.json")) -> dict[str, list[str]]:
    """Load canonical entity seeds and aliases from configuration."""
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as error:
        logger.warning("Failed to load entity seeds from %s: %s", path, error)
        return {}


class EntityResolver:
    """Conservative entity resolver integrating deterministic normalization, alias mapping,
    and strict threshold fuzzy matching with persistent mapping logs.
    """

    def __init__(
        self,
        seeds: dict[str, list[str]] | None = None,
        fuzzy_threshold: float = 0.92,
        mapping_log: str | Path | None = None,
    ) -> None:
        self.seeds = seeds if seeds is not None else load_entities()
        self.fuzzy_threshold = fuzzy_threshold
        self.mapping_log = Path(mapping_log) if mapping_log else None

        # Build lookup maps
        self.canonical_map: dict[str, str] = {}
        self.alias_map: dict[str, str] = {}
        self.compact_map: dict[str, tuple[str, str]] = {}

        for canonical, aliases in self.seeds.items():
            norm_canonical = normalize_name(canonical)
            if norm_canonical:
                self.canonical_map[norm_canonical] = canonical
                self.compact_map[norm_canonical.replace(" ", "")] = (canonical, "normalized_exact")

            for alias in aliases:
                norm_alias = normalize_name(alias)
                if norm_alias:
                    self.alias_map[norm_alias] = canonical
                    self.compact_map[norm_alias.replace(" ", "")] = (canonical, "alias")

    def resolve(self, raw_name: str, source_url: str | None = None) -> EntityMapping:
        """Resolve a raw entity name against known seeds and aliases."""
        trimmed_raw = raw_name.strip() if raw_name else ""
        normalized = normalize_name(trimmed_raw)
        compact = normalized.replace(" ", "")

        canonical: str | None = None
        method = "no_match"
        confidence = 0.0

        if not trimmed_raw or not normalized:
            mapping = EntityMapping(
                raw_name=raw_name or "",
                normalized_name="",
                canonical_name=None,
                match_method="no_match",
                confidence=0.0,
                source_url=source_url,
                timestamp=datetime.now(UTC),
            )
            self._log_mapping(mapping)
            return mapping

        # 1. Exact raw match against canonical names
        if trimmed_raw in self.seeds:
            canonical = trimmed_raw
            method = "exact"
            confidence = 1.0

        # 2. Normalized match against canonical names
        elif normalized in self.canonical_map:
            canonical = self.canonical_map[normalized]
            method = "normalized_exact" if trimmed_raw != canonical else "exact"
            confidence = 1.0

        # 3. Match against known aliases
        elif normalized in self.alias_map:
            canonical = self.alias_map[normalized]
            method = "alias"
            confidence = 1.0

        # 4. Compact match (handles whitespace variants e.g. "open ai" -> "OpenAI")
        elif compact in self.compact_map:
            canonical, base_method = self.compact_map[compact]
            method = base_method
            confidence = 1.0

        # 5. Conservative fuzzy match (guarded by min length and strict threshold)
        elif len(normalized) >= 4:
            candidates = {**self.canonical_map, **self.alias_map}
            best_candidate = ""
            best_score = 0.0

            for candidate_norm, cand_canonical in candidates.items():
                len_ratio = min(len(normalized), len(candidate_norm)) / max(len(normalized), len(candidate_norm))
                if len_ratio < 0.75:
                    continue

                score = SequenceMatcher(None, normalized, candidate_norm).ratio()
                if score > best_score:
                    best_score = score
                    best_candidate = cand_canonical

            if best_score >= self.fuzzy_threshold and best_candidate:
                canonical = best_candidate
                method = "conservative_fuzzy"
                confidence = round(best_score, 3)

        mapping = EntityMapping(
            raw_name=raw_name,
            normalized_name=normalized,
            canonical_name=canonical,
            match_method=method,
            confidence=confidence,
            source_url=source_url,
            timestamp=datetime.now(UTC),
        )
        self._log_mapping(mapping)
        return mapping

    def _log_mapping(self, mapping: EntityMapping) -> None:
        if self.mapping_log:
            try:
                self.mapping_log.parent.mkdir(parents=True, exist_ok=True)
                with self.mapping_log.open("a", encoding="utf-8") as handle:
                    handle.write(
                        json.dumps(mapping.model_dump(mode="json", by_alias=True), ensure_ascii=False)
                        + "\n"
                    )
            except Exception as error:
                logger.warning("Failed to write entity mapping log to %s: %s", self.mapping_log, error)
