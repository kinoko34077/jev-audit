# jev-audit Project Overlay

This overlay records the KiNoTch Project boundary for the existing jev-audit
repository. The user-facing README and Domain implementation remain at the
repository root.

## 概要

このRepositoryは KiNoTch. Repository Base に準拠します。

- 個別情報・仕様・実装: project/
- 個別プロジェクト定義: project/project.json
- 個別仕様索引: project/docs/INDEX.md
- 現在状態: project/docs/CURRENT_STATE.md
- 共通操作: .kinotch/README_BASE.md

## Project-owned surfaces

- CLI: `audit.ps1` / `jev-audit.cli`
- MCP: `mcp.ps1` / `jev_audit.mcp_server`
- Optional Runtime bridge: `jev_audit.runtime_bridge`

既存のCLI/MCP dispatch、Audit Core、Runtime optional pathはProject側の責務として保持します。
`project/project.json` の `paths.source`、`paths.tests`、`paths.docs` が示すrootの既存Domain領域も、移行期間中はProject-ownedとして編集対象です。.kinotchとAGENTS.mdは共通Base層のため編集対象にしません。

## 最短利用方法

```powershell
.\knt.cmd doctor
.\knt.cmd setup
 .\knt.cmd verify
```
