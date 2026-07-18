# bodylog/ — BODY LOG（GAS側）ソース管理

BODY LOG本体は Google Apps Script（GAS）上で動いている。
このディレクトリは **clasp** でGASと直接同期する作業ディレクトリ。

## ファイル構成（ローカルのみ・gitには入らない）

- `コード.js` … GASの本体（doPost / getInitData / upsertWeight_ など）
- `index.html` … UI（タブ3つ: 記録 / トレーニング / まとめ）
- `appsscript.json` … マニフェスト（oauthScopes等）
- `.clasp.json` … clasp設定（スクリプトID）
- `.deployment-id` … 本番Web AppのデプロイID（1行テキスト）

⚠️ 上記は **API_SECRET 等の秘密がハードコードされているため全て gitignore 済み**。
公開リポジトリにコミットしないこと。手元に無い場合は `clasp clone <スクリプトID>` で再取得
（スクリプトIDはGASエディタ → プロジェクトの設定）。

## 変更フロー（クラウド反映まで全部ターミナルで完結）

```bash
cd bodylog

# 1. コード.js / index.html を編集

# 2. GASへアップロード
clasp push

# 3. 本番Web Appに新バージョンを発行（-i 必須！ URLが変わらない）
clasp deploy -i $(cat .deployment-id) -d "変更内容の説明"

# 4. 反映確認（シークレットウィンドウ推奨）
clasp deployments   # バージョン番号が上がっていればOK
```

- **`-i` を付け忘れると新しいデプロイ（＝新URL）が作られてしまう。絶対に付ける。**
- clasp は `~/.local/bin/clasp`（PATH設定済み）。ログインは `clasp login`（reo0915b@gmail.com）
- GASエディタで直接編集した場合は、次の作業前に `clasp pull` でローカルへ取り込むこと

## 秘密情報

- `API_SECRET`（コード.js内）と gifserver 側の `GAS_SECRET`（Render環境変数）は必ず一致させる
- デプロイID・スクリプトID・Web App URLも公開リポジトリに書かない
