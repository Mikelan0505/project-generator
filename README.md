project-generator

templates から案件フォルダを生成し、outputs 配下の既存案件を同期
(CSS同期 + HTML矯正 + body class 付与) するツール。

==================================================

目的

- 案件フォルダの出力先を outputs に統一する
- 既存案件を sync で一括整形・同期できる前提を作る
- 生成物(outputs)は Git 管理外で運用する

==================================================

ディレクトリ構成

project-generator/
script.py
templates/
corporate/
event/
service-lp/
lp/
outputs/ (generated / git ignored)
project-name/
assets/css/style.css
\*.html
.pg_template

==================================================

使い方

実行方法

python script.py

引数なしで実行するとメニューが表示される。

---

new (新規生成)

1. メニューで「1: new」を選択
2. テンプレを選択
   corporate / event / service-lp / lp
3. 案件名・電話番号などを入力

生成先:
outputs/project-name/

---

sync (同期: 全処理)

1. メニューで「2: sync」を選択
2. outputs 配下から案件フォルダを選択
3. 実行確認で y を入力

sync で行われる処理:

- バックアップ作成
  outputs/project-name\_\_backup_YYYYmmdd-HHMMSS.zip

- CSS 同期
  sass-starter-exiga/dist/css/main.css
  -> outputs/project-name/assets/css/style.css

- HTML 矯正
  テンプレ index.html の header / footer を正として統一

- body class 付与
  ファイル名から自動付与
  index.html -> page-home
  about.html -> page-about

==================================================

規約

outputs は完成形

- CSS / header / footer / body class が揃っている状態が正
- 崩れた場合は sync を再実行して整える

templates は素材

- templates 側 HTML に body class が無くても問題なし
- 完成形への矯正は sync が責任を持つ

==================================================

.pg_template について

- outputs/project-name/.pg_template にテンプレ名を1行で記録
- sync が使用テンプレを自動判定するためのメモ
- outputs が Git 管理外なら .pg_template も Git 管理外でOK

==================================================

.gitignore 推奨設定

outputs/\*\*
.vscode/

==================================================

想定用途

- LP / コーポレート / イベントページの量産
- テンプレ修正後の既存案件一括同期
- 手作業による HTML 崩れの矯正

---

## HTML 運用方針（重要）

このプロジェクトでは、HTML / CSS の運用を以下の方針で固定しています。

### 基本方針

- **既存の HTML を「正」とする**
- 無理な共通化・抽象化は行わない
- 必要になったときに「引っ張ってこれる」構成を優先する

つまり、

- 今すでに exiga と噛み合っている HTML は壊さない
- 再利用したい構成は「保管庫（catalog）」にそのまま保存する

という運用を前提としています。

---

### catalog（保管庫）の役割

`templates/**/_catalog.html` は、以下の目的でのみ使用します。

- 実案件で使った section をそのまま保管する
- 「また使えそう」と思った構成をコピペで保存する
- **class 名・構造は一切変更しない**

catalog は以下を目的としません。

- 抽象化
- 共通パーツ化
- 設計の再定義

あくまで **HTML スニペットの保管庫**です。

---

### HTML の正解ルール

HTML 側では、exiga 側の設計を正とします。

- コンテナは `l-container`
- `main` は全ページ共通で `class="main"`
- 見出し構造は以下に統一

---

### 文法チェック観点（Python / SCSS）

**Python**

- インデント整合（タブ混在・ブロック崩れ）
- `:` の付け忘れ（if/for/def/class/try/except）
- 括弧・クォートの閉じ忘れ（`()[]{}` / `"'"""`）
- `=` と `==`、`is None` など演算子・予約語の誤用
- try/except/else/finally 構文の並び・書き方ミス

**SCSS**

- `{}` と `;` の整合（ネスト含む）
- `@use/@forward` のパス・名前空間、公開トークンの不足
- 変数・mapキーの存在（`map.get` の key / null）
- `&` を含むネストの意図ズレ（hover / modifier）
- 単位混在・演算の誤り（`math.div` / px+rem など）
