# bodylog/ — BODY LOG（GAS側）ソース管理

BODY LOG本体は Google Apps Script（GAS）上の2ファイル `Code.gs` と `index.html` で動いている。
このディレクトリは、そのソースを**バージョン管理するためのミラー**。GASエディタとは自動同期しない。

## 運用ルール（重要）

- ここのファイルを編集しても本番には反映されない。**GASエディタへ手動で貼り付け → 新バージョンでデプロイ**が必要。
- 変更したら、Claude は「GASに貼って新バージョンでデプロイして」と明確にリマインドすること（CLAUDE.md の方針）。
- clasp を導入すればターミナルから push/deploy できるようになる。導入したら CLAUDE.md の該当節とこのREADMEを更新すること。

## GASデプロイ手順（事故多発ポイント）

1. GASエディタでファイルを上書き → Ctrl+S
2. デプロイ → **デプロイを管理** → 鉛筆 → バージョン「**新バージョン**」→ デプロイ
   - 「新しいデプロイ」を作るとURLが変わるので使わない
   - アクセス設定は「**全員**」を維持（外部連携に必須。API_SECRETで保護）
3. 反映されない場合: シークレットウィンドウで確認 → 表示されればキャッシュ

## 秘密情報

- `API_SECRET` / スプレッドシートID 等は**コミットしない**。取り込む際はプレースホルダに置換すること。
- gifserver 側の `GAS_SECRET` と GAS の `API_SECRET` は必ず一致させる。

## ファイル（取り込み待ち）

- `Code.gs` … doPost（体重受信 / listExercises / uploadMedia）, getInitData, upsertWeight_ など
- `index.html` … タブ3つ（記録 / トレーニング / まとめ）。冒頭の `GIF_TOOL_URL` に Render の URL(?key=付き) を設定

> GASエディタからコピーしてこのディレクトリに配置したら、この節を実ファイルの説明に置き換える。
