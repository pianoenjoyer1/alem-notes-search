"""Local, dependency-free TF-IDF retrieval over UTF-8 notes."""
import argparse
from collections import Counter
from dataclasses import dataclass
import json
import math
from pathlib import Path
import re
import unicodedata


def tokenize(text):
    text = unicodedata.normalize("NFKC", text).casefold()
    return re.findall(r"[^\W_]+", text, flags=re.UNICODE)


@dataclass(frozen=True)
class Passage:
    source: str
    line: int
    text: str


def read_passages(folder):
    root = Path(folder).resolve()
    if not root.is_dir():
        raise ValueError("Notes directory does not exist: {}".format(folder))
    passages = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in {".md", ".txt"}:
            continue
        # Do not index a symlink leading outside the explicitly selected folder.
        try:
            path.resolve().relative_to(root)
        except ValueError:
            continue
        lines = path.read_text(encoding="utf-8-sig").splitlines()
        current, start = [], 1
        for number, line in enumerate(lines + [""], 1):
            if line.strip():
                if not current:
                    start = number
                current.append(line.strip())
            if current and (not line.strip() or len(current) >= 12):
                passages.append(Passage(path.relative_to(root).as_posix(), start, " ".join(current)))
                current = []
    return passages


class SearchIndex:
    def __init__(self, passages):
        self.passages = list(passages)
        counts = [Counter(tokenize(p.text)) for p in self.passages]
        frequency = Counter(word for count in counts for word in count)
        self.idf = {word: math.log((1 + len(counts)) / (1 + n)) + 1
                    for word, n in frequency.items()}
        self.vectors = [self.vector(count) for count in counts]

    def vector(self, counts):
        weighted = {word: (1 + math.log(n)) * self.idf[word]
                    for word, n in counts.items() if word in self.idf}
        length = math.sqrt(sum(n * n for n in weighted.values()))
        return {word: n / length for word, n in weighted.items()} if length else {}

    def search(self, query, limit=5):
        if not 1 <= limit <= 50:
            raise ValueError("limit must be between 1 and 50")
        if len(query) > 1000:
            raise ValueError("query must be at most 1000 characters")
        vector = self.vector(Counter(tokenize(query)))
        hits = []
        for passage, candidate in zip(self.passages, self.vectors):
            score = sum(weight * candidate.get(word, 0) for word, weight in vector.items())
            if score > 0:
                hits.append({"source": passage.source, "line": passage.line,
                             "text": passage.text, "score": round(score, 6)})
        return sorted(hits, key=lambda h: (-h["score"], h["source"], h["line"]))[:limit]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    parser.add_argument("query")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        hits = SearchIndex(read_passages(args.folder)).search(args.query, args.limit)
    except (OSError, UnicodeError, ValueError) as error:
        parser.error(str(error))
    if args.json:
        print(json.dumps(hits, ensure_ascii=False, indent=2))
    elif not hits:
        print("No matching passages. Try words used in your notes.")
    else:
        for hit in hits:
            print("{source}:{line}  score={score:.3f}\n{text}\n".format(**hit))


if __name__ == "__main__":
    main()
