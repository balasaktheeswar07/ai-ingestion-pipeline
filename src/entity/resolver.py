import re
import json
from pathlib import Path
from datetime import UTC, datetime
from difflib import SequenceMatcher

from models.schemas import EntityMapping

_SUFFIXES = re.compile(r"\b(incorporated|inc|llc|ltd|limited|corp|corporation|co)\b", re.I)


def normalize_name(name: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", " ", name.lower())
    normalized = _SUFFIXES.sub("", normalized)
    return " ".join(normalized.split())


class EntityResolver:
    def __init__(self, seeds: dict[str, list[str]], fuzzy_threshold: float = 0.92, mapping_log: str | None = None) -> None:
        self.seeds, self.fuzzy_threshold, self.mapping_log = seeds, fuzzy_threshold, mapping_log
        self.index = {normalize_name(value): canonical for canonical, aliases in seeds.items() for value in [canonical, *aliases]}

    def resolve(self, raw_name: str, source_url: str | None = None) -> EntityMapping:
        normalized = normalize_name(raw_name)
        canonical = self.index.get(normalized)
        method, confidence = ("normalized_exact", 1.0) if canonical else ("no_match", 0.0)
        if not canonical and len(normalized) >= 4:
            candidate, score = max(((name, SequenceMatcher(None, normalized, name).ratio()) for name in self.index), default=("", 0.0), key=lambda item: item[1])
            if score >= self.fuzzy_threshold:
                canonical, method, confidence = self.index[candidate], "conservative_fuzzy", score
        mapping = EntityMapping(raw_name=raw_name, normalized_name=normalized, canonical_name=canonical, match_method=method, confidence=confidence, source_url=source_url, timestamp=datetime.now(UTC))
        if self.mapping_log:
            Path(self.mapping_log).parent.mkdir(parents=True, exist_ok=True)
            with open(self.mapping_log, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(mapping.model_dump(mode="json"), ensure_ascii=False) + "\n")
        return mapping
