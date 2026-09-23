# jev-audit 利用ガイド

このガイドは、`jev-audit v0.2.9`を誤解せず、監査範囲・context・実行時間を意識して使うためのものです。READMEは導入と基本操作の入口、[ARCHITECTURE.md](ARCHITECTURE.md)は内部構造、ここでは日々の利用判断と注意点を説明します。

## 1. このツールの位置付け

`jev-audit`は、詳細なLLMレビューやテストの代わりではありません。リポジトリや変更範囲をJevで広く浅くスクリーニングし、「次にどこを詳しく確認するか」を絞る一次監査器です。

```text
実装
  ↓
test / lint / typecheck
  ↓
jev-audit
  ↓
status・reason・pathsを見て、必要な箇所だけ人間・LLM・追加testで確認
```

1 batchにつき、Jevへ求める判断は次の4つです。

- `local_status`: `clear / review / rework / unknown` のどれに近いか
- `concrete_issue`: 内容から直接確認できる具体的な欠陥・矛盾候補があるか
- `spec_mismatch`: 提示された内容に明確な仕様との食い違いがあるか
- `regression_risk`: 提示された変更に既存挙動を壊しそうな要因があるか

Jevはbatchごとの確率的な判断を返し、最終statusはPython側の固定ロジックで集約します。Jevに最終的な総合レビューを再依頼する設計ではありません。

## 2. 得意なこと・得意ではないこと

得意なのは、大量のファイルを一次確認して、意味的な不整合・仕様と実装の食い違い・回帰リスクの候補を挙げ、詳細レビューに使う範囲を絞ることです。repository全体のspot checkや、変更後に怪しいファイル群を探す用途にも使えます。

次のものを置き換えるツールではありません。

- 正しさの証明、詳細コードレビュー、root cause分析
- 静的解析、unit / integration / E2E test、security scanner
- 自動修正やrepository品質の採点

## 3. Jevの確率を読む

Jevの出力は、渡したstateと狭く定義された質問に対する判断シグナルです。例えば `spec_mismatch = 0.82` は、今回のbatchと質問に対してJevが `spec_mismatch` 側へ強く傾いたことを示します。

この値を、正解率、実際にバグが存在する確率、repository全体の品質点として扱わないでください。型付きの結果を受け取ることと、意味判断が常に正しいことは別です。数値だけで結論を出さず、対象batchのpathsと内容を確認します。

## 4. statusとレポートの読み方

判定の優先順と現行閾値は次のとおりです。

| 表示 | 現行の条件 | 使い方 |
| --- | --- | --- |
| RED / `rework` | 同じbatchで `concrete_issue >= 0.80` かつ `rework >= 0.60` | 修正候補として詳細レビューし、修正後にtestする |
| YELLOW / `review` | REDでなく、いずれかのbatchで `risk >= 0.55` または `actionable >= 0.60` | `reason` に示されたbatchとpathsを優先確認する |
| UNKNOWN / `unknown` | RED / YELLOWでなく、いずれかのbatchで `unknown >= 0.80`。評価batchがない場合もUNKNOWN | 問題の確率とは見なさず、contextや対象範囲を増やして確認する |
| GREEN / `clear` | 上記の条件に該当しない | 今回の対象で閾値を超える強いシグナルはない。通常の検証は続ける |

ここで使う閾値は`jev-audit`の運用policyです。Jev公式の普遍的な閾値ではありません。REDがYELLOWに優先し、YELLOWがUNKNOWNに優先します。

GREENは安全証明ではありません。今回Jevへ渡した範囲で設定閾値を超える強いシグナルが出なかったことを示すだけなので、通常のtest・型検査・静的解析・実操作確認を省略しないでください。

### `risk`

各batchについて、3つの具体的なリスク判断の最大値を取ります。

```text
batch risk = max(concrete_issue, spec_mismatch, regression_risk)
overall risk = 全batchのbatch riskの最大値
```

そのため `risk = 82%` は「repository全体が82%危険」という意味ではなく、「今回のどこか1 batchで最大82%の具体的なシグナルが出た」という意味です。異なるrepositoryの品質ランキングには使いません。

### `actionable` と `unknown`

`actionable`は `review + rework` の確率を合計し、0〜1の範囲に収めた値です。バグの存在確率ではなく、詳細確認または修正へ回す度合いです。

`unknown`は、そのbatchだけでは局所的な判断材料が足りないことを表します。riskやactionableとは別の情報不足のシグナルです。判断可能なcontextを追加するか、関連する範囲を監査します。

### 確認する順番

```text
status
  ↓
reason（判定条件）
  ↓
trigger batch・via（riskの要因）・paths
  ↓
concrete / rework / actionable / unknown
  ↓
signals と skipped
```

`reason : risk=82% via=spec_mismatch at batch #18`なら、まずbatch #18のpathsを開き、仕様と実装のどの記述を比較できるかを確認します。`skipped`はJevが見ていない範囲の手掛かりです。

## 5. 日常運用とfull scan

通常の開発では、Git repositoryのrootで変更ファイルを監査します。

```powershell
jev-audit . --changed-only
```

`--changed-only`はGitのHEADとの差分と、除外されていない未追跡ファイルを対象にします。削除済みファイルはパスを検出しますが、削除前の内容は監査できません。

変更がないcleanなrepositoryではno-opの`clear`レポートを返します。Jev requestは発行せず、CLIのexit codeは0です。変更はあるものの全ファイルがsensitive、binary、lock、generatedなどでskipされた場合は、Jev requestなしの`unknown`レポートを返します。これは実行失敗ではなく、監査可能な本文がなかったことを示します。

HEADがまだない新規repositoryでは、現在の追跡対象と除外されていない未追跡ファイルを候補にするfallbackがあります。この場合、通常の差分監査より広い範囲が選ばれることがあります。

対象を変更範囲に絞れるため、通常はfull scanよりinput tokenや無関係なnoiseを抑えられます。また、今回一緒に変更した仕様・実装・test・設定を同じ対象集合に含めやすく、変更箇所に関連するcontextへ判断を集中しやすくなります。ただし、それらが同じbatchに入る保証はありません。

release前、大規模変更後、architecture変更後などにはrepository全体の確認も行います。

```powershell
jev-audit
```

巨大repositoryを毎編集でfull scanする運用は避け、日常の変更確認と節目のspot checkを使い分けます。

### 対象directoryの違い

- Git repositoryのrootでのfull scanは、追跡済みファイルと、`.gitignore`等の標準除外規則に該当しない未追跡ファイルを候補にします。
- `--changed-only`は、指定path自体がGit repositoryのrootである必要があります。`jev-audit src --changed-only`のような指定はできません。
- `jev-audit src`のようなfocused scanは通常のdirectory walkです。この場合、Gitのindexや`.gitignore`による候補絞り込みは使われません。scannerが定めた除外は引き続き適用されます。
- Gitを使えない場合や対象pathがrepository rootでない場合のfull scanもdirectory walkになり、`.gitignore`は適用されません。

## 6. 判断精度を上げるためのcontext設計

Jevの判断はモデルだけでなく、どの情報を渡すか、関連ファイルが同じ監査単位に入るか、正本や不要情報を見分けられるかに左右されます。現行実装では質問の形は固定されているため、利用者が改善しやすいのは主にcontextの質・近さ・noiseです。

```text
Question quality  狭く具体的な問い
Context quality   正本・仕様・実装・testが分かる
Context locality  関連情報が同じ監査範囲に集まる
Noise reduction   legacyや無関係な情報を減らす
```

### README・INDEX・project map

rootのREADME、`PROJECT_INDEX.md`、`docs/INDEX.md`などに、短い地図を置くと人間やLLMが関連資料を見つけやすくなります。INDEXは仕様全文の複製ではなく、正本と役割の場所を案内するnavigation layerとして使います。

```md
# Project Index

## Purpose
このrepositoryが何を実現するか

## Current canonical documents
- Main specification: `docs/SPEC.md`
- Current state: `CURRENT_STATE.md`

## Main areas
- `src/api/` — API入口
- `src/core/` — 中核ロジック
- `tests/` — 自動test

## Important relationships
- API contract → `docs/API.md` → `src/api/` → `tests/api/`

## Legacy / non-current
- `docs/archive/` — 過去資料。現行仕様ではない
```

これは一般的な例です。repositoryごとに必要な情報だけ記載し、全仕様・履歴・実装説明をINDEXへ詰め込まないでください。巨大化はtoken増加、truncation、更新負担、正本との矛盾につながります。

### INDEXは全batchへ自動共有されない

現行版は対象ファイルをbatchごとに分け、batch内のファイルだけをJevへ送ります。root INDEXを置いても、その本文が含まれていないbatchがINDEXを参照することはありません。INDEXだけで全batchの精度が上がるとは限りません。

関連ファイルを一緒に見つけやすくするには、次を組み合わせます。

- rootの短い地図と、主要moduleの局所README
- 仕様・実装・testの近接や明示的な参照
- Git rootでの日常的な`--changed-only`
- 意味的にまとまった範囲に絞るfocused scan

大きなrepositoryでは、局所READMEにmoduleの責務、主なファイル、外部との境界、対応仕様、関連testを短く記載します。例えば `jev-audit src/scheduler` のように範囲を指定できます。仕様と実装が別batchになる可能性は残るため、結果を読む際はpathsと正本を照合します。

### 正本・legacy・traceability

どの資料がcurrentか、過去資料が何に置き換えられたかを明示します。必要に応じて`CURRENT`、`DEPRECATED`、`ARCHIVED`、`SUPERSEDED BY ...`などを使い、過去資料は削除せず状態を示します。

可能な範囲で、仕様から実装とtestへ辿れるようにします。

```text
AUTH-01
Spec: docs/AUTH.md
Implementation: src/auth/
Tests: tests/auth/
```

完全なtraceability databaseは不要です。同じ知識をREADME、INDEX、Jev専用資料へ重複させず、正本を決めて他の資料から参照します。人間・各LLM・Jevのために別々の地図を大量に作ることも避けます。

## 7. batch・truncation・skipの限界

現行の既定値は次のとおりです。

| 設定 | 既定値 | 内容 |
| --- | ---: | --- |
| `max_file_chars` | 12,000 | 1ファイルから送る最大文字数 |
| `max_file_bytes` | 2,000,000 | これを超えるファイルをskip |
| `batch_chars` | 32,000 | batch分割の上限。各fileの文字数・path・固定overheadを収容できない値は拒否 |
| `workers` | 4 | 並列Jev request数の上限 |

batch分割は文字数を基準にしたもので、token数や意味上のまとまりではありません。仕様と実装が別batchになれば、直接比較できないことがあります。1ファイルはbatch分割時にさらに分割されないため、pathと固定overheadを含むsingle-item costが`batch_chars`を超える設定は拒否されます。必要なファイル同士を近くに配置し、変更範囲やfocused scanを活用してください。

Jev modelの既定値は`jev-1.13.0`です。`TYPESAFE_DEFAULT_MODEL`またはCLIの`--model`で明示的に上書きできます。既定値を更新する場合は、判定閾値との組み合わせを再評価してください。

既定の12,000文字を超えるテキストは、中央部分を省き、先頭と末尾にtruncation markerを挟んで送られます。省略された部分にだけ問題がある場合は見逃す可能性があります。既定の2,000,000 bytesを超えるファイルは`too_large`としてskipされます。

レポートの`skipped`には、binaryまたは対応できないencoding、sensitive file、lock/generated file、サイズ超過、削除済みファイルなど、監査対象に入らない理由が出ます。`.git`や`node_modules`等の特定directoryも対象外です。重要ファイルがskipされていないか確認し、skipがある状態で「repository全体を見た」と解釈しないでください。

既知のlock fileやbuild directory、Repository Baseの`.kinotch/` directoryは除外されますが、vendor、legacy、過去release資料、evidence、大量JSONなどが常に自動除外されるわけではありません。Git管理下にあり、scannerの除外条件にも該当しない資料はfull scanに入る場合があります。noiseを減らすには日常の`--changed-only`、focused scan、資料の状態表示を使います。Base自体を監査する場合は、`jev-audit .kinotch`のように明示的に対象を指定してください。

## 8. custom profileと閾値

bundled profileは`development`と`generic`です。profileは主に`local_status`の監査規則とcriteriaを指定します。一方、`risk`を構成する`concrete_issue`、`spec_mismatch`、`regression_risk`の3つのNoul質問は固定です。custom profileへ独自ruleを追加しても、そのrule専用のrisk scoreが作られるわけではありません。

custom profileを作る場合は、development、docs consistency、release readinessなど目的を絞ります。抽象的なruleを大量に詰めても精度向上は保証されません。既存profileで足りるなら増やす必要はありません。

上記の閾値は`aggregate.py`にある`jev-audit`独自のpolicyです。調整する場合は、Jevの結果と人間・LLMによる詳細確認結果を蓄積し、検出数、false positive、見逃しを評価します。YELLOWが多いという理由だけで閾値を上げないでください。

## 9. LLM・MCPとの組み合わせ

Jevの出力を使って詳細レビューの範囲を絞ります。

```text
jev-audit
  ↓
status・reason・trigger batch・pathsを確認
  ↓
該当ファイルと正本・関連testだけを読む
  ↓
人間またはCodex / Claude Code等で詳細レビュー
  ↓
必要なtestを実行
```

YELLOWはrisk値だけでなく、actionableを理由に出る場合もあります。status triggerのbatchとpathsを見て、必要なファイルだけをLLMへ渡してください。監査後にrepository全体をLLMへ再送すると、一次スクリーニングでcontextを絞る利点が小さくなります。

MCPから使う場合、日常の変更監査では`audit_directory`へrepository rootの絶対pathと`changed_only: true`を明示するのが確実です。結果を受け取った後も、CLIと同じ順序でstatus、reason、batch、pathsを確認し、必要な範囲を詳しく読みます。毎ターンfull scanする必要はありません。

## 10. セキュリティと外部送信

監査対象として読み込まれたテキストのpathと内容は、Jevを呼び出すため外部のTypeSafe APIへ送信されます。外部送信が許可されているrepositoryだけで使用してください。機密repositoryに使用できるかは、組織の規則と利用中の契約を確認して判断します。詳細は[TypeSafe AI Privacy Policy](https://typesafe.ai/legal/privacy-policy)や[Terms of Use](https://typesafe.ai/legal/terms)の現行版を確認してください。

`TYPESAFE_LOG_LEVEL=debug`やTypeSafe SDK loggerのDEBUGを有効にすると、SDKのwire loggingがrequest bodyをログへ出し、監査対象source本文がローカルログやログ収集基盤へ残る可能性があります。機密性のある監査ではDEBUG loggingを無効にしてください。

scannerは次の名前・拡張子のファイルを既定で除外します。

- `.env`、`.env.*`、`.envrc`、`.npmrc`、`.pypirc`、`.netrc`
- `credentials.json`、`secrets.json`、`id_rsa`、`id_ed25519`
- `*.key`、`*.pem`、`*.p12`、`*.pfx`、`*.jks`、`*.keystore`

生成レポート用の`.audit/` directoryも既定で除外されます。

この仕組みはファイル名・拡張子による除外で、完全なDLPではありません。例えば`config.py`や通常のJSON・ソースファイルに直接書かれたAPI keyは監査対象になり得ます。`.gitignore`等の標準除外規則が未追跡ファイルの候補除外に使われるのも、Git repository rootでの走査時に限られます。追跡済みファイルは`.gitignore`に追加しただけでは候補から外れません。

prompt injectionへの対策の一つとして、全4判断にはファイル本文内の命令文を監査対象データとして扱い、監査指示を変更する命令に従わないよう指示しています。ただし、adversarialな本文が意味判断へ影響しない保証ではなく、security scannerの代替にもなりません。

## 11. 実行時間とtoken効率

input tokenを減らすには、出力を削るより不要なstateを送らないことが基本です。

```text
changed-only
  ↓
意味的にまとまったfocused scan
  ↓
legacy・generated・無関係なnoiseを減らす
  ↓
full scanは節目に行う
  ↓
詳細LLMにはtrigger batchの関連範囲だけを渡す
```

`workers`の既定値は4です。増やすと複数batchを並行処理でき、wall-clock短縮につながる場合がありますが、batch数やinput token量は減りません。API rate limit、network、provider側の並列処理数に左右されるため、2・4・8などを実データで測って決めます。大きい値が常に速いとは限りません。

`max_file_chars`や`batch_chars`を変えると、送る内容やbatch境界も変わります。単に値を大きくすれば精度が上がるわけではなく、小さくすれば必要contextを欠く場合があります。`tokens`表示は実行結果で確認し、文字数をtoken数と同一視しないでください。

## 12. CI利用

現行CLIは`--fail-on never`、`--fail-on review`、`--fail-on rework`を受け付けます。

- `never`: 監査statusによる非0終了を行わない
- `rework`: RED / `rework`のみ非0終了にする
- `review`: YELLOW / `review`、RED / `rework`、UNKNOWN / `unknown`を非0終了にする

導入直後から`--fail-on review`でCIを止めると、YELLOWやUNKNOWNでbuildが止まります。まずは`never`で傾向を見るか、必要なら`rework`から始め、詳細確認の結果を蓄積してからgateを調整します。status由来の終了判定であり、API key不足や実行エラーは別途失敗します。

リポジトリのGitHub Actionsでは、通常suiteをPython 3.10〜3.14で実行し、別jobで`.[mcp,pilot]`をインストールしたMCP・Runtime・TypeSafe SDKのimportと同suiteを確認します。

## 13. 避ける使い方

- GREENだからtestや実操作確認を省く
- riskをバグの正解確率やrepository品質点として比較する
- 巨大repositoryを毎編集でfull scanする
- audit後に結局全repositoryをLLMへ再送する
- unknownを問題のriskと同一視する
- secret除外だけを根拠に機密repositoryへ使う
- INDEXを置けば全batchが内容を知ると考える
- custom profileへruleを大量に足せば精度が自動で上がると考える
- 同じ内容のJev専用文書やINDEXを際限なく増やす
- YELLOWが多いだけで閾値を上げる

## 14. Quick Reference

| 状況 | 推奨 |
| --- | --- |
| 普段の実装後 | repository rootで`jev-audit . --changed-only` |
| release前・大きな変更後 | full scanと通常のtestを行い、必要箇所を詳細確認 |
| YELLOW | `reason`のbatch・pathsを優先レビュー |
| RED | 修正候補として詳細レビューし、修正後にtest |
| UNKNOWN | contextまたは監査範囲を増やす |
| 大規模repository | changed-onlyを中心にし、節目でfull scan |
| 特定module | moduleの局所READMEとfocused scanを使う |
| context不足 | INDEX・局所READMEから正本と関連testを確認 |
| spec mismatchが多い | current / legacy / archiveとSSOTを確認 |
| CI導入初期 | `--fail-on never`または`--fail-on rework`から始める |
| 機密repository | 外部API送信が認められるか先に確認 |
