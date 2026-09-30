"""Zero-dependency markdown AST and heading boundary splitter for atomic knowledge extraction."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import yaml


@dataclass
class AtomicUnit:
    """A self-contained candidate knowledge capsule extracted from a document."""

    topic: str
    content: str
    tags: List[str] = field(default_factory=list)
    confidence: str = "high"
    source: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "topic": self.topic,
            "content": self.content,
            "tags": self.tags,
            "confidence": self.confidence,
            "source": self.source,
        }


# Stopwords to filter from tag generation
STOPWORDS: Set[str] = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and",
    "any", "are", "aren't", "as", "at", "be", "because", "been", "before", "being",
    "below", "between", "both", "but", "by", "can", "can't", "cannot", "could",
    "couldn't", "did", "didn't", "do", "does", "doesn't", "doing", "don't", "down",
    "during", "each", "few", "for", "from", "further", "had", "hadn't", "has",
    "hasn't", "have", "haven't", "having", "he", "he'd", "he'll", "he's", "her",
    "here", "here's", "hers", "herself", "him", "himself", "his", "how", "how's",
    "i", "i'd", "i'll", "i'm", "i've", "if", "in", "into", "is", "isn't", "it",
    "it's", "its", "itself", "let's", "me", "more", "most", "mustn't", "my",
    "myself", "no", "nor", "not", "of", "off", "on", "once", "only", "or",
    "other", "ought", "our", "ours", "ourselves", "out", "over", "own", "same",
    "shan't", "she", "she'd", "she'll", "she's", "should", "shouldn't", "so",
    "some", "such", "than", "that", "that's", "the", "their", "theirs", "them",
    "themselves", "then", "there", "there's", "these", "they", "they'd", "they'll",
    "they're", "they've", "this", "those", "through", "to", "too", "under", "until",
    "up", "very", "was", "wasn't", "we", "we'd", "we'll", "we're", "we've", "were",
    "weren't", "what", "what's", "when", "when's", "where", "where's", "which",
    "while", "who", "who's", "whom", "why", "why's", "with", "won't", "would",
    "wouldn't", "you", "you'd", "you'll", "you're", "you've", "your", "yours",
    "yourself", "yourselves",
}

HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$")
LINK_RE = re.compile(r"\[([^\]]+)\]\([^\)]+\)")
EMOJI_SYMBOLS_RE = re.compile(r"^[^\w\s#]+|[\s]+[^\w\s#]+$")
TAG_SLUG_RE = re.compile(r"[^a-z0-9\-]+")


def clean_topic_title(raw: str) -> str:
    """Normalize a markdown heading into a crisp, readable topic string."""
    title = raw.strip()
    # Strip trailing hashes (e.g. ## Title ##)
    title = re.sub(r"\s*#+\s*$", "", title)
    # Convert markdown links [Link Text](url) -> Link Text
    title = LINK_RE.sub(r"\1", title)
    # Strip markdown emphasis (**bold**, *italic*, `code`)
    title = re.sub(r"[*_`]", "", title)
    # Strip decorative leading emoji/symbols
    title = EMOJI_SYMBOLS_RE.sub("", title).strip()
    return title


def slugify_tag(val: str) -> str:
    """Convert an arbitrary string into a canonical lowercase tag slug."""
    slug = TAG_SLUG_RE.sub("-", val.lower().strip()).strip("-")
    return slug[:50]


def extract_tags_from_text(text: str) -> List[str]:
    """Extract candidate tags from text tokens and hashtags."""
    tags: Set[str] = set()
    # Check for #hashtags
    for match in re.finditer(r"#([a-zA-Z0-9_\-]+)", text):
        tag = slugify_tag(match.group(1))
        if len(tag) >= 2 and tag not in STOPWORDS:
            tags.add(tag)

    # Check for slug candidates
    words = re.findall(r"[A-Za-z0-9]{3,}", text)
    for word in words:
        clean = slugify_tag(word)
        if len(clean) >= 3 and clean not in STOPWORDS:
            tags.add(clean)

    return sorted(tags)[:10]


def is_toc_content(topic: str, content: str) -> bool:
    """Check if a section is just a Table of Contents or list of anchor links."""
    topic_lower = topic.lower()
    if re.search(r"\b(table of contents|toc|contents|quick[- ]links)\b", topic_lower):
        return True

    lines = [line.strip() for line in content.splitlines() if line.strip()]
    if not lines:
        return False

    link_lines = 0
    for line in lines:
        # Check if line is a bulleted markdown link: - [Title](#anchor) or * [Title](url)
        if re.match(r"^[-*+]\s+\[.*?\]\(.*?\)", line):
            link_lines += 1

    return link_lines > 0 and (link_lines / len(lines)) >= 0.7



class AstDocumentSplitter:
    """Decomposes markdown documents into atomic units based on heading AST boundaries."""

    def __init__(self, confidence: str = "high", extra_tags: Optional[List[str]] = None) -> None:
        self.confidence = confidence
        self.extra_tags = [slugify_tag(t) for t in (extra_tags or []) if slugify_tag(t)]

    def extract_frontmatter(self, text: str) -> Tuple[Dict[str, Any], str]:
        """Extract and parse YAML frontmatter from document if present."""
        if not text.startswith("---"):
            return {}, text

        lines = text.splitlines(keepends=True)
        if len(lines) < 2:
            return {}, text

        end_idx = -1
        for idx in range(1, len(lines)):
            if lines[idx].strip() == "---":
                end_idx = idx
                break

        if end_idx == -1:
            return {}, text

        fm_text = "".join(lines[1:end_idx])
        body_text = "".join(lines[end_idx + 1:])

        try:
            parsed = yaml.safe_load(fm_text) or {}
            if isinstance(parsed, dict):
                return parsed, body_text
        except Exception:
            pass

        return {}, text

    def split_document(
        self,
        text: str,
        source_name: str = "",
        extra_tags: Optional[List[str]] = None,
    ) -> List[AtomicUnit]:
        """Decompose markdown text into a sequence of atomic units."""
        frontmatter, body = self.extract_frontmatter(text)

        # Baseline tags from filename, frontmatter, and options
        base_tags: Set[str] = set(self.extra_tags)
        if extra_tags:
            for t in extra_tags:
                s = slugify_tag(t)
                if s:
                    base_tags.add(s)

        # File-based tags
        if source_name:
            stem = Path(source_name).stem.replace(".caps", "").replace(".capsule", "")
            for part in re.split(r"[-_.]+", stem):
                st = slugify_tag(part)
                if st and len(st) >= 3 and st not in STOPWORDS:
                    base_tags.add(st)

        # Frontmatter tags
        fm_tags = frontmatter.get("tags")
        if isinstance(fm_tags, list):
            for t in fm_tags:
                st = slugify_tag(str(t))
                if st and st not in STOPWORDS:
                    base_tags.add(st)
        elif isinstance(fm_tags, str):
            for t in fm_tags.split(","):
                st = slugify_tag(t)
                if st and st not in STOPWORDS:
                    base_tags.add(st)

        doc_title = str(frontmatter.get("title") or "").strip()

        # Parse sections along heading boundaries
        raw_sections = self._parse_sections(body, doc_title=doc_title)

        units: List[AtomicUnit] = []
        for sec_topic, sec_content, sec_ancestors in raw_sections:
            content_clean = sec_content.strip()
            # Enforce minimum lengths (CapsuleParser requires topic >= 3 chars, content >= 10 chars)
            if len(sec_topic) < 3 or len(content_clean) < 10:
                continue

            if is_toc_content(sec_topic, content_clean):
                continue

            # Section tags
            sec_tags = set(base_tags)
            for anc in sec_ancestors:
                tag = slugify_tag(anc)
                if tag and len(tag) >= 3 and tag not in STOPWORDS:
                    sec_tags.add(tag)
                for word in re.findall(r"[A-Za-z0-9]{3,}", anc):
                    w = slugify_tag(word)
                    if w and len(w) >= 3 and w not in STOPWORDS:
                        sec_tags.add(w)

            topic_tags = extract_tags_from_text(sec_topic)
            for tt in topic_tags:
                if tt not in STOPWORDS:
                    sec_tags.add(tt)


            final_tags = sorted(sec_tags)[:20]

            units.append(
                AtomicUnit(
                    topic=sec_topic,
                    content=content_clean,
                    tags=final_tags,
                    confidence=self.confidence,
                    source=source_name,
                )
            )

        return units

    def _parse_sections(
        self, body: str, doc_title: str = ""
    ) -> List[Tuple[str, str, List[str]]]:
        """Split text along markdown headings while preserving code blocks."""
        lines = body.splitlines()
        sections: List[Tuple[str, str, List[str]]] = []

        current_heading: Optional[str] = None
        current_lines: List[str] = []
        hierarchy_stack: List[Tuple[int, str]] = []

        in_code_block = False
        code_fence = ""

        lead_lines: List[str] = []
        first_heading_seen = False

        for line in lines:
            stripped = line.strip()

            # Track fenced code blocks (``` or ~~~)
            if stripped.startswith("```") or stripped.startswith("~~~"):
                fence_marker = stripped[:3]
                if not in_code_block:
                    in_code_block = True
                    code_fence = fence_marker
                elif fence_marker == code_fence:
                    in_code_block = False
                    code_fence = ""

                if not first_heading_seen:
                    lead_lines.append(line)
                else:
                    current_lines.append(line)
                continue

            if in_code_block:
                if not first_heading_seen:
                    lead_lines.append(line)
                else:
                    current_lines.append(line)
                continue

            # Heading check
            match = HEADING_RE.match(line)
            if match:
                level = len(match.group(1))
                raw_title = match.group(2)
                clean_title = clean_topic_title(raw_title)

                # Flush previous section
                if first_heading_seen and current_heading:
                    ancestors = [h[1] for h in hierarchy_stack[:-1]]
                    sections.append((current_heading, "\n".join(current_lines), ancestors))
                    current_lines = []
                elif not first_heading_seen and lead_lines:
                    lead_text = "\n".join(lead_lines).strip()
                    if len(lead_text) >= 10:
                        lead_topic = doc_title or clean_title or "Overview"
                        sections.append((lead_topic, lead_text, []))
                    lead_lines = []

                first_heading_seen = True

                # Update hierarchy stack
                while hierarchy_stack and hierarchy_stack[-1][0] >= level:
                    hierarchy_stack.pop()

                hierarchy_stack.append((level, clean_title))

                # Topic is the clean heading title
                composed_topic = clean_title
                current_heading = composed_topic
            else:
                if not first_heading_seen:
                    lead_lines.append(line)
                else:
                    current_lines.append(line)

        # Flush final section
        if first_heading_seen and current_heading and current_lines:
            ancestors = [h[1] for h in hierarchy_stack[:-1]]
            sections.append((current_heading, "\n".join(current_lines), ancestors))
        elif not first_heading_seen and lead_lines:
            lead_text = "\n".join(lead_lines).strip()
            if len(lead_text) >= 10:
                lead_topic = doc_title or "Overview"
                sections.append((lead_topic, lead_text, []))

        return sections
