# macmini-watcher-gha

Apple Japan 整備済ストア(https://www.apple.com/jp/shop/refurbished/mac)を15分ごとに監視し、Mac mini M4 / M4 Pro が新規に出現したら ntfy.sh 経由で iPhone へプッシュ通知する GitHub Actions ワークフロー。

完全クラウド稼働、PCもClaudeアプリも不要、無料。

## セットアップ

1. GitHubでこのリポジトリを **Private** で作成。
2. 全ファイルをコミットしてプッシュ。
3. Repository Settings → **Secrets and variables → Actions → New repository secret**
   - Name: `NTFY_TOPIC`
   - Value: `chico-macmini-m4-yoshida-k7v2p9` （自分の ntfy トピック名）
4. Actions タブで `Watch Apple refurb Mac mini M4` を選び **Run workflow** を1回手動実行して動作確認。
5. 以降は15分ごとに自動実行される。

## 動作

- `watch.py` が Apple 整備済ページをスクレイピングし、商品名に「Mac mini」と「M4」を両方含む商品を抽出。
- 前回までに通知済みの商品URLは `state.json` に保存され、毎回GitHubにコミットされる。
- 新規出現があれば ntfy.sh JSON publish API へ POST → iPhone へプッシュ。
- 在庫から消えた商品は state から外れるので、再入荷時にまた通知される。

## 注意

- GitHub Actions の cron は混雑時に5〜15分遅延することがある（Apple/GitHub仕様）。
- 整備済は秒で売り切れるモデルもあるので、決済情報を Apple ID に登録しておくこと。
- Apple のページ構造が変わった場合は `watch.py` のスクレイピングを調整する必要がある。
