# jev-audit

[![Tests](https://github.com/kinoko34077/jev-audit/actions/workflows/tests.yml/badge.svg)](https://github.com/kinoko34077/jev-audit/actions/workflows/tests.yml)

TypeSafe AI **Jev** を使って、現在のディレクトリや任意のリポジトリを高速に一次監査する小型ツールです。

目的は完全監査ではなく、**ファイル全体をざっと見て、具体的に怪しい箇所を早く絞ること**です。

詳細なLLMレビューやテストの前段で、広く浅く候補を絞る一次スクリーニング用途を想定しています。

- 実装・設定・文書内の具体的な問題候補
- 仕様・実装の食い違い候補
- 回帰リスクの兆候
- 怪しいファイル群

## セットアップ

前提:

- Python 3.10+
- Jev requestを行う場合は環境変数 `TYPESAFE_API_KEY` を設定済み（cleanな`--changed-only` no-opは不要）
- Gitは任意（`--changed-only`使用時のみ必要）

Jev modelは既定で`jev-1.13.0`に固定しています。更新時は
`TYPESAFE_DEFAULT_MODEL`またはCLIの`--model`で明示し、評価後に既定値を更新してください。

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
jev-audit . --save .audit/audit-result.json
```

`.audit/`は生成レポート用の除外directoryです。保存先の親directoryは自動作成されます。

標準出力もJSONだけ:

```powershell
jev-audit . --json
```

`rework` のときだけ非0終了:

```powershell
jev-audit . --fail-on rework
```

## 推奨ワークフロー

通常の開発では、テスト等の後に変更範囲を監査します。

```text
test / lint / typecheck
  ↓
jev-audit . --changed-only
  ↓
YELLOW / RED の理由と対象batchを確認
```

releaseや大きな変更の節目ではfull scanも行い、通常のテストと必要箇所の詳細レビューを続けます。

- **GREEN**: 今回の対象で強いシグナルはありません。通常の検証は省略しません。
- **YELLOW**: `reason` のbatchとpathsを優先して確認します。
- **RED**: 修正候補として詳細レビューとテストを行います。
- **UNKNOWN**: 判断材料が不足しています。関連contextや監査範囲を増やします。

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

bundled profile名（`development`、`generic`）は常にパッケージ内の正本を使います。custom profileは明示した`.json` pathだけを読み込み、監査対象repository内の同名ファイルやdirectoryが既定profileを上書きすることはありません。

## 秘密情報

以下の本文は既定でJevへ送りません。

- `.env`, `.env.*`, `.envrc`
- `.npmrc`, `.pypirc`, `.netrc`
- `credentials.json`, `secrets.json`
- `id_rsa`, `id_ed25519`
- `*.key`, `*.pem`, `*.p12`, `*.pfx`, `*.jks`, `*.keystore`

対象path自体がGit repository rootで、Gitが利用可能な場合はGitから候補を列挙し、未追跡ファイルには `.gitignore` 等の標準除外規則を適用します。Git未導入環境やrepository内のsubdirectoryを対象にしたfull scanでは通常のdirectory走査になり、`.gitignore`は適用されません。`--changed-only`はGit repository rootでのみ使えます。変更がないcleanなrepositoryではno-opの`clear`を返し、exit 0になります。

Git metadataが存在するのにroot判定や候補列挙に失敗した場合は、`.gitignore`を無視したdirectory walkへfail-openせずエラーで停止します。`--changed-only`でsymlinkやsubmodule pointerだけが変更された場合も、変更をskip情報として残して`UNKNOWN`扱いにします。

これはファイル名・拡張子等による除外で、完全なDLPではありません。ソース内に直接書かれた鍵や機密情報は監査対象になり得ます。外部APIへの送信が認められている範囲で利用してください。`TYPESAFE_LOG_LEVEL=debug`やTypeSafe SDK loggerのDEBUGを有効にすると、request bodyに含まれるsource本文がローカルログやログ収集基盤へ出る可能性があるため、機密性のある監査ではDEBUG loggingを無効にしてください。詳しくは[利用ガイドのセキュリティ節](docs/USAGE_GUIDE.md)を参照してください。

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

MCPは既定で`JEV_AUDIT_ALLOWED_ROOT`（未設定時は`CLAUDE_PROJECT_DIR`、さらに未設定ならserverのcurrent directory）配下だけを監査します。任意pathを明示的に許可する場合だけ`JEV_AUDIT_ALLOW_ANY_PATH=1`を設定してください。MCPにはfile size、batch size、workersのhard capもあります。

## KiNoTch Runtime Pilot

The first Runtime Pilot is optional and does not change the default install or
the Audit Core. Install the pinned Runtime reference package when evaluating
the shared `repo.audit` Action boundary:

```powershell
python -m pip install -e ".[pilot]"
$env:JEV_AUDIT_RUNTIME = "1"
```

When `JEV_AUDIT_RUNTIME=1` is explicitly set and `kinotch_runtime` is importable,
both CLI and MCP call the existing Audit Core through the Runtime kernel. Without
that opt-in, the direct Audit Core path remains active even if the package happens
to be installed. This is a measurement boundary, not a CLI/MCP Surface Pack. Known audit and provider
failures retain a structured code, the original message, and exception metadata
where available; unknown Runtime failures are re-raised for the Runtime
kernel's `INTERNAL_ERROR` redaction.

The evaluated live Pilot evidence and remaining Contract boundary are recorded in
[docs/RUNTIME_PILOT.md](docs/RUNTIME_PILOT.md).

## レポートの読み方

- `risk`: 各batchの `concrete_issue / spec_mismatch / regression_risk` の最大値を求め、その中の最大値を表示します。`risk=82%` はrepo全体の危険度ではなく、どこか1 batchで出た最大シグナルです。
- `concrete_issue`: ファイル内容から直接読める欠陥・矛盾候補
- `local_status`: `clear / review / rework / unknown` の確率分布。`actionable` は `review + rework` で、詳細確認や修正へ回す度合いです。`unknown` は問題の確率ではなく、局所的な判断材料の不足を表します。
- `elapsed`: 実行開始から終了までのwall-clock時間
- `reason`: statusの判定条件とbatch。triggerには対象`paths`も含まれます。
- `coverage`: 送信文字数/元文字数、truncated file数、skip file数。`truncated_paths`と`skipped_paths_by_reason`で対象範囲を復元できます。
- `provenance`: tool version、resolved model、profile hash、scan条件、Git HEAD SHA。再現性確認に使います。
- `api work`: 並列Jev requestの処理時間合計であり、実待ち時間ではない

GREENは安全証明ではありません。riskの値は正解率やrepo品質スコアでもありません。いずれのstatusでも、テスト・実操作・詳細レビューを省略する根拠にはなりません。

## 精度を上げるには

Jevの判断は各batchへ渡された情報に基づきます。短いREADMEやINDEXで正本と関連ファイルの場所を示し、currentとlegacyを区別し、日常利用では `--changed-only` やmodule単位のfocused scanで関連contextを集めます。root INDEXが全batchへ自動共有されるわけではありません。

context設計、batchやskipの限界、custom profile、CI、MCP、token効率などは[詳細な利用ガイド](docs/USAGE_GUIDE.md)を参照してください。
