# hlmv-dl GUI

hlmv-dl（HELLO! MOVIE の音声ガイド・コメンタリーのダウンロードツール）を
Windows で GUI から使うためのアプリです。hlmv-dl 本体は GitHub Actions が
ビルドして exe に同梱するため、利用者側に Python や git は不要です。

## 構成

```
app.py                         GUI 本体
core.py                        ツールの検出・更新・一覧取得・ダウンロード
icons.py                       SVG アイコン
theme.py                       配色とスタイルシート
scripts/build_tool.py          hlmv-dl を exe 化する（CI で実行）
.github/workflows/build-app.yml        GUI のビルド（tag push で Release に添付）
.github/workflows/tool-release.yml     ツールの配布（手動実行のみ）
```

## 初回セットアップ

1. GitHub に空のリポジトリを作成する。
2. このフォルダから push する。

   ```
   git remote add origin https://github.com/<ユーザー名>/<リポジトリ名>.git
   git push -u origin main
   ```

3. Actions タブで **Publish hlmv-dl tool** を手動実行する。
   GUI の「ツールの更新」が使う配布物（`tool-latest` リリース）が作られます。
4. アプリを配布するときはタグを打つ。

   ```
   git tag v0.1.0
   git push origin v0.1.0
   ```

   **Build app** が走り、Releases に `hlmv-dl.exe` が添付されます。

## 開発時の起動

`run.bat` をダブルクリックします（uv があれば uv で、無ければ pip で PySide6 を入れて起動）。

## 更新の仕組み

- hlmv-dl は毎日は自動ビルドしません。更新したいときに **Publish hlmv-dl tool** を手動で実行します。
- 配布された最新版は GUI の「ツール → ツールの更新…」で取得・適用できます。
- 更新版は `%LOCALAPPDATA%\hlmv-gui\tools\` に置かれ、同梱版より優先されます。
- 取得した exe はチェックサムと起動確認を通してから差し替えます。

## 注意

非公式のツールです。配布コンテンツの権利は各権利者に帰属します。個人の範囲で、各サービスの利用規約に従って使ってください。
