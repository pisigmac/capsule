"""LLM-assisted semantic decomposition for atomic knowledge extraction."""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

from .ast_splitter import AstDocumentSplitter, AtomicUnit, slugify_tag

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an expert technical knowledge extractor for the Capsule atomic memory system.
Your job is to read the provided documentation and decompose it into a list of atomic, self-contained knowledge units ("capsules").

Guidelines:
1. One Fact / Rule Per Capsule: Each capsule must express a single specific invariant, architectural rule, configuration detail, or operational procedure.
2. Self-Contained: The content must NOT use ambiguous pronouns (like "it", "they", "this system") without explicit referents. Anyone reading this capsule in isolation must fully understand it.
3. Topic: A crisp, descriptive title (between 3 and 100 characters).
4. Content: The detailed body of the fact (at least 15 characters).
5. Tags: 2 to 5 relevant lowercase categorical tags.
6. Confidence: "high" or "medium".

Return a valid JSON array of objects conforming to:
[
  {
    "topic": "Crisp title",
    "content": "Detailed self-contained proposition",
    "tags": ["tag1", "tag2"],
    "confidence": "high"
  }
]
"""


class LlmDocumentSplitter:
    """Uses LLM structured generation to extract atomic units, falling back to AST splitter."""

    def __init__(
        self,
        model: str = "gemini-2.5-flash",
        confidence: str = "high",
        extra_tags: Optional[List[str]] = None,
    ) -> None:
        self.model = model
        self.confidence = confidence
        self.extra_tags = extra_tags or []
        self._ast_fallback = AstDocumentSplitter(confidence=confidence, extra_tags=extra_tags)

    def split_document(
        self,
        text: str,
        source_name: str = "",
        extra_tags: Optional[List[str]] = None,
    ) -> List[AtomicUnit]:
        """Extract atomic units using an LLM provider, or fallback to AST splitting."""
        # 1. Try Gemini GenAI API
        if os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"):
            try:
                units = self._extract_with_gemini(text, source_name=source_name, extra_tags=extra_tags)
                if units:
                    return units
            except Exception as exc:
                logger.warning("Gemini extraction failed (%s); falling back to AST splitter.", exc)

        # 2. Try OpenAI API
        if os.getenv("OPENAI_API_KEY"):
            try:
                units = self._extract_with_openai(text, source_name=source_name, extra_tags=extra_tags)
                if units:
                    return units
            except Exception as exc:
                logger.warning("OpenAI extraction failed (%s); falling back to AST splitter.", exc)

        # 3. Fallback to AST
        logger.info("Using offline AST splitter for %s", source_name or "document")
        return self._ast_fallback.split_document(text, source_name=source_name, extra_tags=extra_tags)

    def _extract_with_gemini(
        self, text: str, source_name: str, extra_tags: Optional[List[str]]
    ) -> List[AtomicUnit]:
        """Extract units via google.genai or google.generativeai."""
        try:
            from google import genai
            from google.genai import types

            client = genai.Client()
            response = client.models.generate_content(
                model=self.model,
                contents=f"Document text:\n\n{text[:15000]}",
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    response_mime_type="application/json",
                    temperature=0.2,
                ),
            )
            raw_json = response.text
        except Exception:
            # Try google.generativeai legacy package
            import google.generativeai as gai

            gai.configure(api_key=os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))
            gmodel = gai.GenerativeModel(self.model, system_instruction=SYSTEM_PROMPT)
            resp = gmodel.generate_content(
                f"Document text:\n\n{text[:15000]}",
                generation_config={"response_mime_type": "application/json", "temperature": 0.2},
            )
            raw_json = resp.text

        return self._parse_json_response(raw_json, source_name=source_name, extra_tags=extra_tags)

    def _extract_with_openai(
        self, text: str, source_name: str, extra_tags: Optional[List[str]]
    ) -> List[AtomicUnit]:
        """Extract units via OpenAI chat completion."""
        from openai import OpenAI

        client = OpenAI()
        model_name = self.model if "gpt" in self.model else "gpt-4o-mini"
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Document text:\n\n{text[:15000]}"},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        raw_json = response.choices[0].message.content or "[]"
        return self._parse_json_response(raw_json, source_name=source_name, extra_tags=extra_tags)

    def _parse_json_response(
        self, raw_json: str, source_name: str, extra_tags: Optional[List[str]]
    ) -> List[AtomicUnit]:
        """Parse model JSON array into validated AtomicUnit objects."""
        data = json.loads(raw_json.strip())
        if isinstance(data, dict):
            # If wrapped in a top-level key like {"capsules": [...]}
            for v in data.values():
                if isinstance(v, list):
                    data = v
                    break

        if not isinstance(data, list):
            return []

        base_tags = [slugify_tag(t) for t in (extra_tags or self.extra_tags) if slugify_tag(t)]
        units: List[AtomicUnit] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            topic = str(item.get("topic") or "").strip()
            content = str(item.get("content") or "").strip()
            if len(topic) < 3 or len(content) < 10:
                continue

            tags = [slugify_tag(str(t)) for t in item.get("tags") or [] if slugify_tag(str(t))]
            tags.extend(base_tags)
            clean_tags = sorted(set(tags))[:20]

            conf = item.get("confidence") or self.confidence
            if conf not in ("high", "medium", "low", "hearsay"):
                conf = self.confidence

            units.append(
                AtomicUnit(
                    topic=topic,
                    content=content,
                    tags=clean_tags,
                    confidence=conf,
                    source=source_name,
                )
            )

        return units
