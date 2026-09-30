"""Git PR diff analyzer that detects potential invariant violations."""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import List, Optional, Set

from capsule_cli.ci import InvariantAlert
from services.parser.parser import CapsuleParser


class PRDiffChecker:
    """Detects modified files in PR / Git diff and intersects them with architectural capsules."""

    def __init__(self, parser: Optional[CapsuleParser] = None) -> None:
        self.parser = parser or CapsuleParser()

    def get_changed_files(
        self,
        base_ref: Optional[str] = None,
        repo_root: Optional[Path] = None,
    ) -> List[str]:
        """Fetch list of changed files between base_ref and current HEAD."""
        root = repo_root or Path.cwd()

        def _run_git(args: List[str]) -> Optional[str]:
            try:
                res = subprocess.run(
                    ["git", "-C", str(root)] + args,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if res.returncode == 0:
                    return res.stdout.strip()
            except Exception:
                pass
            return None

        # If base_ref not provided, attempt to auto-detect
        target_base = base_ref
        if not target_base:
            for candidate in ["origin/main", "origin/dev", "main", "dev", "HEAD~1"]:
                if _run_git(["rev-parse", "--verify", candidate]) is not None:
                    target_base = candidate
                    break

        changed: Set[str] = set()
        if target_base:
            out = _run_git(["diff", "--name-only", f"{target_base}...HEAD"])
            if out is None:
                # Try two-dot diff
                out = _run_git(["diff", "--name-only", target_base])
            if out:
                for line in out.splitlines():
                    if line.strip():
                        changed.add(line.strip())

        # Also check uncommitted/staged files in working directory
        status_out = _run_git(["status", "--porcelain"])
        if status_out:
            for line in status_out.splitlines():
                if len(line) > 3:
                    file_path = line[3:].strip()
                    # Handle renames e.g. "old -> new"
                    if " -> " in file_path:
                        file_path = file_path.split(" -> ")[-1].strip()
                    if file_path:
                        changed.add(file_path)

        return sorted(changed)

    def check_invariants(
        self,
        changed_files: List[str],
        capsules_dir: Path,
        confidence_threshold: Optional[str] = None,
    ) -> List[InvariantAlert]:
        """Intersect modified files with capsules to detect affected architectural invariants."""
        if not changed_files or not capsules_dir.exists():
            return []

        alerts: List[InvariantAlert] = []
        seen_keys: Set[str] = set()

        # Parse all capsules in capsules_dir
        capsule_files = list(capsules_dir.glob("**/*.caps.md")) + list(capsules_dir.glob("**/*.capsule.md")) + list(capsules_dir.glob("**/*.md"))
        
        # Pre-process changed file stems and directories
        changed_info = []
        for cf in changed_files:
            p = Path(cf)
            stems = {p.stem.lower(), p.name.lower()}
            parts = {part.lower() for part in p.parts}
            changed_info.append((cf, stems, parts))

        for cap_path in capsule_files:
            if any(part.startswith(".") for part in cap_path.parts if part != "."):
                continue

            try:
                parsed = self.parser.parse_file(cap_path)
            except Exception:
                continue

            # Confidence filtering: if high confidence requested or by default
            if confidence_threshold and parsed.confidence != confidence_threshold:
                continue

            cap_tags = {t.lower() for t in parsed.tags}
            cap_topic = parsed.topic.lower()
            referenced_file = str(parsed.raw_frontmatter.get("file_path") or "").lower()

            for cf, stems, parts in changed_info:
                cf_lower = cf.lower()
                match_type = None
                summary = ""

                # 1. Direct file path match
                if referenced_file and (referenced_file in cf_lower or cf_lower in referenced_file):
                    match_type = "direct_path"
                    summary = f"Explicitly references file '{cf}'"
                # 2. Tag match on path elements or stem
                elif cap_tags and (cap_tags & stems or cap_tags & parts):
                    matching_tags = list((cap_tags & stems) | (cap_tags & parts))
                    match_type = "tag_match"
                    summary = f"Tags {matching_tags} match modified path '{cf}'"
                # 3. Topic keyword match
                elif any(s in cap_topic for s in stems if len(s) > 3):
                    match_type = "topic_match"
                    summary = f"Topic mentions keyword from '{cf}'"

                if match_type:
                    dedup_key = f"{parsed.id or cap_path.name}:{cf}"
                    if dedup_key not in seen_keys:
                        seen_keys.add(dedup_key)
                        alerts.append(
                            InvariantAlert(
                                capsule_id=parsed.id,
                                capsule_topic=parsed.topic,
                                capsule_file=str(cap_path.resolve()),
                                confidence=parsed.confidence,
                                affected_file=cf,
                                match_type=match_type,
                                summary=summary,
                            )
                        )

        return alerts
