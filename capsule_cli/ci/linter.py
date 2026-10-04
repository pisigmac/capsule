"""Vault and capsule schema linter for CI pipelines."""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from uuid import UUID

import yaml

from capsule_cli.ci import LintIssue, LintReport
from services.parser.parser import CONFIDENCE_LEVELS


class CapsuleLinter:
    """Linter that verifies schema integrity, frontmatter syntax, and link validity."""

    CONFIDENCE_LEVELS = CONFIDENCE_LEVELS

    def __init__(self) -> None:
        self.frontmatter_pattern = re.compile(r"^---\s*\n(.*?)^---\s*\n", re.MULTILINE | re.DOTALL)

    def lint_file_content(self, text: str, file_path: str = "inline.caps.md") -> Tuple[List[LintIssue], Optional[Dict[str, Any]], str]:
        """Lint a single capsule's raw content. Returns (issues, frontmatter_dict, body_content)."""
        issues: List[LintIssue] = []
        fm_match = self.frontmatter_pattern.match(text)
        frontmatter: Dict[str, Any] = {}
        body = text

        if not fm_match:
            issues.append(
                LintIssue(
                    file_path=file_path,
                    rule="schema/missing-frontmatter",
                    message="Missing YAML frontmatter delimited by '---'",
                    level="warning",
                    line_number=1,
                )
            )
            # Try to extract topic from first H1 or first line
            topic = body.split("\n")[0][:100] if body else ""
        else:
            fm_text = fm_match.group(1)
            try:
                loaded = yaml.safe_load(fm_text)
                if loaded is None:
                    frontmatter = {}
                elif not isinstance(loaded, dict):
                    issues.append(
                        LintIssue(
                            file_path=file_path,
                            rule="schema/invalid-frontmatter-type",
                            message="YAML frontmatter must be a key-value mapping",
                            level="error",
                            line_number=1,
                        )
                    )
                else:
                    frontmatter = loaded
            except yaml.MarkedYAMLError as exc:
                line_no = exc.problem_mark.line + 1 if exc.problem_mark else 1
                issues.append(
                    LintIssue(
                        file_path=file_path,
                        rule="schema/yaml-syntax",
                        message=f"YAML syntax error: {exc.problem}",
                        level="error",
                        line_number=line_no,
                    )
                )
            except yaml.YAMLError as exc:
                issues.append(
                    LintIssue(
                        file_path=file_path,
                        rule="schema/yaml-syntax",
                        message=f"YAML parse error: {exc}",
                        level="error",
                        line_number=1,
                    )
                )
            body = text[fm_match.end() :].strip()

        # Validate Topic
        topic = frontmatter.get("topic")
        if topic is None:
            # Fallback check from body
            h1_match = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
            if h1_match:
                topic = h1_match.group(1).strip()
            else:
                issues.append(
                    LintIssue(
                        file_path=file_path,
                        rule="schema/missing-topic",
                        message="Missing 'topic' field in frontmatter",
                        level="error",
                    )
                )
                topic = ""
        else:
            topic = str(topic).strip()

        if topic and len(topic) < 3:
            issues.append(
                LintIssue(
                    file_path=file_path,
                    rule="schema/topic-too-short",
                    message=f"Topic is too short ({len(topic)} chars). Minimum 3 characters required.",
                    level="error",
                )
            )
        elif topic and len(topic) > 120:
            issues.append(
                LintIssue(
                    file_path=file_path,
                    rule="schema/topic-too-long",
                    message=f"Topic is very long ({len(topic)} chars). Recommended max 120 characters.",
                    level="warning",
                )
            )

        # Validate Content
        if not body or len(body.strip()) < 10:
            issues.append(
                LintIssue(
                    file_path=file_path,
                    rule="schema/content-too-short",
                    message=f"Content body is too short ({len(body.strip())} chars). Minimum 10 characters required.",
                    level="error",
                )
            )

        # Validate Confidence
        if "confidence" in frontmatter:
            conf = str(frontmatter["confidence"]).lower()
            if conf not in self.CONFIDENCE_LEVELS:
                issues.append(
                    LintIssue(
                        file_path=file_path,
                        rule="schema/invalid-confidence",
                        message=f"Invalid confidence '{conf}'. Must be one of: {sorted(self.CONFIDENCE_LEVELS)}",
                        level="error",
                    )
                )

        # Validate Tags
        if "tags" in frontmatter:
            tags = frontmatter["tags"]
            if not isinstance(tags, (list, tuple)):
                issues.append(
                    LintIssue(
                        file_path=file_path,
                        rule="schema/invalid-tags-type",
                        message="Field 'tags' must be a list of strings",
                        level="error",
                    )
                )
            else:
                seen_tags: Set[str] = set()
                for tag in tags:
                    if not isinstance(tag, str) or not tag.strip():
                        issues.append(
                            LintIssue(
                                file_path=file_path,
                                rule="schema/invalid-tag-item",
                                message=f"Tag element must be a non-empty string, got {tag!r}",
                                level="error",
                            )
                        )
                    else:
                        normalized = tag.lower().strip()
                        if normalized in seen_tags:
                            issues.append(
                                LintIssue(
                                    file_path=file_path,
                                    rule="schema/duplicate-tag",
                                    message=f"Duplicate tag '{tag}' in frontmatter",
                                    level="warning",
                                )
                            )
                        seen_tags.add(normalized)

        # Validate ID
        if "id" in frontmatter and frontmatter["id"]:
            try:
                UUID(str(frontmatter["id"]))
            except (ValueError, TypeError, AttributeError):
                issues.append(
                    LintIssue(
                        file_path=file_path,
                        rule="schema/invalid-id",
                        message=f"Invalid UUID in 'id' field: {frontmatter['id']!r}",
                        level="error",
                    )
                )
        else:
            issues.append(
                LintIssue(
                    file_path=file_path,
                    rule="schema/missing-id",
                    message="Capsule has no explicit UUID 'id' in frontmatter",
                    level="warning",
                )
            )

        # Validate Freshness Date
        if "freshness" in frontmatter and frontmatter["freshness"]:
            freshness_val = frontmatter["freshness"]
            if not isinstance(freshness_val, datetime):
                try:
                    datetime.fromisoformat(str(freshness_val).replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    issues.append(
                        LintIssue(
                            file_path=file_path,
                            rule="schema/invalid-freshness",
                            message=f"Invalid ISO 8601 date in 'freshness': {freshness_val!r}",
                            level="warning",
                        )
                    )

        # Validate Relationships Structure
        if "relationships" in frontmatter and frontmatter["relationships"]:
            rels = frontmatter["relationships"]
            if not isinstance(rels, list):
                issues.append(
                    LintIssue(
                        file_path=file_path,
                        rule="schema/invalid-relationships-type",
                        message="Field 'relationships' must be a list of mapping entries or UUID strings",
                        level="error",
                    )
                )
            else:
                for idx, rel in enumerate(rels):
                    target = None
                    if isinstance(rel, str):
                        target = rel
                    elif isinstance(rel, dict):
                        target = rel.get("to") or rel.get("id") or rel.get("to_id")
                    else:
                        issues.append(
                            LintIssue(
                                file_path=file_path,
                                rule="schema/invalid-relationship-item",
                                message=f"Relationship at index {idx} must be a dict or UUID string",
                                level="error",
                            )
                        )
                        continue

                    if target:
                        try:
                            UUID(str(target))
                        except (ValueError, TypeError):
                            issues.append(
                                LintIssue(
                                    file_path=file_path,
                                    rule="schema/invalid-relationship-uuid",
                                    message=f"Relationship target {target!r} is not a valid UUID",
                                    level="error",
                                )
                            )

        return issues, frontmatter, body

    def lint_file(self, file_path: Path) -> List[LintIssue]:
        """Lint a file on disk."""
        try:
            text = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return [
                LintIssue(
                    file_path=str(file_path),
                    rule="file/encoding",
                    message="File is not valid UTF-8 encoded text",
                    level="error",
                )
            ]
        except Exception as exc:
            return [
                LintIssue(
                    file_path=str(file_path),
                    rule="file/unreadable",
                    message=f"Cannot read file: {exc}",
                    level="error",
                )
            ]

        issues, _, _ = self.lint_file_content(text, str(file_path))
        return issues

    def lint_directory(self, dir_path: Path, recursive: bool = True) -> LintReport:
        """Scan and lint an entire directory of capsules, checking cross-file references."""
        report = LintReport()
        if not dir_path.exists() or not dir_path.is_dir():
            report.errors.append(
                LintIssue(
                    file_path=str(dir_path),
                    rule="vault/not-found",
                    message=f"Capsules directory not found: {dir_path}",
                    level="error",
                )
            )
            return report

        pattern = "**/*" if recursive else "*"
        all_files: List[Path] = []
        for p in sorted(dir_path.glob(pattern)):
            if p.is_file() and (p.name.endswith(".caps.md") or p.name.endswith(".capsule.md") or p.suffix == ".md"):
                # Skip hidden/archive/staging files if within .vault
                if any(part.startswith(".") for part in p.parts if part != "."):
                    continue
                all_files.append(p)

        report.total_scanned = len(all_files)
        known_ids: Dict[str, Path] = {}
        pending_relationships: List[Tuple[Path, str, str]] = []  # (source_file, target_uuid, rel_type)

        for file_path in all_files:
            try:
                text = file_path.read_text(encoding="utf-8")
            except Exception as exc:
                report.errors.append(
                    LintIssue(
                        file_path=str(file_path),
                        rule="file/read-error",
                        message=f"Cannot read file: {exc}",
                        level="error",
                    )
                )
                continue

            issues, frontmatter, _ = self.lint_file_content(text, str(file_path))

            file_has_error = False
            for issue in issues:
                if issue.level == "error":
                    report.errors.append(issue)
                    file_has_error = True
                else:
                    report.warnings.append(issue)

            if not file_has_error:
                report.passed_count += 1

            if frontmatter:
                # Check for ID collisions across vault
                capsule_id = frontmatter.get("id")
                if capsule_id:
                    capsule_id_str = str(capsule_id).strip().lower()
                    if capsule_id_str in known_ids:
                        report.errors.append(
                            LintIssue(
                                file_path=str(file_path),
                                rule="schema/duplicate-id",
                                message=f"Duplicate capsule ID '{capsule_id}' already defined in {known_ids[capsule_id_str]}",
                                level="error",
                            )
                        )
                    else:
                        known_ids[capsule_id_str] = file_path

                # Queue relationships for cross-file link validation
                rels = frontmatter.get("relationships")
                if isinstance(rels, list):
                    for r in rels:
                        target = None
                        rel_type = "relates_to"
                        if isinstance(r, str):
                            target = r
                        elif isinstance(r, dict):
                            target = r.get("to") or r.get("id") or r.get("to_id")
                            rel_type = str(r.get("type") or "relates_to")
                        if target:
                            try:
                                valid_uuid = str(UUID(str(target))).lower()
                                pending_relationships.append((file_path, valid_uuid, rel_type))
                            except ValueError:
                                pass

        # Verify all relationship targets exist in the known ID set
        for src_file, target_uuid, rel_type in pending_relationships:
            if target_uuid not in known_ids:
                broken_issue = LintIssue(
                    file_path=str(src_file),
                    rule="links/broken-relationship",
                    message=f"Broken relationship: target capsule ID '{target_uuid}' ({rel_type}) not found in vault",
                    level="error",
                )
                report.broken_relationships.append(broken_issue)
                report.errors.append(broken_issue)

        return report
