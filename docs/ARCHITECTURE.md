# Architecture

`jev-audit` は小型の高速簡易監査器として、監査ロジックを1箇所に置く。

```text
CLI ─┐
     ├── Audit Core ─ Scanner ─ Batch ─ Jev ─ Local Aggregate ─ Report
MCP ─┘
```

## 境界

- `scanner.py`: ファイル列挙・安全な除外・必要最小限のGit-aware列挙
- `batching.py`: Jevへ送る単位へ分割
- `jev_gateway.py`: Jev質問とTypeSafe SDK境界
- `aggregate.py`: バッチ結果の軽量な決定的集約
- `auditor.py`: オーケストレーション
- `cli.py`: CLI / CI入口
- `mcp_server.py`: MCP入口
- `profiles/*.json`: 監査規定

## 監査方針

バッチ単体では、プロジェクト全体の完成証明を要求しない。
そのファイル群から直接確認できる問題だけを評価する。

Jevの`local_status`はrisk値と分離する。`review + rework`は要確認判定へ使い、`unknown`は情報不足として別statusに分離する。
最終段でJevへ再問い合わせはせず、バッチ結果をコードで集約する。

## セキュリティ

`.env`、秘密鍵、代表的なcredential/secretsファイルは本文をJevへ送らない。

## 非目標

- 正しさの証明
- 詳細な静的解析器の代替
- 完全なテスト・回帰検証
- 自動修正

目的は、詳細調査すべき場所を高速に絞ることだけである。


## MCP directory resolution

MCP adapter resolves the target directory in this order: explicit tool `path`, Claude Code `CLAUDE_PROJECT_DIR`, then server process cwd. The Audit Core itself remains client-agnostic.

changed-onlyでは削除ファイルの存在を検出・報告するが、削除前本文は復元せずJev監査対象には含めない。
