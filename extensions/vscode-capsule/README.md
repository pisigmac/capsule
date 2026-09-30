# Capsule Companion — VS Code & Cursor Extension

> **Atomic memory and architectural invariant hover companion for VS Code, Cursor, and Windsurf.**

[![Version](https://img.shields.io/badge/version-0.5.0-blue.svg)](https://github.com/pisigmac/capsule)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## 🌟 Features

- 🛡️ **Inline Invariant Hover Tooltips**: Hover over code identifiers, `@capsule(id)` annotations, or files matching capsule tags to instantly view relevant architectural decisions and invariants.
- 🌳 **Sidebar Memory Vault Explorer**: Browse and search all repository capsules categorized by confidence and tags in the Activity Bar.
- 🔍 **Quick Command Palette Search**: Press `Cmd+Shift+P` (or `Ctrl+Shift+P`) -> `Capsule: Search Memory Vault` for fuzzy searching across all project knowledge.
- ➕ **One-Click Capsule Creation**: Create atomic `.caps.md` notes with pre-filled YAML frontmatter directly from the editor.
- ⚡ **Zero-Latency In-Memory Indexing**: Local file-watcher updates the hover cache in real time with <5ms response latency.

---

## 🚀 Installation & Building

```bash
cd extensions/vscode-capsule
npm install
npm run compile
```

To package as a `.vsix` extension:
```bash
npx @vscode/vsce package
```

---

## ⚙️ Configuration

| Setting | Default | Description |
|---|---|---|
| `capsule.capsulesDirectory` | `caps` | Directory relative to workspace root containing `.caps.md` files |
| `capsule.enableHover` | `true` | Enable or disable inline hover tooltips |
| `capsule.confidenceThreshold` | `all` | Minimum confidence level required for tooltips (`all`, `medium`, `high`) |
