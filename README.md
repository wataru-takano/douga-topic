# 動画編集トピック（静的サイト＋ニュース自動更新）

## 中身
| ファイル | 役割 |
|---|---|
| `index.html` | サイト本体。ニュース以外（プラグイン、セール、各ソフト情報など）はこのファイルの中に入っています |
| `data/news.json` | ニュースのデータ。毎日自動で更新されます（手で書いたニュースは消えません） |
| `scripts/update_news.py` | RSSからニュースを集めるプログラム（Python標準ライブラリのみ） |
| `scripts/feeds.json` | 取得するRSSのURLと、絞り込みのキーワード |
| `.github/workflows/update-news.yml` | GitHub Actionsの設定（毎日 日本時間6:00に実行） |

## 設定の手順（GitHub Pages の場合）
1. GitHubで新しいリポジトリを作る（Publicがおすすめ。PrivateでPagesを使うには有料プランが必要）。
2. このフォルダの中身を、すべてリポジトリに置く。`.github` フォルダも忘れずに。
   - ブラウザからのアップロードで `.github` が入らないときは、Gitのコマンドで push してください。
3. **Settings → Pages** で、Source を「Deploy from a branch」、Branch を `main` / `(root)` にして保存する。数分でURLが発行されます。
4. **Settings → Actions → General → Workflow permissions** を「Read and write permissions」にして保存する。
5. **Actions** タブ →「ニュース自動更新」→ **Run workflow** で、1回手動で実行して動作を確認する。
   - ログに「OK: ○○ → 新規 ○ 件」と出れば成功です。「取得失敗」と出たフィードは、URLが違うか、サイトが取得を断っています。`scripts/feeds.json` で直してください。

## Cloudflare Pages の場合
GitHubのリポジトリは同じものを使います。Cloudflare Pagesで「Gitに接続」→ リポジトリを選び、ビルドコマンドは空欄、出力ディレクトリは `/`（空欄）にします。Actionsがニュースを更新して push するたびに、自動で再公開されます。

## 任意：AIで海外記事を日本語にする
1. AnthropicのAPIキーを用意する。
2. リポジトリの **Settings → Secrets and variables → Actions → New repository secret** で、名前を `ANTHROPIC_API_KEY`、値をAPIキーにして保存する。
3. 以降の実行から、海外記事の題名の日本語化と、60字以内の要約が付きます（1回につき最大12件）。
   - API料金がかかります。使うモデルは、環境変数 `ANTHROPIC_MODEL` で変えられます（初期値は `claude-haiku-4-5-20251001`）。
   - キーを設定しなければ、題名（英語のまま）と出典リンクだけを載せます。

## 自動更新される範囲と、されない範囲
- **自動**：ニュースタブ（新しい記事の追加、45日たった自動追加分の削除）。
- **手動**：プラグイン、セール、各ソフトの価格・バージョンなど。ここは価格やセールが変わりやすいので、自動化せず、`index.html` の中のデータを書き換えてください。

## 注意
- `scripts/feeds.json` のRSSのURLは、公開されている一般的な形式で書いたもので、作成時に実際に接続して確認したものではありません。初回の実行ログで確認してください。
- 自動で追加したニュースは、題名と出典リンクだけです。記事の本文は転載しません。
- GitHub Actionsの定期実行は、時刻が数十分ずれたり、混雑時に遅れたりすることがあります。
- 広告やアフィリエイトリンクを載せる場合は、「PR」「広告」の表示を付けてください。
