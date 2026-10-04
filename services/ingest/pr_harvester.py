"""Merged PR harvester for extracting architectural invariants from GitHub PRs."""
from __future__ import annotations

import json
import logging
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional

from services.ingest.git_harvester import GitHarvestItem, KEYWORD_SIGNALS

logger = logging.getLogger("capsule.ingest.pr")


class PRHarvester:
    """Extracts architectural rationale and decisions from merged pull requests."""

    def __init__(self) -> None:
        self.gh_cli_path = shutil.which("gh")

    def is_gh_available(self) -> bool:
        return self.gh_cli_path is not None

    def extract_merged_prs(
        self,
        repo_path: Path,
        limit: int = 30,
        default_confidence: str = "high",
        extra_tags: Optional[List[str]] = None,
    ) -> List[GitHarvestItem]:
        """Fetch merged PRs using GitHub CLI (`gh pr list --state merged`)."""
        if not self.is_gh_available():
            logger.info("GitHub CLI (`gh`) not installed; skipping remote PR API extraction")
            return []

        try:
            cmd = [
                "gh",
                "pr",
                "list",
                "--state",
                "merged",
                "--limit",
                str(limit),
                "--json",
                "number,title,body,author,mergedAt,labels",
            ]
            res = subprocess.run(cmd, cwd=str(repo_path), capture_output=True, text=True, check=False)
            if res.returncode != 0:
                logger.warning("gh pr list failed: %s", res.stderr)
                return []

            data = json.loads(res.stdout)
            candidates: List[GitHarvestItem] = []

            for pr in data:
                number = pr.get("number")
                title = (pr.get("title") or "").strip()
                body = (pr.get("body") or "").strip()
                author_obj = pr.get("author") or {}
                author_login = author_obj.get("login", "unknown")
                merged_at = pr.get("mergedAt", "")
                labels = [label.get("name") for label in pr.get("labels", []) if isinstance(label, dict)]

                if not title:
                    continue

                # Filter trivial PRs
                combined = f"{title}\n{body}".lower()
                has_keywords = any(kw in combined for kw in KEYWORD_SIGNALS)
                is_semantic = any(title.lower().startswith(p) for p in ["feat", "fix", "refactor", "perf", "sec"])

                if not has_keywords and not is_semantic:
                    continue

                tags_set = {"git", "pr"}
                for label in labels:
                    if label:
                        tags_set.add(label.lower().replace(" ", "-"))

                for kw in KEYWORD_SIGNALS:
                    if kw in combined:
                        tags_set.add(kw.replace(" ", "-"))

                if extra_tags:
                    for et in extra_tags:
                        tags_set.add(et.lower().strip())

                content_parts = []
                if body and len(body) >= 20:
                    content_parts.append(body)
                else:
                    content_parts.append(f"Architectural decision from merged Pull Request #{number}:")
                    content_parts.append(f"> {title}")

                content_text = "\n\n".join(content_parts).strip()
                source = f"pr:#{number}"

                candidates.append(
                    GitHarvestItem(
                        sha=f"pr-{number}",
                        short_sha=f"PR#{number}",
                        date=merged_at,
                        author=author_login,
                        subject=title,
                        body=body,
                        tags=sorted(tags_set),
                        topic=title[:100],
                        content=content_text,
                        confidence=default_confidence,
                        source=source,
                    )
                )

            return candidates
        except Exception as e:
            logger.warning("Error harvesting PRs: %s", e)
            return []
