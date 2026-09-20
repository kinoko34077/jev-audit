# jev-audit

TypeSafe AI **Jev** を使って、現在のディレクトリや任意のリポジトリを高速に一次監査する小型ツールです。

目的は完全監査ではなく、**ファイル全体をざっと見て、具体的に怪しい箇所を早く絞ること**です。

- 実装・設定・文書内の具体的な問題候補
- 仕様・実装の食い違い候補
- 回帰リスクの兆候
- 怪しいファイル群

## セットアップ

前提:

- Python 3.10+
- 環境変数 `TYPESAFE_API_KEY` を設定済み
- Gitは任意（`--changed-only`使用時のみ必要）

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

Gitの変更ファイルだけ（削除は件数のみ検出し、内容監査はしません）:

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

- `.env`, `.env.*`, `.envrc`
- `.npmrc`, `.pypirc`, `.netrc`
- `credentials.json`, `secrets.json`
- `id_rsa`, `id_ed25519`
- `*.key`, `*.pem`, `*.p12`, `*.pfx`, `*.jks`, `*.keystore`

Gitが利用可能なGitリポジトリでは `.gitignore` も尊重します。Git未導入環境では通常のディレクトリ走査へ自動フォールバックします。

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

`audit_directory` の対象directory解決順:

1. MCP clientが `path` に渡したdirectory（Codex/Claude等）
2. Claude Codeの `CLAUDE_PROJECT_DIR`
3. MCP server processのcurrent working directory

Codexではactive workspace/repositoryの絶対pathをtool引数 `path` として渡すのが確実です。Claude Codeでは`path`を明示してもよく、省略時は`CLAUDE_PROJECT_DIR`を使用します。CLIとMCPは同じAudit Coreを使用します。

## レポートの読み方

- `risk`: `concrete_issue / spec_mismatch / regression_risk`のうち、全バッチで最も高い具体的リスク値
- `concrete_issue`: ファイル内容から直接読める欠陥・矛盾候補
- `local_status`: `clear / review / rework / unknown` の確率分布。`review + rework`は要確認判定に使い、`unknown`は情報不足として分離する
- `elapsed`: 実行開始から終了までのwall-clock時間
- `reason`: 最終statusを発生させた条件とbatch
- `api work`: 並列Jev requestの処理時間合計であり、実待ち時間ではない

これは高速簡易監査です。テスト・実操作・詳細レビューの代替ではありません。
