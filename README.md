# project-generator

`project-generator` は、案件開始時の土台を素早く出力するための仕事用スターターテンプレ生成ツールです。

旧来の素材保管庫や sync 前提の運用には戻さず、今回は「最初のたたき台をきれいに出す」ことに用途を絞っています。スタイルと挙動は、同階層にある `sass-starter-exiga` の `dist` を利用します。

## 目的

- `website` `lp` `shop` の最小スターターを案件ごとに出力する
- HTML の初期骨組みをすぐ編集できる状態で用意する
- `sass-starter-exiga/dist/css` と `dist/js` を生成先へコピーする

## テンプレの種類

- `website`
  - コーポレート・事業紹介向け
  - `index.html`
  - `about.html`
  - `service.html`
  - `contact.html`
- `lp`
  - 1ページ完結の訴求向け
  - `index.html`
- `shop`
  - 店舗・物販向け
  - 商品カテゴリ、商品カード、価格、営業時間、アクセス、来店相談導線が主役
  - `index.html`
  - `products.html`
  - `about.html`
  - `contact.html`

## ディレクトリ構成

```text
project-generator/
├─ docs/
│  └─ project-generator-handover.md
├─ outputs/
├─ templates/
│  ├─ lp/
│  │  ├─ assets/
│  │  │  └─ img/
│  │  └─ index.html
│  ├─ shop/
│  │  ├─ assets/
│  │  │  └─ img/
│  │  ├─ index.html
│  │  ├─ products.html
│  │  ├─ about.html
│  │  └─ contact.html
│  └─ website/
│     ├─ assets/
│     │  └─ img/
│     ├─ index.html
│     ├─ about.html
│     ├─ service.html
│     └─ contact.html
├─ wp-stubs/
│  ├─ style.css
│  └─ index.php
├─ convert_to_wp.py
├─ README.md
└─ script.py
```

生成後のイメージ:

```text
outputs/<project-name>/
├─ index.html
├─ about.html          # website / shop
├─ service.html        # website のみ
├─ products.html       # shop のみ
├─ contact.html        # website / shop
├─ assets/
│  └─ img/
└─ dist/
   ├─ css/
   └─ js/
```

PHP 変換後のイメージ:

```text
outputs/<project-name>/
├─ index.html
├─ about.html
├─ service.html
├─ contact.html
├─ style.css
├─ index.php
├─ functions.php
├─ header.php
├─ footer.php
├─ front-page.php
├─ page-about.php
├─ page-service.php
├─ page-contact.php
├─ assets/
│  └─ img/
└─ dist/
   ├─ css/
   └─ js/
```

shop を PHP 変換した後のイメージ:

```text
outputs/<project-name>/
├─ index.html
├─ products.html
├─ about.html
├─ contact.html
├─ style.css
├─ index.php
├─ functions.php
├─ header.php
├─ footer.php
├─ front-page.php
├─ page-products.php
├─ page-about.php
├─ page-contact.php
├─ assets/
│  └─ img/
└─ dist/
   ├─ css/
   └─ js/
```

lp を PHP 変換した後のイメージ:

```text
outputs/<project-name>/
├─ index.html
├─ style.css
├─ index.php
├─ functions.php
├─ header.php
├─ footer.php
├─ front-page.php
├─ assets/
│  └─ img/
└─ dist/
   ├─ css/
   └─ js/
```

## 使い方

対話入力で生成する場合:

```bash
python script.py
```

引数で指定する場合:

```bash
python script.py --template website --project sample-site
```

短縮形:

```bash
python script.py -t website -p sample-site
```

既存出力を上書きする場合:

```bash
python script.py -t lp -p sample-lp -f
```

`shop` を生成する場合:

```bash
python script.py -t shop -p sample-shop
```

### 最小 PHP 化

生成済みの `website` / `shop` / `lp` 案件を、header / footer 共通化だけ行う最小構成の PHP テンプレへ変換できます。

```bash
python convert_to_wp.py --project sample-site --template website
python convert_to_wp.py --project sample-shop --template shop
python convert_to_wp.py --project sample-lp --template lp
```

この変換は `script.py` には混ぜず、別スクリプト `convert_to_wp.py` で行います。現在の対応範囲は以下です。

- `website` `shop` `lp` に対応
- `website`: `index.html` `about.html` `service.html` `contact.html` を読む
- `shop`: `index.html` `products.html` `about.html` `contact.html` を読む
- `lp`: `index.html` を読む
- `functions.php` `header.php` `footer.php` と各 `page-*.php` を生成する
- `wp-stubs/style.css` をテンプレートとして読み、`Theme Name:` を案件名ベースで差し替えて `style.css` を生成する
- `wp-stubs/index.php` を最小フォールバックとして `index.php` にコピーする
- `get_stylesheet_directory_uri()` を使って CSS / JS / 画像パスを WordPress 用に寄せる
- `home_url()` を使って `.html` リンクを固定スラッグ前提の WordPress URL に寄せる
- サイトタイトルリンクは `bloginfo('name')` と `home_url('/')` を使う
- `functions.php` で CSS / JS を enqueue し、`header.php` / `footer.php` には直書きしない
- `lp` のページ内アンカーはそのまま保持する
- 各ページは `<?php get_header(); ?>` と `<?php get_footer(); ?>` の最小形に置き換える
- `main` 内の section 分割や `template-parts` 化はまだ行わない

### dist 更新

生成済み案件の `dist/css` と `dist/js` を最新化したい場合:

```bash
python script.py -r -p sample-site
```

これは `sass-starter-exiga/dist/css` と `sass-starter-exiga/dist/js` を、既存の `outputs/sample-site/dist/` に再コピーするためのコマンドです。HTML やテンプレ本文は変更しません。

## script.py がやること

- テンプレ選択
- 案件名入力
- `outputs/` 配下に案件フォルダ生成
- テンプレ複製
- `{{PROJECT}}` `{{DATE}}` `{{PAGE_TITLE}}` の置換
- body class の自動付与
  - `website/index.html` -> `t-website p-home`
  - `website/about.html` -> `t-website p-about`
  - `website/service.html` -> `t-website p-service`
  - `website/contact.html` -> `t-website p-contact`
  - `lp/index.html` -> `t-lp p-home`
  - `shop/index.html` -> `t-shop p-home`
  - `shop/products.html` -> `t-shop p-products`
  - `shop/about.html` -> `t-shop p-about`
  - `shop/contact.html` -> `t-shop p-contact`
- HTML の軽い正規化
  - `<main class="main">` を保証
  - CSS の参照先を `./dist/css/main.css` に正規化
  - JS の参照先を `./dist/js/core/app.js` に正規化
- `sass-starter-exiga/dist/css` と `sass-starter-exiga/dist/js` を生成先にコピー
- `--refresh-dist` 実行時は既存案件の `dist/css` と `dist/js` だけを再コピー

## convert_to_wp.py がやること

- 生成済みの `outputs/<project-name>/` を読む
- 現在は `website` `shop` `lp` を対象にする
- `index.html` の外枠から `header.php` と `footer.php` を切り出す
- 各 HTML の `<main>...</main>` をそのまま各 PHP ファイルへ残す
- `functions.php` `front-page.php` と各 `page-*.php` を生成する
- `wp-stubs/style.css` から案件名入りの `style.css` を生成する
- `wp-stubs/index.php` を `index.php` としてコピーする
- `get_stylesheet_directory_uri()` で CSS / JS / 画像の相対パスを WordPress 用に置き換える
- `home_url()` で `.html` リンクを WordPress 用リンクへ置き換える
- サイトタイトルリンクを `bloginfo('name')` と `home_url('/')` に置き換える
- CSS / JS の直書きを消し、`functions.php` の enqueue に寄せる
- `lp` のページ内アンカーはそのまま維持する
- `get_template_part()` や `template-parts` 化はまだ行わない

## exiga の dist を使う前提

このツールは、ワークスペース内で `project-generator` と `sass-starter-exiga` が同階層にある前提です。

```text
GitHub/
├─ project-generator/
└─ sass-starter-exiga/
```

`script.py` は `sass-starter-exiga/dist/css` と `sass-starter-exiga/dist/js` を参照して生成先へコピーします。

## outputs について

`outputs/` は生成物置き場です。Git 管理外で扱う想定です。

## 今回採用していないもの

- sync モード
- 既存案件の再同期
- header / footer の後から矯正
- `.pg_template`
- catalog 保管庫思想
- 重い HTML 補正処理
- カート、決済、注文フローなどの本格EC機能

必要になったら将来拡張できますが、現時点では最小構成のまま保つ方針です。
