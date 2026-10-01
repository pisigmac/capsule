"""Git commit and merged PR harvester for extracting architectural invariants."""
from __future__ import annotations

import logging
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

from services.ingest.ast_splitter import AtomicUnit
from services.ingest.decomposer import IngestResult
from services.shared.models import Capsule
from services.store.store import CapsuleStore, content_hash

logger = logging.getLogger("capsule.ingest.git")

KEYWORD_SIGNALS = {
    "workaround",
    "override",
    "invariant",
    "security",
    "concurrency",
    "deadlock",
    "breaking change",
    "policy",
    "regression",
    "must not",
    "always",
    "never",
    "limit",
    "pool",
    "exhaustion",
    "bypass",
    "deprecated",
    "migration",
    "failover",
    "race condition",
    "auth",
    "token",
    "leak",
    "lock",
    "thread",
    "timeout",
}

IGNORED_PREFIXES = (
    "chore",
    "style",
    "build",
    "ci",
    "test",
    "bump",
    "version",
    "release",
    "merge",
    "update readme",
    "format",
    "lint",
    "typo",
)

CONVENTIONAL_RE = re.compile(
    r"^(feat|fix|refactor|perf|docs|sec|security)(?:\(([a-zA-Z0-9_\-\/\.]+)\))?!?: (.+)$",
    re.IGNORECASE,
)


@dataclass
class GitHarvestItem:
    """A candidate architectural invariant extracted from a git commit or PR."""

    sha: str
    short_sha: str
    date: str
    author: str
    subject: str
    body: str
    commit_type: Optional[str] = None
    scope: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    topic: str = ""
    content: str = ""
    confidence: str = "high"
    source: str = ""

    def to_atomic_unit(self) -> AtomicUnit:
        return AtomicUnit(
            topic=self.topic,
            content=self.content,
            tags=self.tags,
            confidence=self.confidence,
            source=self.source,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sha": self.sha,
            "short_sha": self.short_sha,
            "date": self.date,
            "author": self.author,
            "subject": self.subject,
            "topic": self.topic,
            "content": self.content,
            "tags": self.tags,
            "confidence": self.confidence,
            "source": self.source,
        }


class GitHarvester:
    """Scans repository git history to discover architectural decisions and bug fix rationale."""

    def __init__(self, parser=None) -> None:
        pass

    def run_git(self, repo_path: Path, args: List[str]) -> Optional[str]:
        try:
            res = subprocess.run(
                ["git", "-C", str(repo_path)] + args,
                capture_output=True,
                text=True,
                check=False,
            )
            if res.returncode == 0:
                return res.stdout
        except Exception as e:
            logger.warning("Git command failed in %s: %s", repo_path, e)
        return None

    def extract_candidates(
        self,
        repo_path: Path,
        depth: int = 50,
        types: Optional[List[str]] = None,
        since: Optional[str] = None,
        default_confidence: str = "high",
        extra_tags: Optional[List[str]] = None,
    ) -> List[GitHarvestItem]:
        """Extract and filter candidate commits from git log."""
        git_args = [
            "log",
            f"-n{depth}",
            "--format=%H|%ad|%an|%s%n%b%n--END_COMMIT--",
            "--date=iso-strict",
        ]
        if since:
            git_args.append(f"--since={since}")

        raw_log = self.run_git(repo_path, git_args)
        if not raw_log:
            return []

        raw_blocks = raw_log.split("--END_COMMIT--")
        candidates: List[GitHarvestItem] = []
        filter_types = {t.lower().strip() for t in types} if types else None

        for block in raw_blocks:
            lines = block.strip().splitlines()
            if not lines:
                continue

            header = lines[0]
            header_parts = header.split("|", 3)
            if len(header_parts) < 4:
                continue

            sha, date_str, author, subject = header_parts
            body_lines = lines[1:] if len(lines) > 1 else []
            # Strip trailers like Signed-off-by, Co-authored-by
            cleaned_body_lines = [
                line
                for line in body_lines
                if not re.match(r"^(signed-off-by|co-authored-by|see:|fixes:|ref:)", line, re.IGNORECASE)
            ]
            body_text = "\n".join(cleaned_body_lines).strip()

            short_sha = sha[:8]
            subject_clean = subject.strip()

            conv_match = CONVENTIONAL_RE.match(subject_clean)
            commit_type: Optional[str] = None
            scope: Optional[str] = None
            topic_subject = subject_clean

            if conv_match:
                commit_type = conv_match.group(1).lower()
                scope = conv_match.group(2).lower() if conv_match.group(2) else None
                topic_subject = conv_match.group(3).strip()

            # Filter by explicit types if requested
            if filter_types:
                if not commit_type or commit_type not in filter_types:
                    continue
            else:
                # If no explicit types, skip ignored trivial prefixes unless keywords present
                is_ignored = any(subject_clean.lower().startswith(p) for p in IGNORED_PREFIXES)
                has_keywords = any(k in subject_clean.lower() or k in body_text.lower() for k in KEYWORD_SIGNALS)
                if is_ignored and not has_keywords:
                    continue

                # If not conventional and has no keyword signals, skip generic noise
                if not conv_match and not has_keywords:
                    continue

            # Determine tags
            tags_set: Set[str] = {"git"}
            if scope:
                for sc in scope.replace("/", ",").split(","):
                    if sc.strip():
                        tags_set.add(sc.strip().lower())
            if commit_type:
                tags_set.add(commit_type)

            for kw in KEYWORD_SIGNALS:
                if kw in subject_clean.lower() or kw in body_text.lower():
                    # Add clean singular tag if single word
                    clean_kw = kw.replace(" ", "-")
                    tags_set.add(clean_kw)

            if extra_tags:
                for et in extra_tags:
                    if et.strip():
                        tags_set.add(et.strip().lower())

            # Format topic
            topic = topic_subject
            # Capitalize first character
            if topic:
                topic = topic[0].upper() + topic[1:]
            if len(topic) < 5:
                topic = f"Git Insight: {subject_clean}"
            if len(topic) > 100:
                topic = topic[:97] + "..."

            # Format content
            content_parts = []
            if body_text and len(body_text) >= 15:
                content_parts.append(body_text)
            else:
                content_parts.append(f"Architectural decision and rationale from git commit `{short_sha}`:")
                content_parts.append(f"> {subject_clean}")

            content_text = "\n\n".join(content_parts).strip()
            if len(content_text) < 15:
                content_text = f"{content_text}\n\nCommit `{short_sha}` authored by {author}."

            source = f"git:{short_sha}"

            candidates.append(
                GitHarvestItem(
                    sha=sha,
                    short_sha=short_sha,
                    date=date_str,
                    author=author,
                    subject=subject_clean,
                    body=body_text,
                    commit_type=commit_type,
                    scope=scope,
                    tags=sorted(tags_set),
                    topic=topic,
                    content=content_text,
                    confidence=default_confidence,
                    source=source,
                )
            )

        return candidates

    def harvest(
        self,
        repo_path: Path,
        store: CapsuleStore,
        depth: int = 50,
        types: Optional[List[str]] = None,
        since: Optional[str] = None,
        default_confidence: str = "high",
        dry_run: bool = False,
        extra_tags: Optional[List[str]] = None,
        on_progress: Optional[Callable[[GitHarvestItem, bool, bool], None]] = None,
    ) -> IngestResult:
        """Harvest git history and ingest discovered items into CapsuleStore."""
        candidates = self.extract_candidates(
            repo_path=repo_path,
            depth=depth,
            types=types,
            since=since,
            default_confidence=default_confidence,
            extra_tags=extra_tags,
        )

        result = IngestResult(
            total_files=1,
            total_units=len(candidates),
            units=[c.to_atomic_unit() for c in candidates],
        )

        seen_digests: Set[str] = set()

        for item in candidates:
            body_hash = content_hash(item.topic, item.content)
            is_duplicate = body_hash in seen_digests

            if dry_run:
                if on_progress:
                    on_progress(item, False, is_duplicate)
                seen_digests.add(body_hash)
                continue

            try:
                cap = store.create(
                    topic=item.topic,
                    content=item.content,
                    tags=item.tags,
                    source=item.source,
                    confidence=item.confidence,
                )
                if getattr(cap, "deduped", False) or is_duplicate:
                    result.deduped_count += 1
                    result.deduped.append(cap)
                    if on_progress:
                        on_progress(item, False, True)
                else:
                    result.created_count += 1
                    result.created.append(cap)
                    if on_progress:
                        on_progress(item, True, False)

                seen_digests.add(body_hash)
            except Exception as exc:
                logger.error("Failed to store harvested capsule from %s: %s", item.short_sha, exc)

        return result
