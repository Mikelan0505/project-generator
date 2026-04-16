# ファイル名

tasks-guide.md

## project-generator Tasks ガイド

このファイルは、`project-generator/.vscode/tasks.json` に登録している Task の役割を、あとで見返しやすいように整理したメモです。

---

## Task 一覧

### `pg: refresh dist`

**dist だけ更新** します。
HTML テンプレや WordPress 変換は触りません。

#### やること

- CSS / JS など `dist` 側を更新する

#### 使う場面

- SCSS や JS を直した
- 生成済み案件の `dist` だけ最新にしたい

---

### `pg: regenerate website (force)`

**website テンプレの静的HTML案件を再生成** します。
既存の同名案件があっても上書き前提です。

#### 主な生成物

- `index.html`
- `about.html`
- `service.html`
- `contact.html`
- `assets`
- `dist`

#### 使う場面

- website テンプレを直した
- website 案件を最初から作り直したい

---

### `pg: regenerate shop (force)`

**shop テンプレの静的HTML案件を再生成** します。

#### 主な生成物

- `index.html`
- `products.html`
- `about.html`
- `contact.html`
- `assets`
- `dist`

#### 使う場面

- shop テンプレを直した
- 商品一覧つき案件を作り直したい

---

### `pg: regenerate lp (force)`

**lp テンプレの静的HTML案件を再生成** します。

#### 主な生成物

- `index.html`
- `assets`
- `dist`

#### 使う場面

- LP テンプレを直した
- 1ページLP案件を作り直したい

---

### `pg: convert website to wp`

**生成済みの website 案件を WordPress 用 PHP 一式へ変換** します。

#### 主な生成物

- `style.css`
- `index.php`
- `functions.php`
- `header.php`
- `footer.php`
- `front-page.php`
- `page-about.php`
- `page-service.php`
- `page-contact.php`

#### 使う場面

- すでに website の HTML 案件がある
- それを WordPress テーマ化したい

---

### `pg: convert shop to wp`

**生成済みの shop 案件を WordPress 用 PHP 一式へ変換** します。

#### 主な生成物

- `style.css`
- `index.php`
- `functions.php`
- `header.php`
- `footer.php`
- `front-page.php`
- `page-products.php`
- `page-about.php`
- `page-contact.php`

#### 使う場面

- すでに shop の HTML 案件がある
- それを WordPress テーマ化したい

---

### `pg: convert lp to wp`

**生成済みの lp 案件を WordPress 用 PHP 一式へ変換** します。

#### 主な生成物

- `style.css`
- `index.php`
- `functions.php`
- `header.php`
- `footer.php`
- `front-page.php`

#### 使う場面

- すでに LP の HTML 案件がある
- それを WordPress テーマ化したい

---

### `pg: website full flow`

**website の静的HTML再生成 → WordPress 変換まで一気に実行** します。

#### 実質やること

1. `pg: regenerate website (force)`
2. `pg: convert website to wp`

#### 使う場面

- website 案件を最初から最新状態で WordPress 用まで作りたい
- 一発で最後まで流したい

---

### `pg: shop full flow`

**shop の静的HTML再生成 → WordPress 変換まで一気に実行** します。

#### 実質やること

1. `pg: regenerate shop (force)`
2. `pg: convert shop to wp`

#### 使う場面

- shop 案件を最初から最新状態で WordPress 用まで作りたい

---

### `pg: lp full flow`

**lp の静的HTML再生成 → WordPress 変換まで一気に実行** します。

#### 実質やること

1. `pg: regenerate lp (force)`
2. `pg: convert lp to wp`

#### 使う場面

- LP 案件を最初から最新状態で WordPress 用まで作りたい

---

## 覚え方

### `refresh`

**dist だけ** 更新する

### `regenerate`

**静的HTML案件を再生成** する

### `convert ... to wp`

**WordPress 用 PHP 一式へ変換** する

### `full flow`

**再生成 + WordPress 変換** を一気にやる

---

## 使い分けの目安

### SCSS / JS だけ直した

- `pg: refresh dist`

### 静的HTMLとして案件を作り直したい

- `pg: regenerate website (force)`
- `pg: regenerate shop (force)`
- `pg: regenerate lp (force)`

### 既存の HTML 案件を WordPress 化したい

- `pg: convert website to wp`
- `pg: convert shop to wp`
- `pg: convert lp to wp`

### 最初から最後まで一気にやりたい

- `pg: website full flow`
- `pg: shop full flow`
- `pg: lp full flow`

---

## よく使う想定

### website を最初から WordPress 用まで作る

- `pg: website full flow`

### shop を最初から WordPress 用まで作る

- `pg: shop full flow`

### lp を最初から WordPress 用まで作る

- `pg: lp full flow`

### すでにある案件を後から WordPress 化する

- `pg: convert ... to wp`

### CSS / JS だけ差し替えたい

- `pg: refresh dist`

---

## 補足

- どの Task も、実行時に **案件名** を入力する
- WordPress 変換は `convert_to_wp.py` を使う
- `style.css` と `index.php` も `wp-stubs/` から自動生成される
- 現時点では `website / shop / lp` が対応テンプレ
- まだ `template-parts` 化や loop 化は行わない

---

## 現時点の結論

よく使うのはたぶんこの3つ。

- `pg: website full flow`
- `pg: shop full flow`
- `pg: lp full flow`

細かく分けたい時だけ、

- `regenerate`
- `convert ... to wp`
- `refresh dist`

を使う。
g: website full flow`

### shop を最初から WordPress 用まで作る

- `pg: shop full flow`

### lp を最初から WordPress 用まで作る

- `pg: lp full flow`

### すでにある案件を後から WordPress 化する

- `pg: convert ... to wp`

### CSS / JS だけ差し替えたい

- `pg: refresh dist`

---

## 補足

- どの Task も、実行時に **案件名** を入力する
- WordPress 変換は `convert_to_wp.py` を使う
- `style.css` と `index.php` も `wp-stubs/` から自動生成される
- 現時点では `website / shop / lp` が対応テンプレ
- まだ `template-parts` 化や loop 化は行わない

---

## 現時点の結論

よく使うのはたぶんこの3つ。

- `pg: website full flow`
- `pg: shop full flow`
- `pg: lp full flow`

細かく分けたい時だけ、

- `regenerate`
- `convert ... to wp`
- `refresh dist`

を使う。
