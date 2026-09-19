# jev-audit

TypeSafe AI **Jev** を使って、現在のディレクトリや任意のリポジトリを高速に一次監査するための小型ツールです。

目的は「正しさを証明する」ことではなく、以下を安価・高速に確率評価して、詳細レビューが必要な場所を早く見つけることです。

- この状態で完了扱いしてよさそうか
- 修正が必要そうか
- 検証が足りないか
- 回帰リスクがあるか
- 仕様・README・実装が食い違っていないか
- どの監査規定への違反確率が高いか
- どのファイル群が怪しいか

## 1. セットアップ

前提:

- Python 3.10+
- 環境変数 `TYPESAFE_API_KEY` を設定済み

PowerShell:

```powershell
.\setup.ps1
```

任意のディレクトリから `jev-audit` を直接呼びたい場合は、ユーザーPATHへランチャーを追加します。

```powershell
.\install-command.ps1
```

その後、新しいPowerShellを開いてください。

## 2. 使い方

このフォルダから別リポジトリを監査:

```powershell
.\audit.ps1 C:\path\to\repo
```

`install-command.ps1` 実行後は、任意の場所から:

```powershell
cd C:\path\to\repo
jev-audit .
```

現在ディレクトリなら `.` は省略できます。

```powershell
jev-audit
```

Gitで変更されたファイルだけ:

```powershell
jev-audit . --changed-only
```

JSON保存:

```powershell
jev-audit . --save audit-result.json
```

標準出力もJSONだけにする:

```powershell
jev-audit . --json
```

CI等で `rework` のときだけ非0終了:

```powershell
jev-audit . --fail-on rework
```

## 3. 監査プロファイル

既定は `development` です。

```powershell
jev-audit . --profile development
jev-audit . --profile generic
```

任意のJSONファイルも指定できます。

```powershell
jev-audit . --profile C:\rules\my-audit.json
```

一覧:

```powershell
jev-audit --list-profiles
```

## 4. 処理の流れ

```text
対象ディレクトリ
  ↓
ファイル列挙
  ↓
secret / binary / build成果物などを除外
  ↓
テキストをバッチ分割
  ↓
各バッチをJevで並列監査
  ↓
ローカルで確率集約
  ↓
集約結果をJevでもう一度全体判定
  ↓
最終レポート
```

全ファイルを1リクエストへ無理に詰め込まず、複数バッチへ分けます。
`--workers` で並列数、`--batch-chars` で1バッチの大きさを調整できます。

```powershell
jev-audit . --workers 2 --batch-chars 12000
```

## 5. 秘密情報

以下の本文は既定で外部へ送信しません。

- `.env`, `.env.*`
- `.npmrc`, `.pypirc`, `.netrc`
- `credentials.json`, `secrets.json`
- `id_rsa`, `id_ed25519`
- `*.key`, `*.p12`, `*.pfx`, `*.jks`, `*.keystore`

また、Gitリポジトリでは `git ls-files -co --exclude-standard` を使うため、通常の `.gitignore` も尊重します。

## 6. MCP

セットアップ時にMCP v2も入ります。

直接起動:

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

MCP hostから `audit_directory(path="C:\\path\\to\\repo")` のように呼べます。

## 7. 注意

これは **高速簡易監査** です。

- Jevの確率判断はテストの代替ではありません。
- 全文を送っていても、正しさを数学的に保証するものではありません。
- 巨大ファイルは既定で2MB超を除外します。
- 各ファイルは既定で12,000文字まで。超過時は先頭＋末尾へ切り詰めます。
- lock/generated系の代表的なファイルは既定で除外します。

完全監査ではなく「どこが怪しいかを高速に絞る」用途を主目的にしています。
