from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader


TERMS = (
    "four tasks",
    "OARS",
    "change talk",
    "sustain talk",
    "discord",
    "righting reflex",
    "advice",
)


def main() -> int:
    pdf = Path("/Users/andyyin/Downloads/Motivational_Interviewing_4thEd.pdf")
    reader = PdfReader(str(pdf))
    print(f"pages: {len(reader.pages)}")
    for term in TERMS:
        print(f"\n## {term}")
        hits = 0
        for index, page in enumerate(reader.pages):
            text = " ".join((page.extract_text() or "").split())
            position = text.lower().find(term.lower())
            if position == -1:
                continue
            start = max(0, position - 180)
            end = min(len(text), position + 260)
            print(f"page {index + 1}: {text[start:end]}")
            hits += 1
            if hits == 2:
                break
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
