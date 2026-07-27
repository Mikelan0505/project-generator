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
├─ .htmlvalidate.json
├─ docs/
│  └─ project-generator-handover.md
├─ outputs/                  # Git管理外の生成物
│  └─ sample/               # HTML検証時に再生成する破棄可能なsample
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
├─ tools/
│  └─ public_release_check.py
├─ wp-stubs/
│  ├─ style.css
│  └─ index.php
├─ convert_to_wp.py
├─ package-lock.json
├─ package.json
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

### 問い合わせフォームの送信処理

`website` / `shop` の `contact.html` にある `action="#"` は、送信先が未設定であることを示す placeholder です。これは現在のテンプレート上の初期値であり、form action の固定仕様ではありません。

`project-generator` は、static HTML の生成時に form の server-side submission 処理を生成しません。WordPress 変換でも、form handler、nonce、mail 送信、AJAX 処理は追加しません。

公開前に、案件固有の送信先と server-side 処理を実装してください。入力 validation、spam 対策、CSRF 対策、完了画面も案件側で設計する必要があります。placeholder のまま公開しても問い合わせ送信機能は成立しません。

### dist 更新

生成済み案件の `dist/css` と `dist/js` を最新化する場合は、PowerShell wrapper を使用します。
`outputs` 内の有効な案件が1件だけなら、その案件を自動選択します。

```powershell
.\sync-dist.ps1
```

案件名を位置指定または名前付きparameterで明示することもできます。

```powershell
.\sync-dist.ps1 sample-site
.\sync-dist.ps1 -Project sample-site
```

`outputs` 内に複数案件がある場合は自動選択せず、案件名の指定を要求します。

VS Codeから実行する場合は、`Ctrl+Shift+P`でコマンドパレットを開き、
`Tasks: Run Task`から次のいずれかを選択します。

- `Project Generator: Sync dist (auto)`
- `Project Generator: Sync dist (project)`

`outputs` 内に複数案件がある場合は、案件名を入力する
`Project Generator: Sync dist (project)`を使用してください。
どちらのtaskも内部ではrepository rootの`sync-dist.ps1`を呼び出します。

既存のPython commandは、正式な低level interfaceとして引き続き使用できます。

```bash
python script.py --refresh-dist --project sample-site
```

この処理は `sass-starter-exiga/dist/css` と `sass-starter-exiga/dist/js` を、
既存の `outputs/sample-site/dist/` に再コピーします。

- HTMLは変更しない
- PHPは変更しない
- template内容は再同期しない
- 既存案件全体は再生成しない

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
`outputs/sample`はHTML検証専用の破棄可能な生成物であり、
`npm run lint:html`のたびに現在のtemplateとStarterから再生成されます。
`outputs/sample`へ手作業の案件データを置かないでください。
その他の任意の`outputs`内案件は、標準検証scriptの対象外です。

## 今回採用していないもの

- sync モード
- 既存案件の再同期
- header / footer の後から矯正
- `.pg_template`
- catalog 保管庫思想
- 重い HTML 補正処理
- カート、決済、注文フローなどの本格EC機能

必要になったら将来拡張できますが、現時点では最小構成のまま保つ方針です。

## ローカル保守と安全検証

このリポジトリは、生成結果だけでなく生成経路も検証対象とします。
作業開始時には `project-generator` と `sass-starter-exiga` の両方で
working treeがcleanであることを確認してください。
`starter-contract.json`は必須であり、欠落・破損・読み取り不能の場合は
生成と`--refresh-dist`を開始しません。

### HTML検証

HTML検証にはNode.js `>=22.16.0 <23`とnpm `10.9.2`を使用します。
初回または`package-lock.json`更新後は、次のコマンドで依存関係を
lockfileどおりにインストールします。

    npm ci --ignore-scripts

標準HTML検証コマンドは次のとおりです。

    npm run lint:html

このコマンドは`templates/**/*.html`を先に検証し、成功した場合だけ
`outputs/sample`を現在のtemplateとStarterから再生成して、
`outputs/sample/**/*.html`を検証します。
`outputs/sample`はHTML検証専用の破棄可能な生成物です。
手作業の案件データは置かないでください。

その他の任意の`outputs`内生成案件は標準scriptで一括検証せず、
必要に応じて案件単位で個別検証してください。

統合ローカル検証コマンドは次のとおりです。

    npm run check

HTML検証とPython回帰テストは独立した品質ゲートとして、
`check`内でこの順番に実行されます。

### 実案件の公開前検査

`npm run check:public`は、サーバーへ公開する実案件にplaceholder、
開発用URL、未設定form、SEO不足、参照切れ、公開禁止file、HTML構文違反が
残っていないかを確認する独立した品質ゲートです。
Generator自身を検証する`npm run check`には組み込んでいません。

`--root`にはrepositoryや`outputs`全体ではなく、
「サーバーへ公開する予定のfile群」だけが入ったdirectoryを指定します。
`--base-url`には、例示値ではなく実案件のHTTPS本番URLを指定してください。
本番サイトがsubdirectory配下の場合も、そのpathまで含めます。

PowerShellでの基本例:

```powershell
npm run check:public -- --root "C:\path\to\client-project" --base-url "https://www.client-site.jp"
```

空白・日本語を含むpathとsubdirectory構成の例:

```powershell
npm run check:public -- --root "C:\案件\公開 データ\株式会社サンプル" --base-url "https://www.client-site.jp/corporate/"
```

上記のpath、domain、案件名は説明用の例示であり、そのまま実行する値では
ありません。案件ごとの実在する公開directoryと本番URLへ置き換えてください。
`--root`は絶対pathと、現在のdirectoryを基準にした相対pathの両方を扱えます。

検査は公開対象を一切変更しないread-only処理です。問題を1件見つけても
停止せず、検査可能な全fileから検出事項を収集し、相対path、行番号、
RULE_ID、理由の固定順で表示します。

終了codeの意味:

- `0`: 対象HTMLが1件以上あり、公開停止事項を検出しなかった
- `1`: 公開を止める検出事項が1件以上あった
- `2`: 引数、対象path、Node.js、local html-validateなどの使用上のエラーで
  検査を完了できなかった

主な検査対象:

- HTML、CSS、JavaScript、JSON、XML、PHP、SVG、CSV、TSV、YAMLと
  `.htaccess`など、拡張子または既知のfile名からtextと判定できる公開file
- `{{...}}`、`20XX`、`〇〇`、example domain、既知のstarter説明文などの
  未置換・ダミー情報
- form actionの未設定、空値、fragment、`javascript:`と相対送信先の参照切れ
- localhost、loopback address、`file://`などの開発用URL
- 各HTMLのtitle、description、canonical、OGPと、base URLとの整合
- `href`、`src`、`srcset`、`poster`、同一page内fragment、同一site内参照
- credential、archive、backup、transaction残骸、Generator manifestなどの
  公開禁止file
- UTF-8読み取りと、localの`node_modules/html-validate`によるHTML構文

HTML構文検査はlocalにinstall済みの`html-validate`だけを使用します。
Node.jsまたはlocal packageがない場合はskipせず終了code 2とし、
`npx`やnetworkからの自動downloadへfallbackしません。

画像などのbinary fileは文字列として読みませんが、HTMLからの参照先として
存在を確認します。`mailto:`、`tel:`、`data:`、`blob:`と外部originの
HTTP(S) URLはlocal fileの存在検査対象外です。外部URLの到達性、
PHPやWordPressが動的に出力するSEO、formの実送信、server設定、
法令・規約への適合性までは検証しません。

`.git`、`.hg`、`.svn`、`node_modules`が公開root内にある場合は公開停止事項
として報告し、巨大な内部treeは走査しません。symlinkとWindows junctionも
参照範囲を安全に確定できないため、それぞれ`SYMLINK_UNCHECKED`、
`JUNCTION_UNCHECKED`として公開停止し、参照先へ再帰しません。
走査はentry数20,000件、directory深度64、text file単体10 MiB、
text合計100 MiBを上限とし、超過時は終了code 2で公開rootの絞り込みを
要求します。

Generatorの`templates`には意図的なダミー情報があり、生成直後の案件にも
未設定formやSEO情報が残るため、公開前検査に失敗するのが正常です。
案件固有情報、送信処理、公開URL、assetを完成させてから実行してください。

検査成功は、検査範囲で既知の公開停止事項が見つからなかったことだけを
示します。「公開内容全体の正しさ」や公開可能性を保証するものではありません。

### 回帰テスト

正式な回帰テストコマンドは次のとおりです。

    python -m unittest discover -s tests -q

`python -m unittest discover`だけでは、実行位置や構成によっては
0件実行を成功と誤認する可能性があります。

生成PHPの構文検査にはPHP CLIを使用します。PHPがPATHにない場合は、
`PROJECT_GENERATOR_PHP`へ実行ファイルの絶対パスを設定します。

    $env:PROJECT_GENERATOR_PHP = "C:\path\to\php.exe"
    python -m unittest discover -s tests -q
    Remove-Item Env:PROJECT_GENERATOR_PHP

### starter契約の更新手順

`sass-starter-exiga`を変更した場合は、次の順序を守ります。

1. starter側でbuildとbrowser smokeを完了する。
2. starter側をcommitし、working treeをcleanにする。
3. `starter-contract.json`の`requiredCommit`を新しいHEADへ更新する。
4. コピー対象の`dist/css`と`dist/js`から`distTreeSha256`を更新する。
5. `requiredAssetSha256`を実ファイルから更新する。
6. runtime selectorを変更した場合だけ`requiredRuntimeTokens`を更新する。
7. starter契約検査と全回帰テストを実行する。

runtime tokenは、コピー対象JavaScript内のコメントではない
静的文字列リテラルと完全一致する必要があります。
部分文字列やコメント内だけの記述では契約を満たしません。

starter実行契約はbranch非依存です。再現性の基準は`requiredCommit`、
cleanなworking tree、dist tree hash、必須asset hash、runtime tokenです。
detached HEADでも同じcommitとartifactであれば有効とします。

`main`と`origin/main`の同期はrelease・監査時の運用確認であり、
generator実行時の必須条件にはしません。remote未設定やoffline環境でも、
固定commitとartifactを検証できることを優先します。

### 案件manifest

`project-manifest.json`には、次の追跡情報を記録します。

- 案件表示名とslug
- 使用template
- generator commit
- starter commit
- コピー対象dist treeのSHA-256
- 必須assetのSHA-256
- 作成日時と更新日時

`--refresh-dist`では、案件表示名と`createdAt`を保持します。
distとmanifestは一組としてtransactionalに交換し、片方だけが
新しくなる状態を許可しません。

### WordPress生成物の所有権

`.project-generator-wordpress.json`には、generatorが管理する
WordPress生成ファイルと各SHA-256を記録します。

`convert_to_wp.py --force`で置換できるのは、所有権manifestに記録され、
かつ生成後に変更されていないファイルだけです。

次のファイルは自動置換しません。

- ユーザーが編集したファイル
- 所有権manifestに記録されていない同名ファイル
- 記録済みSHA-256と現在値が一致しないファイル

WordPress版のheader/footer navは、`is_front_page()`と`is_page()`から
`is-current`と`aria-current="page"`を動的に出力します。

### transaction残骸

通常生成、`--refresh-dist`、WordPress変換は、各処理に対応する
未解決transaction残骸を検出した場合に停止します。

対象例は次のとおりです。

- `.案件名.tmp-*`
- `.案件名.backup-*`
- `.案件名.failed-*`
- `.dist.tmp-*`
- `.dist.backup-*`
- `.dist.failed-*`
- `.project-manifest.json.tmp-*`
- `.project-manifest.json.backup-*`
- `.project-manifest.json.failed-*`

WordPress変換では、案件ディレクトリの隣に次の残骸が残る場合があります。

- `.案件名.wp-tmp-*`
- `.案件名.wp-backup-*`
- `.案件名.wp-failed-*`

残骸を見つけても、内容を確認する前に削除してはいけません。
live、backup、failed、tmpの内容と更新時刻を比較し、旧データと新データを
判別してください。

liveが欠落し、backupが旧案件一式であると確認できた場合だけ、
backupを元の案件名へ戻します。その後に全回帰テスト、PHP lint、
`git status`を確認してから不要な残骸を削除します。
