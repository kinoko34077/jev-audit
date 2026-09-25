# Jev Audit 総合ガイド

Status: stable `v0.2.12`

この文書は、`jev-audit`が**何をするものか、何に使うか、どの入口を選ぶか、結果をどう読むか**を一枚で把握するための入口である。細かなCLI optionや全境界条件は [USAGE_GUIDE.md](USAGE_GUIDE.md)、内部構造は [ARCHITECTURE.md](ARCHITECTURE.md)、現行状態は [`project/docs/CURRENT_STATE.md`](../project/docs/CURRENT_STATE.md) を参照する。

## 1. Jev Auditとは

`jev-audit`は、TypeSafe AI **Jev**を使ってrepositoryやdirectoryを高速に一次監査する小型ツールである。

目的は「AIにrepository全体を長時間レビューさせること」ではなく、**広い範囲を先に軽く見て、詳細レビュー・テスト・修正へ回すべき場所を絞ること**にある。

基本処理は次の形である。

```text
対象directory / Git変更
  ↓
安全な除外・text抽出
  ↓
複数batchへ分割
  ↓
Jevで局所的な監査質問を評価
  ↓
コードで決定的に集約
  ↓
Audit Report
```

CLIとlocal STDIO MCPは同じAudit Coreを使う。Jevへ最終判断を丸投げせず、各batchの結果をローカルコードで集約する。

## 2. 何を判定するか

Jev Auditは各batchについて、主に次のsignalを見る。

| signal | 意味 |
|---|---|
| `concrete_issue` | そのファイル群から直接確認できる、具体的な欠陥・矛盾・危険な挙動の兆候 |
| `spec_mismatch` | 同じ監査範囲内で確認できる、仕様・説明・設定・実装の明確な食い違い |
| `regression_risk` | 具体的な変更・実装から直接読み取れる回帰リスク |
| `local_status` | `clear / review / rework / unknown` の局所状態分布 |

重要なのは、**「証拠が見つからない」ことと「違反している」ことを同一視しない**点である。

例えば、batch内にテスト結果が無いだけで`concrete_issue`を高くしない。別ファイルを見ないと判断できない場合は、問題ありと推測するのではなく`unknown`側として扱う。

## 3. 向いている用途

### 日常開発の一次監査

テスト・lint・typecheck等の後に変更部分だけを広く確認する。

```text
test / lint / typecheck
  ↓
jev-audit . --changed-only
  ↓
review / rework のbatchとpathを確認
  ↓
必要箇所だけ詳細レビュー・修正
```

### PR前・レビュー前の絞り込み

変更ファイルが多い場合に、どこを人間・LLM・詳細テストで優先して見るべきかを絞る。

### release前・大きな変更後のfull scan

変更範囲だけではなくrepository全体を軽く再確認したい場合にfull scanする。

### Agentの軽量preflight

Agentが本格的なコードレビューや修正へ入る前に、MCPから一次監査して怪しい領域を選ぶ。

### 仕様と実装を同時に渡す監査

仕様書と関連実装を同じ監査範囲へ入れることで、`spec_mismatch`のsignalを使って直接確認可能な食い違い候補を拾う。

## 4. 向いていない用途

Jev Auditは次の代替ではない。

- 正しさの証明
- 詳細な静的解析器
- 型検査・lint・unit test・integration test
- 完全な回帰検証
- repository品質の点数付け
- 自動修正器
- セキュリティ監査の完全な代替

`clear`やGREENは「問題が存在しない証明」ではない。**今回の入力範囲で強い問題signalが出なかった**という意味に限定する。

## 5. どの入口を使うか

| 入口 | 適する状況 | filesystem / Git |
|---|---|---|
| Local CLI `jev-audit` | 開発者がterminalからrepositoryを監査する | 直接扱う |
| Local STDIO MCP `jev-audit-mcp` | Codex / Claude等のlocal Agentから監査する | allowed root内を直接扱う |
| Remote REST | script / app / CI等からHTTPでfile snapshotを送る | 扱わない |
| Remote MCP | Remote Agent / MCP clientからfile snapshotをtool callする | 扱わない |

このrepositoryが所有するのは**Local CLI / Local STDIO MCP / Audit Core**である。

Remote REST / Remote MCPは `kinoko34077/kinotch-api` が所有する。Remote版は同じ`jev-audit` v0.2.12由来の監査意味論を使うが、local filesystemやGitへ到達せず、callerが明示的に送ったfile snapshotだけを監査する。

Remote版の正本: <https://github.com/kinoko34077/kinotch-api/blob/main/docs/jev-audit.md>

## 6. 最短の使い方

### Setup

前提:

- Python 3.10+
- 実際にJev requestを行う場合は`TYPESAFE_API_KEY`
- `--changed-only`を使う場合はGit

PowerShell:

```powershell
.\setup.ps1
```

通常実行:

```powershell
jev-audit .
```

変更部分だけ:

```powershell
jev-audit . --changed-only
```

特定moduleだけ:

```powershell
jev-audit .\jev_audit
```

JSONを保存:

```powershell
jev-audit . --save .audit/audit-result.json
```

標準出力をJSONだけにする:

```powershell
jev-audit . --json
```

`rework`時だけ非0終了にする:

```powershell
jev-audit . --fail-on rework
```

利用可能profileを確認:

```powershell
jev-audit --list-profiles
```

## 7. scan modeの使い分け

### `--changed-only`

日常開発の既定候補。Git repository rootで使う。

- 追跡済みregular fileの変更では、現在本文に加えてbounded Git diff contextを渡す。
- untracked fileは現在本文を使う。
- 削除fileは削除された事実を記録するが、削除前本文を復元してJevへ送らない。
- symlinkやsubmodule pointerだけの変更等、本文監査できないentryはskip情報として残し、必要に応じて`unknown`になる。
- clean repositoryではJev requestを行わず、通常のno-op `clear`を返すためAPI keyは不要。

### full scan

```powershell
jev-audit .
```

repository全体を対象にする。release前、大規模変更後、初回監査などに使う。

### focused scan

```powershell
jev-audit path\to\module
```

問題領域や関連contextが分かっている場合に、対象を狭めて監査密度を上げる。

## 8. Profileとmodel

bundled profileは次の2種類である。

- `development`: 開発repository向け
- `generic`: より一般的な内容向け

Local版では明示的なJSON profileも指定できる。

```powershell
jev-audit . --profile development
jev-audit . --profile generic
jev-audit . --profile C:\rules\my-audit.json
```

既定Jev modelは`jev-1.13.0`。Local版ではCLI `--model`または`TYPESAFE_DEFAULT_MODEL`で明示overrideできるが、既定modelを変更する場合は評価後に固定値を更新する。

Remote版は再現性のためmodel/profileをより強く固定しており、caller側の任意model overrideや任意profile fileは受け付けない。

## 9. Reportの読み方

CLIの代表的な表示は次のように解釈する。

| 表示 | 内部status | 意味 |
|---|---|---|
| GREEN | `clear` | 強い要確認signalなし |
| YELLOW | `review` | 詳細確認へ回す候補あり |
| RED | `rework` | 修正候補として優先確認 |
| UNKNOWN | `unknown` | 判断材料不足 |

`risk`はrepository全体の品質scoreではない。各batchの`concrete_issue / spec_mismatch / regression_risk`から得た最大signalを示す。

`unknown`も問題確率ではなく、局所的な判断材料不足を示す。

`coverage.char_coverage`は**実際に読み込んだtext file群**に対する送信文字数 / 元文字数であり、repository全体を何%理解したかという指標ではない。

providerがtoken usageを返さない場合、token数は`null`または`-`として扱い、0 tokenとは解釈しない。

## 10. Security / privacy

代表的なsecret fileは既定で本文送信対象から除外する。

例:

- `.env`, `.env.*`, `.envrc`
- `.npmrc`, `.pypirc`, `.netrc`
- `credentials.json`, `secrets.json`
- private key / certificate系file

ただし、これは**完全なDLPではない**。通常source fileへ直接埋め込まれたcredentialや機密情報は監査対象になり得る。

Jev監査では対象sourceの内容が外部providerへ送信されるため、送信が許可されたrepository / fileだけを対象にする。

`TYPESAFE_LOG_LEVEL=debug`やTypeSafe SDK loggerのDEBUGを有効にすると、request body内のsourceがlocal logや収集基盤へ出る可能性がある。機密sourceを扱う場合はDEBUG loggingを無効にする。

Git metadataが存在するのに安全なroot判定やcandidate列挙に失敗した場合、`.gitignore`を無視したdirectory walkへ自動的にfail-openせず停止する。

## 11. 主なguardrail

現行の代表的な既定値:

| 項目 | Local既定 |
|---|---:|
| effective content / file | 12,000 chars |
| batch target | 32,000 chars |
| parallel Jev requests | 4 |
| audit files | 10,000 |
| estimated total input | 5,000,000 chars |
| batches | 1,000 |
| workers | 最大32 |
| MCP workers | 最大16 |

総input guardrailにはfile本文やdiffだけでなく、各batchへ繰り返し入るquestion/profile instructionの推定分も含む。上限を超えた場合はJev request開始前に停止する。

## 12. Local MCP

起動:

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

`audit_directory`のdirectory解決順は、tool argument `path` → `CLAUDE_PROJECT_DIR` → MCP server processのcwd。

既定では`JEV_AUDIT_ALLOWED_ROOT`配下だけを許可する。任意pathを明示的に許可する場合だけ`JEV_AUDIT_ALLOW_ANY_PATH=1`を使う。

Agentから使う場合も、監査結果だけで修正を確定せず、YELLOW / RED / UNKNOWNの根拠batchとpathを詳細レビューへ渡す使い方が基本になる。

## 13. Remote REST / MCPとの関係

Remote版は、Local版をserverへそのまま載せたものではない。

```text
Local
repository / Git
  ↓
scanner
  ↓
Audit Core

Remote
callerがfile snapshotを構成
  ↓ REST or MCP
private jev-audit Worker
  ↓
同系統の監査意味論 / aggregate
```

Remote v1はrepository clone、local path指定、Git discovery、`changed_only`を行わない。その代わり、HTTP / Remote MCPから明示的なfile snapshotを監査できる。

ProductionではRESTとCloudflare Access Service Token MCPの両経路が実E2E確認済み。Remoteのendpoint、認証、request契約、上限、release状態は`kinotch-api`側の専用文書を正本とする。

## 14. Version / stable baseline

現行安定版は`v0.2.12`。

```text
v0.2.12
  → 13e11ef422643ac247e82685f771034eb0afa5e1
```

このtagは現行`pyproject.toml`、`jev_audit.__version__`、Project Current Stateの`0.2.12`と一致し、対象SHAのTests / Verifyが成功した状態を固定している。

## 15. どの文書を見るか

- **まず全体を把握する**: この`OVERVIEW.md`
- **細かな使い方・制限**: [USAGE_GUIDE.md](USAGE_GUIDE.md)
- **内部構造**: [ARCHITECTURE.md](ARCHITECTURE.md)
- **Runtime Pilot**: [RUNTIME_PILOT.md](RUNTIME_PILOT.md)
- **現行状態**: [`project/docs/CURRENT_STATE.md`](../project/docs/CURRENT_STATE.md)
- **Project specification**: [`project/docs/SPEC.md`](../project/docs/SPEC.md)
- **Remote REST / MCP**: <https://github.com/kinoko34077/kinotch-api/blob/main/docs/jev-audit.md>
