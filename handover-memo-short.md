# ファイル名

handover-memo-short.md

## 短い引き継ぎメモ

### 今回できたこと

- `project-generator` の再構築を進め、テンプレを `website / shop / lp` の3系統に整理した
- `convert_to_wp.py` を作成し、静的HTMLから **最小 WordPress テーマ構成** へ変換できるようにした
- 対応済みテンプレ:
  - `website`
  - `shop`
  - `lp`
- 変換で出力される主なファイル:
  - `style.css`
  - `index.php`
  - `functions.php`
  - `header.php`
  - `footer.php`
  - `front-page.php`
  - `page-*.php`
- `functions.php` で CSS / JS を enqueue する方式へ統一
- `wp-stubs/style.css` と `wp-stubs/index.php` を用意し、`convert_to_wp.py` 実行時に自動生成されるようにした
- `style.css` の `Theme Name:` は案件名ベースで自動生成される
- `home_url()` / `bloginfo('name')` / `body_class()` へ変換する方針を固めた
- `lp` は 1ページ構成として、ページ内アンカーを維持する方針で変換できるようにした
- 仕様や運用メモを作成済み:
  - `convert-to-wp-spec.md`
  - `wp-theme-import-guide.md`
  - `tasks-guide.md`

### VS Code / Tasks

- `.vscode/settings.json` と `.vscode/extensions.json` を整備した
- 競合しやすい拡張機能は Workspace Disable 済み
- `tasks.json` に以下を整理済み
  - `pg: refresh dist`
  - `pg: regenerate website (force)`
  - `pg: regenerate shop (force)`
  - `pg: regenerate lp (force)`
  - `pg: convert website to wp`
  - `pg: convert shop to wp`
  - `pg: convert lp to wp`
  - `pg: website full flow`
  - `pg: shop full flow`
  - `pg: lp full flow`

### Local / WordPress 確認

- 新しく Local サイト `generator-wp-test` を作成した
- `website` の生成物を実際に WordPress テーマとして配置し、有効化できた
- `index.php` がないと「壊れているテーマ」扱いになることを確認し、`wp-stubs/index.php` 自動生成に反映済み
- 見た目確認で大きな崩れはなし
- `u-reveal u-reveal-up js-reveal` の動作確認も済み
- つまり、**Local 上では WordPress テーマとして表示確認できる状態** まで到達した

### GitHub

- 既存リポジトリ `project-generator` に push 済み
- コミット:
  - `8feb343`
- 内容:
  - テンプレ整理
  - WordPress 変換フロー追加
  - `wp-stubs` 追加
  - 各種 md ドキュメント追加

### いまの到達点

- generator → WordPress 変換 → Local テーマ確認
  まで一連の流れが通った
- 少なくとも `website` は Local 上で有効化・表示確認できた
- `shop / lp` も変換器としては対応済み

### 次にやる候補

- `shop` か `lp` も Local で実テーマ確認する
- README 冒頭に「今できること」を短く整理する
- 画像パスルールをさらに明文化する
- 必要なら Xserver 契約前メモを作る

### 補足

- Intelephense の `Undefined function` は、`project-generator` 内では WordPress 文脈がないため出る想定内警告
- 無視してよいのは主に WordPress 関数の未定義警告
- PHP 構文エラーや parse error は無視しない

- 画像パスルールをさらに明文化する
- 必要なら Xserver 契約前メモを作る

### 補足

- Intelephense の `Undefined function` は、`project-generator` 内では WordPress 文脈がないため出る想定内警告
- 無視してよいのは主に WordPress 関数の未定義警告
- PHP 構文エラーや parse error は無視しない
