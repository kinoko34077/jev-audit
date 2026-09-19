# Architecture

`jev-audit` は監査ロジックを1箇所に置き、利用入口だけを分離する。

```text
CLI ─┐
     ├── Audit Core ── Scanner ── Batch ── Jev ── Aggregate ── Report
MCP ─┘
```

## 境界

- `scanner.py`: ローカルファイルの列挙・安全な除外・Git情報取得
- `batching.py`: Jevへ送る単位へ分割
- `jev_gateway.py`: TypeSafe SDK / Jevだけを知る外部境界
- `aggregate.py`: 個別バッチ結果のローカル集約
- `auditor.py`: 全体のオーケストレーション
- `cli.py`: 人間・CI向け入口
- `mcp_server.py`: AI/MCP向け薄い入口
- `profiles/*.json`: 監査規定。ロジックと分離したデータ

## セキュリティ

`.env`、秘密鍵、credentials/secrets JSON等の本文は既定でJevへ送らない。
ファイル名のみ監査メタデータとして残る場合がある。

## 完了判定

Jevの結果は確率的な一次監査であり、正しさの証明ではない。
テスト・実操作・静的解析等の決定的な証拠を置換しない。
