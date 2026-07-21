# convert_to_wp.py 仕様固定メモ

## 目的

`project-generator`で生成した静的HTML案件を、最小構成のWordPressテーマとして利用できる状態へ変換する。
対象は`website`、`shop`、`lp`である。

変換の中心は、header/footer共通化、WordPress URL化、asset enqueue、body class付与、現在ページnavの動的化である。
`template-parts`、`wp_nav_menu()`、loop、投稿取得、カスタムフィールドまでは扱わない。

## 対応テンプレートと生成ファイル

全テンプレートで次を生成する。

- `style.css`
- `index.php`
- `functions.php`
- `header.php`
- `footer.php`
- `.project-generator-wordpress.json`

元の静的HTMLやassetは削除せず、案件ディレクトリ内に残す。

### website

入力HTML:

- `index.html`
- `about.html`
- `service.html`
- `contact.html`

追加生成:

- `front-page.php`
- `page-about.php`
- `page-service.php`
- `page-contact.php`

### shop

入力HTML:

- `index.html`
- `products.html`
- `about.html`
- `contact.html`

追加生成:

- `front-page.php`
- `page-products.php`
- `page-about.php`
- `page-contact.php`

### lp

入力HTML:

- `index.html`

追加生成:

- `front-page.php`

## 変換処理

`convert_to_wp.py`は次を行う。

1. 同じ案件に属する全operationのtransaction残骸を検査する。
2. 対象案件、generation manifest、要求template、必須HTMLを検査する。
3. 既存WordPress生成物と所有権manifestを検査する。
4. 案件全体を`.案件名.wp-tmp-*`へコピーする。
5. staging内で既存のgenerator所有ファイルを除去する。
6. `header.php`、`footer.php`、`functions.php`、各ページPHPを生成する。
7. 生成ファイルのSHA-256を所有権manifestへ記録する。
8. stagingとlive案件をtransactionalに交換する。

変換途中で失敗した場合、live案件は交換しない。
forward swapとrollbackの両方に失敗した場合は、元例外と復旧例外を保持し、backup、staging、failedの位置を例外へ記録する。
この状態は`DirectoryTransactionRecoveryError`として通知する。

## 変換template契約

WordPress変換では`project-manifest.json`を必須で読み取り、`project.template`（generation template）とrequested template（`--template`）の一致を検査する。
`project-manifest.json`の欠落、不正JSON、不正schema、または不正な`project.template`はすべて停止条件とする。
generation manifestを持たない旧案件は、正しいtemplateを指定して`script.py`から再生成する必要がある。

再変換時は、`.project-generator-wordpress.json`の`template`もrequested templateと一致しなければならない。
`--force`でもtemplate不一致を許可しない。
この検査はtemplate migration機能ではなく、異なるtemplateによる誤変換を防ぐためのfail-closed契約である。

これらの不一致やmanifest不正は、staging作成とswapより前に検出する。
停止時は静的HTMLや既存案件を変更しない。

## header.php

`header.php`には次を含める。

- `<!doctype html>`から`<main>`直前までの共通header
- WordPress document title
- `wp_head()`
- `body_class('t-<template>')`
- skip-link
- site headerとnavigation

固定サイトタイトルリンクは次へ変換する。

```php
<a href="<?php echo esc_url( home_url( '/' ) ); ?>" class="site-title__link">
  <?php bloginfo( 'name' ); ?>
</a>
```

静的CSS `<link>`は削除し、`functions.php`のenqueueへ移す。

## footer.php

`footer.php`には次を含める。

- `<footer>...</footer>`
- `wp_footer()`
- `</body>`
- `</html>`

静的JavaScript `<script>`は削除し、`functions.php`のenqueueへ移す。

## 各ページPHP

各ページPHPは次の形を基本とする。

```php
<?php
add_filter(
  'body_class',
  static function ( $classes ) {
    $classes[] = 'p-home';
    return $classes;
  }
);
?>
<?php get_header(); ?>

<main>...</main>

<?php get_footer(); ?>
```

ページclassは次の規則で付与する。

- `index.html` → `p-home`
- その他 → `p-<HTMLファイル名のstem>`

`<main>...</main>`のsection構造は保持し、section単位のPHP分割は行わない。

## functions.php

次を実装する。

- `dist/css/main.css`の`wp_enqueue_style()`
- `dist/js/core/app.js`の`wp_enqueue_script()`
- `filemtime()`によるversion付与
- `script_loader_tag`による`type="module"`付与

assetが存在しない場合、versionは`null`とする。

## URLとasset path

### ページリンク

静的HTMLリンクを`home_url()`へ変換する。

website:

- `index.html` → `/`
- `about.html` → `/about/`
- `service.html` → `/service/`
- `contact.html` → `/contact/`

shop:

- `index.html` → `/`
- `products.html` → `/products/`
- `about.html` → `/about/`
- `contact.html` → `/contact/`

lp:

- `index.html` → `/`
- `service.html` → `/#offer`
- `contact.html` → `/#cta`

### asset

次の相対asset pathは`get_stylesheet_directory_uri()`ベースへ変換する。

- `dist/...`
- `assets/img/...`
- `img/...`

CSSとJavaScript本体はHTML内に直書きせずenqueueする。

## navigationの現在ページ状態

`<nav>...</nav>`内の対応リンクだけを動的化する。

- `index.html` → `is_front_page()`
- その他の対応HTML → `is_page( '<slug>' )`

現在ページの場合だけ次を出力する。

- `is-current` class
- `aria-current="page"`

静的HTMLに残っていた`is-current`と`aria-current="page"`は除去し、WordPress条件式へ置き換える。
`nav`外のリンクには現在ページ変換を適用しない。

## 所有権manifestと--force

`.project-generator-wordpress.json`は、generatorが管理するWordPress生成ファイルと各SHA-256を記録する。

`--force`で再変換できる条件は次のとおり。

- 所有権manifestが正常に読める。
- 既存のgenerator管理名ファイルがmanifestに記録されている。
- 既存ファイルのSHA-256が記録値と一致する。

次は`--force`でも上書き・削除しない。

- generator所有権を確認できない同名ファイル
- 生成後に編集されたファイル
- 管理範囲外またはtraversalを含むmanifest path
- 不正schema、kind、template、SHA-256を持つmanifest

manifestに記録された生成ファイルが欠落している場合は、再変換時に再生成できる。

## cross-operation transaction残骸

通常生成、`--refresh-dist`、WordPress変換は、操作種別を問わず同じ案件に属する未解決transaction残骸を共通scannerで横断検査する。
案件ディレクトリの隣にある次の残骸が対象となる。

- `.案件名.tmp-*`
- `.案件名.backup-*`
- `.案件名.failed-*`
- `.案件名.wp-tmp-*`
- `.案件名.wp-backup-*`
- `.案件名.wp-failed-*`

案件内にある次のdist／generation manifest transaction残骸も対象となる。

- `.dist.tmp-*`
- `.dist.backup-*`
- `.dist.failed-*`
- `.project-manifest.json.tmp-*`
- `.project-manifest.json.backup-*`
- `.project-manifest.json.failed-*`

別案件の残骸は対象外とする。
対象が一件でも存在すれば、通常生成、`--refresh-dist`、WordPress変換をすべて停止する。
残骸は自動削除しないため、内容確認と手動復旧が必要となる。
pre-swap cleanup失敗で残ったstagingも、次回scannerの停止対象になる。

正常交換後はbackupを削除する。
交換失敗後にrollbackが成功した場合は、failed候補を削除して元のswap例外を再送出する。
rollbackも失敗した場合は、復旧に必要な資産を残す。

## 実行例

```powershell
python script.py --template website --project wp-convert-check --force
python convert_to_wp.py --project wp-convert-check --template website
```

```powershell
python script.py --template shop --project shop-convert-check --force
python convert_to_wp.py --project shop-convert-check --template shop
```

```powershell
python script.py --template lp --project lp-convert-check --force
python convert_to_wp.py --project lp-convert-check --template lp
```

再変換時だけ`convert_to_wp.py`へ`--force`を付ける。

## 受入確認

- 対応3テンプレートを変換できる。
- 生成PHPが`php -l`を通る。
- `header.php`に静的CSS linkが残らない。
- `footer.php`に静的JS scriptが残らない。
- `wp_head()`と`wp_footer()`がある。
- `home_url()`、`bloginfo( 'name' )`、`body_class()`を使用する。
- 各ページPHPが`get_header()`、`<main>`、`get_footer()`を持つ。
- nav current状態が`is_front_page()`／`is_page()`で動的に切り替わる。
- 所有権外または編集済みWordPressファイルを`--force`でも保護する。
- transaction二重失敗時にbackup、staging、failedと両方の例外情報を保持する。

## 対象外

- `template-parts`
- `wp_nav_menu()`
- WordPress loop
- 投稿・固定ページの自動作成
- カスタムフィールド
- section単位のPHP分割
- WooCommerce等のEC機能
