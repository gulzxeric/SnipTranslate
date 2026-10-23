"""Small UI-independent value objects shared by OCR and translation."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Rect:
    x: float
    y: float
    width: float
    height: float


@dataclass(frozen=True, slots=True)
class TextBlock:
    text: str
    rect: Rect


@dataclass(slots=True)
class OcrResult:
    blocks: list[TextBlock]
    language: str
    width: int
    height: int

    @property
    def text(self) -> str:
        return "\n".join(block.text for block in self.blocks)


@dataclass(slots=True)
class TranslationResult:
    texts: list[str]
    detected_language: str = ""
