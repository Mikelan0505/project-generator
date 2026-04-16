# ファイル名

convert-to-wp-spec.md

## convert_to_wp.py 仕様固定メモ

### 目的

`project-generator` で生成した静的 HTML を、**最小の WordPress テーマ構成** に変換する。
対象は現時点で `website` と `shop`。
目的は **読み込み系の PHP 化** と **本番寄りの最小 WordPress 化** であり、まだ `template-parts` 化や loop 化までは行わない。

---

## 対応テンプレート

- `website`
- `shop`

---

## 変換対象テンプレートと出力ファイル

### website

元ファイル:

- `index.html`
- `about.html`
- `service.html`
- `contact.html`

変換後:

- `header.php`
- `footer.php`
- `functions.php`
- `front-page.php`
- `page-about.php`
- `page-service.php`
- `page-contact.php`

### shop

元ファイル:

- `index.html`
- `products.html`
- `about.html`
- `contact.html`

変換後:

- `header.php`
- `footer.php`
- `functions.php`
- `front-page.php`
- `page-products.php`
- `page-about.php`
- `page-contact.php`

---

## convert_to_wp.py の役割

`convert_to_wp.py` は以下を行う。

1. 生成済みの HTML を読む
2. `header.php` / `footer.php` を切り出す
3. 各 `.html` を WordPress 用 `.php` に変換する
4. `functions.php` を生成する
5. CSS / JS の直書きを削除し、enqueue に寄せる
6. `.html` リンクを `home_url()` ベースに変換する
7. サイトタイトルを `bloginfo('name')` に変換する
8. `body_class()` をテンプレ別に付与する
9. `main` の中身はそのまま保持する

---

## 基本方針

### 読み込み共通化

各ページは最小で次の形を保つ。

    <?php get_header(); ?>

    <main class="main" id="main">
      ...
    </main>

    <?php get_footer(); ?>

### まだやらないこと

以下はまだ対象外。

- `template-parts` 化
- `wp_nav_menu()`
- WordPress loop
- 投稿取得
- カスタムフィールド
- current 自動切り替え
- セクション単位の PHP 分割

---

## header.php の仕様

### 共通で含めるもの

- `<!doctype html>`
- `<html lang="ja">`
- `<head>...</head>`
- `<?php wp_head(); ?>`
- `<body <?php body_class('...'); ?>>`
- skip-link
- `<header>...</header>`

### body_class

- `website` → `body_class('t-website')`
- `shop` → `body_class('t-shop')`

### サイトタイトル

固定文字列ではなく WordPress から取る。

    <a href="<?php echo esc_url( home_url( '/' ) ); ?>" class="site-title__link">
      <?php bloginfo( 'name' ); ?>
    </a>

### CSS の扱い

`header.php` に CSS の `<link>` は直書きしない。
CSS は `functions.php` の enqueue に寄せる。

---

## footer.php の仕様

### 共通で含めるもの

- `<footer>...</footer>`
- `<?php wp_footer(); ?>`
- `</body>`
- `</html>`

### JS の扱い

`footer.php` に JS の `<script>` は直書きしない。
JS は `functions.php` の enqueue に寄せる。

---

## functions.php の仕様

### 目的

- CSS / JS を enqueue する
- `filemtime()` ベースの版管理を行う
- `type="module"` を維持する

### 読み込むファイル

- `dist/css/main.css`
- `dist/js/core/app.js`

### 期待する役割

- `wp_enqueue_style()`
- `wp_enqueue_script()`
- `filemtime()` を使った version 付与
- `script_loader_tag` フィルタで `type="module"` を付与

### 例

    <?php
    function pg_asset_version( $relative_path ) {
      $file_path = get_stylesheet_directory() . $relative_path;
      if ( file_exists( $file_path ) ) {
        return (string) filemtime( $file_path );
      }
      return null;
    }

    function pg_enqueue_assets() {
      wp_enqueue_style(
        'pg-main',
        get_stylesheet_directory_uri() . '/dist/css/main.css',
        array(),
        pg_asset_version( '/dist/css/main.css' )
      );

      wp_enqueue_script(
        'pg-main',
        get_stylesheet_directory_uri() . '/dist/js/core/app.js',
        array(),
        pg_asset_version( '/dist/js/core/app.js' ),
        true
      );
    }
    add_action( 'wp_enqueue_scripts', 'pg_enqueue_assets' );

    function pg_add_module_attribute( $tag, $handle, $src ) {
      if ( 'pg-main' !== $handle ) {
        return $tag;
      }

      return sprintf(
        '<script type="module" src="%s"></script>',
        esc_url( $src )
      );
    }
    add_filter( 'script_loader_tag', 'pg_add_module_attribute', 10, 3 );

---

## パス変換ルール

### CSS / JS

相対パスは使わず、`functions.php` の enqueue に寄せる。

対象:

- `./dist/css/main.css`
- `./dist/js/core/app.js`

### 画像

画像相対パスは `get_stylesheet_directory_uri()` ベースに変換する。

対象例:

- `./assets/img/...`
- `/img/...`
- 必要に応じて画像パス全般

変換イメージ:

    <?php echo esc_url( get_stylesheet_directory_uri() . '/img/sample.webp' ); ?>

または `assets/img` を使う場合はその構成に合わせる。

---

## ナビリンク変換ルール

### website

- トップ → `home_url( '/' )`
- 会社案内 → `home_url( '/about/' )`
- サービス → `home_url( '/service/' )`
- お問い合わせ → `home_url( '/contact/' )`

### shop

- トップ → `home_url( '/' )`
- 商品一覧 → `home_url( '/products/' )`
- 店舗案内 → `home_url( '/about/' )`
- お問い合わせ → `home_url( '/contact/' )`

### 例

    <a href="<?php echo esc_url( home_url( '/' ) ); ?>">トップ</a>
    <a href="<?php echo esc_url( home_url( '/products/' ) ); ?>">商品一覧</a>
    <a href="<?php echo esc_url( home_url( '/about/' ) ); ?>">店舗案内</a>
    <a href="<?php echo esc_url( home_url( '/contact/' ) ); ?>">お問い合わせ</a>

---

## main の扱い

- 各ページの `<main>...</main>` は保持する
- section 分割はしない
- 各テンプレの本文構造は極力そのまま残す

---

## 確認項目

### website

以下のコマンドで確認する。

    python script.py --template website --project wp-convert-check -f
    python convert_to_wp.py --project wp-convert-check --template website

確認対象:

- `functions.php`
- `header.php`
- `footer.php`
- `front-page.php`
- `page-about.php`
- `page-service.php`
- `page-contact.php`

確認内容:

- `functions.php` に enqueue がある
- `header.php` に CSS 直書きがない
- `footer.php` に JS 直書きがない
- `wp_head()` / `wp_footer()` がある
- `home_url()` が使われている
- `bloginfo('name')` が使われている
- `body_class('t-website')` になっている
- 各ページが `get_header()` / `<main>` / `get_footer()` の最小形になっている

### shop

以下のコマンドで確認する。

    python script.py --template shop --project shop-convert-check -f
    python convert_to_wp.py --project shop-convert-check --template shop

確認対象:

- `functions.php`
- `header.php`
- `footer.php`
- `front-page.php`
- `page-products.php`
- `page-about.php`
- `page-contact.php`

確認内容:

- `functions.php` に enqueue がある
- `header.php` に CSS 直書きがない
- `footer.php` に JS 直書きがない
- `wp_head()` / `wp_footer()` がある
- `home_url()` が使われている
- `bloginfo('name')` が使われている
- `body_class('t-shop')` になっている
- `products` が `home_url('/products/')` になっている
- 各ページが `get_header()` / `<main>` / `get_footer()` の最小形になっている

---

## 現時点の到達点

- `website` は最小の本番寄り WordPress 化ができている
- `shop` も同じ変換思想で WordPress 化できている
- `functions.php` 生成と enqueue 方針は固まった
- 読み込み共通化の仕組みはできた

---

## 次段階で検討するもの

まだ未着手だが、今後の候補として以下がある。

- `lp` の WordPress 化対応
- `template-parts` 化
- `wp_nav_menu()` 対応
- current 自動切り替え
- セクション単位の変換
- loop / 投稿取得
- カスタムフィールド対応

ただし、現時点ではまだこの段階には進めない。
まずは `website` / `shop` の **最小 WordPress 変換仕様を固定する** ことを優先する。

---

## 現時点の到達点

- `website` は最小の本番寄り WordPress 化ができている
- `shop` も同じ変換思想で WordPress 化できている
- `functions.php` 生成と enqueue 方針は固まった
- 読み込み共通化の仕組みはできた

---

## 次段階で検討するもの

まだ未着手だが、今後の候補として以下がある。

- `lp` の WordPress 化対応
- `template-parts` 化
- `wp_nav_menu()` 対応
- current 自動切り替え
- セクション単位の変換
- loop / 投稿取得
- カスタムフィールド対応

ただし、現時点ではまだこの段階には進めない。
まずは `website` / `shop` の **最小 WordPress 変換仕様を固定する** ことを優先する。
