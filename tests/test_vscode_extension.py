"""Verification tests for the VS Code / Cursor Companion extension manifest and bundle."""
from __future__ import annotations

import json
from pathlib import Path


class TestVsCodeExtension:
    def test_extension_package_json_validity(self):
        pkg_path = Path("extensions/vscode-capsule/package.json")
        assert pkg_path.exists()

        data = json.loads(pkg_path.read_text(encoding="utf-8"))
        assert data["name"] == "capsule-companion"
        assert data["version"] == "0.5.0"
        assert data["publisher"] == "pisigmac"
        assert "main" in data

        contributes = data.get("contributes", {})
        commands = contributes.get("commands", [])
        command_ids = {c["command"] for c in commands}

        assert "capsule.search" in command_ids
        assert "capsule.new" in command_ids
        assert "capsule.openCapsule" in command_ids
        assert "capsule.reconcile" in command_ids
        assert "capsule.refreshTree" in command_ids

        # Views and viewsContainers
        assert "viewsContainers" in contributes
        assert "activitybar" in contributes["viewsContainers"]
        assert "views" in contributes
        assert "capsule-sidebar" in contributes["views"]

        # Configuration properties
        config = contributes.get("configuration", {}).get("properties", {})
        assert "capsule.capsulesDirectory" in config
        assert "capsule.enableHover" in config
        assert "capsule.confidenceThreshold" in config

    def test_extension_compiled_artifacts_exist(self):
        dist_dir = Path("extensions/vscode-capsule/dist")
        assert (dist_dir / "extension.js").exists()
        assert (dist_dir / "hoverProvider.js").exists()
        assert (dist_dir / "treeProvider.js").exists()
        assert (dist_dir / "capsuleService.js").exists()

    def test_tsconfig_validity(self):
        tsconfig_path = Path("extensions/vscode-capsule/tsconfig.json")
        assert tsconfig_path.exists()
        data = json.loads(tsconfig_path.read_text(encoding="utf-8"))
        assert data["compilerOptions"]["module"] == "commonjs"
        assert data["compilerOptions"]["outDir"] == "dist"
