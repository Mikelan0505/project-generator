# ファイル名

wp-theme-import-guide.md

## 生成した PHP 一式を WordPress テーマに持っていく手順書

この手順書は、`project-generator` の `convert_to_wp.py` で生成した PHP 一式を、実際の WordPress テーマとして使い始めるための最小手順をまとめたものです。
対象は現時点で `website` / `shop` / `lp` の3テンプレです。

---

## 前提

`convert_to_wp.py` により、少なくとも以下のようなファイルが生成されている前提です。

### website

- `functions.php`
- `header.php`
- `footer.php`
- `front-page.php`
- `page-about.php`
- `page-service.php`
- `page-contact.php`

### shop

- `functions.php`
- `header.php`
- `footer.php`
- `front-page.php`
- `page-products.php`
- `page-about.php`
- `page-contact.php`

### lp

- `functions.php`
- `header.php`
- `footer.php`
- `front-page.php`

また、`dist/css/main.css` と `dist/js/core/app.js` を読み込む前提で `functions.php` が生成されている。

---

## 目的

最終的に、WordPress テーマフォルダ内に以下のような構成を作る。

    your-theme/
      style.css
      functions.php
      header.php
      footer.php
      front-page.php
      page-about.php
      page-service.php
      page-contact.php
      dist/
        css/
          main.css
        js/
          core/
            app.js
      assets/
      img/

※ `shop` や `lp` の場合はページファイルが少し変わる。

---

## 全体の流れ

1. `project-generator` で HTML を生成する
2. `convert_to_wp.py` で PHP 一式を生成する
3. WordPress テーマフォルダを作る
4. 生成された PHP ファイルをテーマへコピーする
5. `dist` と画像類をテーマへコピーする
6. `style.css` を作る
7. WordPress 管理画面でテーマを有効化する
8. 固定ページやフロントページ設定を行う
9. 表示確認する

---

## 手順 1: project-generator で生成する

### website の例

    python script.py --template website --project my-site -f
    python convert_to_wp.py --project my-site --template website

### shop の例

    python script.py --template shop --project my-shop -f
    python convert_to_wp.py --project my-shop --template shop

### lp の例

    python script.py --template lp --project my-lp -f
    python convert_to_wp.py --project my-lp --template lp

生成先は通常 `outputs/<project-name>/`。

---

## 手順 2: 生成物を確認する

`outputs/<project-name>/` の中に、少なくとも以下があることを確認する。

### website

- `functions.php`
- `header.php`
- `footer.php`
- `front-page.php`
- `page-about.php`
- `page-service.php`
- `page-contact.php`

### shop

- `functions.php`
- `header.php`
- `footer.php`
- `front-page.php`
- `page-products.php`
- `page-about.php`
- `page-contact.php`

### lp

- `functions.php`
- `header.php`
- `footer.php`
- `front-page.php`

また、元の HTML と `dist`、画像フォルダも残っているか確認する。

---

## 手順 3: WordPress テーマフォルダを作る

WordPress のテーマディレクトリに新しいテーマフォルダを作る。

例:

    wp-content/themes/my-theme/

Local を使っている場合の例:

    C:\Users\ユーザー名\Local Sites\サイト名\app\public\wp-content\themes\my-theme\

---

## 手順 4: PHP ファイルをテーマへコピーする

`outputs/<project-name>/` から、生成された PHP ファイルを新しいテーマフォルダへコピーする。

### website の場合

コピー対象:

- `functions.php`
- `header.php`
- `footer.php`
- `front-page.php`
- `page-about.php`
- `page-service.php`
- `page-contact.php`

### shop の場合

コピー対象:

- `functions.php`
- `header.php`
- `footer.php`
- `front-page.php`
- `page-products.php`
- `page-about.php`
- `page-contact.php`

### lp の場合

コピー対象:

- `functions.php`
- `header.php`
- `footer.php`
- `front-page.php`

---

## 手順 5: dist と画像をコピーする

`functions.php` は以下を前提にしている。

- `dist/css/main.css`
- `dist/js/core/app.js`

そのため、テーマフォルダ内にも同じ構成で `dist` を置く必要がある。

### コピー対象例

- `outputs/<project-name>/dist/css/main.css`
- `outputs/<project-name>/dist/js/core/app.js`

### コピー先例

    my-theme/
      dist/
        css/
          main.css
        js/
          core/
            app.js

画像パスも `get_stylesheet_directory_uri()` ベースなので、
HTML 内で使っていた画像フォルダもテーマ内に同じ構成で置く。

たとえば、元で `assets/img` を使っていたなら、

    my-theme/
      assets/
        img/

または、`/img/...` を使っているなら

    my-theme/
      img/

に合わせて置く。

### 注意

`convert_to_wp.py` がどういう画像パスへ変換したかに合わせて、テーマ側のフォルダ構成を揃えること。

---

## 手順 6: style.css を作る

WordPress テーマとして認識させるために、テーマ直下へ `style.css` を作る。

最小でよいので、まずはこれで十分。

    /*
    Theme Name: My Theme
    */

ファイル:

    my-theme/style.css

### 補足

ここでは CSS 本体は `dist/css/main.css` を enqueue しているため、`style.css` はテーマ認識用と割り切ってよい。

---

## 手順 7: テーマを有効化する

WordPress 管理画面へ入り、

- 外観
- テーマ

から新しいテーマを有効化する。

---

## 手順 8: 固定ページを作る

### website の場合

必要な固定ページを作る。

- about
- service
- contact

スラッグ例:

- `about`
- `service`
- `contact`

### shop の場合

必要な固定ページを作る。

- products
- about
- contact

スラッグ例:

- `products`
- `about`
- `contact`

### lp の場合

通常は 1ページなので固定ページは必須ではない。
`front-page.php` だけで始められる。

---

## 手順 9: フロントページを設定する

WordPress 管理画面で

- 設定
- 表示設定

へ行き、

- ホームページの表示
- 固定ページ

を選ぶ。

フロントページ用のページを必要に応じて設定する。

### 補足

`front-page.php` がある場合、WordPress はトップ表示時にこれを優先して使う。
ただし運用上、固定ページ設定も合わせて整えておくとわかりやすい。

---

## 手順 10: 表示確認する

最低限、以下を確認する。

### 共通

- ヘッダーが出る
- フッターが出る
- CSS が当たる
- JS が動く
- 画像が出る
- Console に致命的なエラーがない

### website

- トップが `front-page.php` で出る
- `/about/`
- `/service/`
- `/contact/`
  のリンクが正しく動く

### shop

- トップが `front-page.php` で出る
- `/products/`
- `/about/`
- `/contact/`
  のリンクが正しく動く

### lp

- トップが `front-page.php` で出る
- ページ内アンカーが正しく飛ぶ
- `#problem` / `#faq` / `#cta` などが壊れていない

---

## 現時点でやらないこと

この手順ではまだ以下は行わない。

- `template-parts` 化
- `wp_nav_menu()` 化
- current の自動切り替え
- WordPress loop
- 投稿取得
- カスタムフィールド
- 管理画面からのコンテンツ編集対応
- ACF 連携

今はあくまで **静的HTMLベースの見た目を、最小の WordPress テーマ構成へ持っていく段階** と考える。

---

## 変換後のファイルの役割

### header.php

- `<!doctype html>` から `<header>` までを持つ
- `wp_head()` を含む
- `body_class()` を含む

### footer.php

- `<footer>` から `</html>` までを持つ
- `wp_footer()` を含む

### functions.php

- CSS / JS を enqueue する
- `filemtime()` で版管理する
- `type="module"` を保つ

### front-page.php / page-\*.php

- `get_header()`
- `<main>...</main>`
- `get_footer()`
  の最小構成

---

## つまずきやすい点

### 1. CSS が効かない

原因候補:

- `dist/css/main.css` をテーマ内へコピーしていない
- テーマフォルダ内の構成が `functions.php` の想定と違う

### 2. JS が動かない

原因候補:

- `dist/js/core/app.js` をコピーしていない
- `type="module"` が正しく出ていない
- Console エラーが出ている

### 3. 画像が出ない

原因候補:

- 画像フォルダの配置先が違う
- `convert_to_wp.py` の変換先とテーマ内構成が合っていない

### 4. about / service / products が開かない

原因候補:

- 固定ページを作っていない
- スラッグが想定と違う
- `home_url()` のリンク先に合うページがない

### 5. テーマが表示されない

原因候補:

- `style.css` がない
- `Theme Name:` コメントがない

---

## 最小チェックリスト

### 共通

- [ ] `style.css` を作った
- [ ] `functions.php` を置いた
- [ ] `header.php` を置いた
- [ ] `footer.php` を置いた
- [ ] `dist/css/main.css` を置いた
- [ ] `dist/js/core/app.js` を置いた
- [ ] 画像フォルダを置いた
- [ ] テーマを有効化した

### website

- [ ] `front-page.php` を置いた
- [ ] `page-about.php` を置いた
- [ ] `page-service.php` を置いた
- [ ] `page-contact.php` を置いた

### shop

- [ ] `front-page.php` を置いた
- [ ] `page-products.php` を置いた
- [ ] `page-about.php` を置いた
- [ ] `page-contact.php` を置いた

### lp

- [ ] `front-page.php` を置いた

---

## 現時点の結論

`convert_to_wp.py` で生成した PHP 一式は、
**そのまま WordPress テーマの最小土台として持ち込める段階** にある。

ただし、これはまだ **読み込み系だけの最小テーマ化** であり、
今後必要に応じて

- `template-parts`
- `wp_nav_menu()`
- loop
- カスタムフィールド

へ進めていく。
ーマを有効化した

### website

- [ ] `front-page.php` を置いた
- [ ] `page-about.php` を置いた
- [ ] `page-service.php` を置いた
- [ ] `page-contact.php` を置いた

### shop

- [ ] `front-page.php` を置いた
- [ ] `page-products.php` を置いた
- [ ] `page-about.php` を置いた
- [ ] `page-contact.php` を置いた

### lp

- [ ] `front-page.php` を置いた

---

## 現時点の結論

`convert_to_wp.py` で生成した PHP 一式は、
**そのまま WordPress テーマの最小土台として持ち込める段階** にある。

ただし、これはまだ **読み込み系だけの最小テーマ化** であり、
今後必要に応じて

- `template-parts`
- `wp_nav_menu()`
- loop
- カスタムフィールド

へ進めていく。
