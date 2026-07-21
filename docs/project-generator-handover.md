# project-generator handover

## 概要

`project-generator` は、案件開始時の土台を出力するための仕事用スターターテンプレ生成ツールです。

このリポジトリでは、素材保管庫や後から同期して整える思想には戻さず、最初に触りやすい HTML をまとめて生成することを目的にしています。

スタイルと挙動は、同階層にある `sass-starter-exiga/dist` を利用します。

## 現在の方針

- generator は「案件開始時の土台を出力するもの」
- HTML は `project-generator/templates/` 側で持つ
- CSS / JS は `sass-starter-exiga/dist/css` と `dist/js` を使う
- body class や `<main class="main">` などの最低限の整形は generator 側で行う
- PHP 対応は `script.py` に混ぜず、別スクリプトから始める
- 最初の PHP 対応は header / footer の読み込み共通化だけに絞る
- 最小 PHP 化でも記法は WordPress 本番寄りに寄せる
- sync、catalog、重い後補正には戻さない

## 現在のテンプレ

### website

会社紹介・事業紹介向けの4ページ構成です。

- `index.html`
- `about.html`
- `service.html`
- `contact.html`

### lp

1ページ完結の訴求向けテンプレです。

- `index.html`

### shop

今回追加した、店舗・物販向けの4ページ構成テンプレです。

- `index.html`
- `products.html`
- `about.html`
- `contact.html`

`shop` は特定業種専用ではなく、以下のような店舗へ流用できる想定です。

- ケーキ店
- 焼き菓子店
- コーヒー豆店
- 雑貨店
- ギフトショップ
- 小規模物販店

主役にしている情報は以下です。

- 商品カテゴリ
- 商品カード
- 価格表示
- 店舗情報
- 営業時間
- アクセス
- 来店 / 問い合わせ / 取り置き相談導線

本格ECではなく、あくまで「店舗 + 商品訴求」の最小スターターとして止めています。

## shop テンプレのページ構成

### index.html

店舗トップページです。

- header
- hero
- concept
- featured products
- category list
- shop info
- cta
- footer

### products.html

商品一覧ページです。カテゴリ別に並べやすく、商品名、価格、短い説明を整理できる構成にしています。

- header
- page hero
- category nav
- product grid
- guide
- cta
- footer

### about.html

店舗紹介ページです。店の背景、こだわり、営業時間、アクセスを整理します。

- header
- page hero
- store concept
- commitment
- access / business hours
- cta
- footer

### contact.html

問い合わせページです。商品相談、取り置き相談、来店前相談を受ける最小フォーム構成です。

- header
- page hero
- contact intro
- form
- footer

## body class ルール

テンプレ種別 class + ページ class を自動付与します。

### website

- `index.html` -> `t-website p-home`
- `about.html` -> `t-website p-about`
- `service.html` -> `t-website p-service`
- `contact.html` -> `t-website p-contact`

### lp

- `index.html` -> `t-lp p-home`

### shop

- `index.html` -> `t-shop p-home`
- `products.html` -> `t-shop p-products`
- `about.html` -> `t-shop p-about`
- `contact.html` -> `t-shop p-contact`

## script.py の役割

`script.py` は軽量版です。現在の主な責務は以下です。

- テンプレ選択
- 案件名入力
- `outputs/` 配下に案件フォルダ生成
- テンプレ複製
- プレースホルダ置換
- body class 自動付与
- CSS link の軽い正規化
- `<main class="main">` の軽い正規化
- `sass-starter-exiga/dist/css` と `dist/js` のコピー
- `--refresh-dist` による既存案件の dist 更新

## script.py の引数

### 新規生成

```bash
python script.py --template website --project sample-site
python script.py -t shop -p sample-shop
```

### 上書き生成

```bash
python script.py -t lp -p sample-lp -f
```

### dist 更新

```bash
python script.py --refresh-dist --project sample-site
python script.py -r -p sample-site
```

これは `sass-starter-exiga/dist/css` と `dist/js` を、既存の `outputs/<project-name>/dist/` に再コピーするだけの軽量コマンドです。

以下はやりません。

- HTML の再整形
- body class の再付与
- header / footer の差し替え
- `.pg_template`
- catalog
- template 再コピー
- 旧 sync 処理

## convert_to_wp.py の役割

`convert_to_wp.py` は、生成済み HTML を最小構成の WordPress 風 PHP テンプレへ変換するための別スクリプトです。現在の責務は以下です。

- `outputs/<project-name>/` を読む
- `website` `shop` `lp` を対象にする
- `website`: `index.html` `about.html` `service.html` `contact.html` を読む
- `shop`: `index.html` `products.html` `about.html` `contact.html` を読む
- `lp`: `index.html` を読む
- `functions.php` `header.php` `footer.php` `front-page.php` と各 `page-*.php` を生成する
- `wp-stubs/style.css` をテンプレートとして読み、`Theme Name:` を案件名ベースで差し替えて `style.css` を生成する
- `wp-stubs/index.php` を最小フォールバックとして `index.php` にコピーする
- `index.html` の外枠から `header.php` と `footer.php` を切り出す
- 各ページの `<main>...</main>` はそのまま残す
- `get_stylesheet_directory_uri()` で CSS / JS / 画像パスを WordPress 用に置き換える
- `home_url()` で `.html` リンクを WordPress 用の固定スラッグ URL に置き換える
- サイトタイトルリンクを `bloginfo('name')` と `home_url('/')` に置き換える
- CSS / JS の直書きはやめ、`functions.php` の enqueue に寄せる
- `lp` のページ内アンカーはそのまま維持する
- `template-parts` 化や `get_template_part()` はまだ行わない

## convert_to_wp.py の引数

```bash
python convert_to_wp.py --project sample-site --template website
python convert_to_wp.py --project sample-shop --template shop
python convert_to_wp.py --project sample-lp --template lp
```

これは読み込み系だけを PHP 化する最小コマンドです。まだ WordPress ループ、投稿取得、`functions.php` 連携までは進めません。

## ディレクトリ構成

```text
project-generator/
├─ docs/
│  └─ project-generator-handover.md
├─ outputs/
├─ templates/
│  ├─ lp/
│  ├─ shop/
│  └─ website/
├─ wp-stubs/
├─ convert_to_wp.py
├─ README.md
└─ script.py
```

## 生成後のイメージ

### website

```text
outputs/<project-name>/
├─ index.html
├─ about.html
├─ service.html
├─ contact.html
├─ assets/
│  └─ img/
└─ dist/
   ├─ css/
   └─ js/
```

### website を PHP 化した後

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

### shop を PHP 化した後

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

### lp

```text
outputs/<project-name>/
├─ index.html
├─ assets/
│  └─ img/
└─ dist/
   ├─ css/
   └─ js/
```

### lp を PHP 化した後

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

### shop

```text
outputs/<project-name>/
├─ index.html
├─ products.html
├─ about.html
├─ contact.html
├─ assets/
│  └─ img/
└─ dist/
   ├─ css/
   └─ js/
```

## 採用していないもの

- sync モード
- 既存案件の再同期
- header / footer の後から矯正
- `.pg_template`
- catalog 保管庫思想
- event テンプレ
- 重い HTML 補正処理
- カート、決済、注文フローなどのEC機能

## 今後の拡張候補

- `thanks.html`
- `privacy.html`
- `faq.html`
- `works.html`
- テンプレごとの小さな派生追加

ただし、テンプレを増やしすぎる前に「実務で差し替えやすい最小構成」の思想を崩さないことを優先します。

## 現在の安全機構

### starter契約

- starterのHEADが`starter-contract.json`の`requiredCommit`と一致する。
- starterのworking treeがcleanである。
- コピー対象dist treeのSHA-256が一致する。
- 必須assetごとのSHA-256が一致する。
- runtime tokenがJavaScriptの静的文字列リテラルとして完全一致する。
- コメント内だけ、または長い文字列の一部分だけでは一致とみなさない。
- `dist`外へのtraversalを含むasset pathは拒否する。

### 案件生成とrefresh

- 新規生成は一時ディレクトリで完了してからliveへ交換する。
- `--refresh-dist`はdistと`project-manifest.json`を一組として交換する。
- refreshでも案件表示名と`createdAt`を保持する。
- rename失敗時はrollbackを試みる。
- rollbackできない場合はbackupとfailedを残し、次回処理を停止する。
- unresolvedな`.dist.*`と`.project-manifest.json.*`残骸がある状態では
  refreshを開始しない。

### WordPress変換

- `.project-generator-wordpress.json`で生成ファイルの所有権とSHA-256を管理する。
- `--force`でもユーザー編集済みファイルは置換しない。
- 所有権を確認できない既存同名ファイルは置換しない。
- 変換処理は一時ディレクトリを使用し、失敗時に元案件を保持する。
- header/footer navの現在ページ状態は`is_front_page()`と`is_page()`で
  動的に生成する。
- `is-current`と`aria-current="page"`は現在ページだけに付与する。

### 検証コマンド

正式な回帰テストコマンドは次のとおりです。

    python -m unittest discover -s tests -q

PHP CLIがPATHにない場合は、`PROJECT_GENERATOR_PHP`へ実行ファイルを指定します。
生成されたWordPress PHPは`php -l`で構文検査します。

### 障害時の扱い

- transaction残骸は内容を確認するまで削除しない。
- liveが欠落している場合でも、backupが旧案件一式であると確認するまで戻さない。
- 復旧後は全テスト、PHP lint、`git diff --check`、`git status`を確認する。
- 復旧と機能変更を同じcommitに混在させない。
