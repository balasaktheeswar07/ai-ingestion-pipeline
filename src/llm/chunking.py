from dataclasses import dataclass


@dataclass(frozen=True)
class TextChunk:
    text: str
    index: int


def chunk_text(text: str, *, max_chars: int = 12000, title: str = "", metadata: str = "") -> list[TextChunk]:
    if max_chars < 100:
        raise ValueError("max_chars must be at least 100")
    prefix = "\n".join(part for part in (title, metadata) if part).strip()
    usable = max_chars - len(prefix) - (2 if prefix else 0)
    if usable < 1:
        raise ValueError("metadata exceeds max_chars")
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[TextChunk] = []
    current = ""
    for paragraph in paragraphs or [text]:
        while paragraph:
            candidate = f"{current}\n\n{paragraph}".strip()
            if len(candidate) <= usable:
                current = candidate
                break
            if current:
                chunks.append(TextChunk(f"{prefix}\n\n{current}".strip(), len(chunks)))
                current = ""
            else:
                chunks.append(TextChunk(f"{prefix}\n\n{paragraph[:usable]}".strip(), len(chunks)))
                paragraph = paragraph[usable:]
    if current:
        chunks.append(TextChunk(f"{prefix}\n\n{current}".strip(), len(chunks)))
    return chunks
