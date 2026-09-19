# jev-audit

TypeSafe AI **Jev** を使って、現在のディレクトリや任意のリポジトリを高速に一次監査する小型ツールです。

目的は完全監査ではなく、**ファイル全体をざっと見て、具体的に怪しい箇所を早く絞ること**です。

- 実装・設定・文書内の具体的な問題候補
- 仕様・実装の食い違い候補
- 回帰リスクの兆候
- 危険な暗黙前提
- 関連しそうな監査規定
- 怪しいファイル群

`context不足` は問題そのものと分離して表示し、リスク値には加算しません。

## セットアップ

前提:

- Python 3.10+
- 環境変数 `TYPESAFE_API_KEY` を設定済み

PowerShell:

```powershell
.\setup.ps1
```

任意のディレクトリから直接呼ぶ場合:

```powershell
.\install-command.ps1
```

新しいPowerShellを開けば、どのディレクトリでも使えます。

## 使い方

```powershell
cd C:\path\to\repo
jev-audit
```

Gitの変更ファイルだけ:

```powershell
jev-audit . --changed-only
```

JSON保存:

```powershell
jev-audit . --save audit-result.json
```

標準出力もJSONだけ:

```powershell
jev-audit . --json
```

`rework` のときだけ非0終了:

```powershell
jev-audit . --fail-on rework
```

## 処理

```text
対象ディレクトリ
  ↓
secret / binary / build成果物等を除外
  ↓
テキストを複数バッチへ分割
  ↓
Jevで並列・局所監査
  ↓
コードで軽量集約
  ↓
レポート
```

バッチでは「そのファイル群から直接確認できる問題」だけを評価します。
テスト結果等が見つからないだけで規定違反とは扱いません。

既定値:

- 各ファイル最大 12,000文字
- 1バッチ最大 32,000文字
- 並列 4 request

必要なら変更できます。

```powershell
jev-audit . --workers 2 --batch-chars 24000
```

## 監査プロファイル

既定は `development`。

```powershell
jev-audit . --profile development
jev-audit . --profile generic
jev-audit --list-profiles
```

任意JSONも指定できます。

```powershell
jev-audit . --profile C:\rules\my-audit.json
```

## 秘密情報

以下の本文は既定でJevへ送りません。

- `.env`, `.env.*`
- `.npmrc`, `.pypirc`, `.netrc`
- `credentials.json`, `secrets.json`
- `id_rsa`, `id_ed25519`
- `*.key`, `*.p12`, `*.pfx`, `*.jks`, `*.keystore`

Gitリポジトリでは `.gitignore` も尊重します。

## MCP

```powershell
.\mcp.ps1
```

または:

```powershell
jev-audit-mcp
```

公開tool:

- `audit_directory`
- `list_profiles`

CLIとMCPは同じAudit Coreを使用します。

## レポートの読み方

- `risk`: 上位3バッチの具体的リスク値の平均
- `concrete_issue`: ファイル内容から直接読める欠陥・矛盾候補
- `context_insufficient`: 判断材料不足。**riskには含めない**
- `rule suspicion signals`: どの監査規定が相対的に関係しそうか。絶対的な違反確率ではない

これは高速簡易監査です。テスト・実操作・詳細レビューの代替ではありません。
