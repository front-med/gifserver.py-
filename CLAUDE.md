# CLAUDE.md — BODY LOG プロジェクト引き継ぎ書

このリポジトリは、前田怜緒（Reo）の個人開発プロジェクト「BODY LOG」エコシステムの一部。
Claude.aiのチャットで開発してきた内容を、Claude Codeで継続開発するための引き継ぎ書。

## ユーザーの好み（重要）

- 日本語で応答する。口調はフランクでよい（敬語不要とのこと）
- 質問するときは選択肢を提示する形式を好む（オープンな質問より選択式）
- コード納品は「上書き可能な全文」を基本とする
- デザインは白黒モノトーン（背景#fff、テキスト#1a1a1a、アクセント#111）で統一。フォントは全要素で統一（font-family: inherit を維持）
- 過度な確認より、まず動くものを出して直していくスタイルを好む

## システム全体構成

```
[iPhone/どこでも]
  BODY LOG (GAS Webアプリ) ──── スプレッドシート（データ保存）
     │ 📷モーダル                      │
     │  ├ ファイルアップロード          Drive「コンディション管理_フォーム素材」
     │  ├ アプリ内 動画→GIF変換 (gifshot)
     │  ├ URL直リンク取込 (UrlFetchApp)
     │  └ CLIP→GIFツールへのリンク（?ex=種目名 付き）
     │
  CLIP→GIF (このリポジトリ / Render) ──POST──> GASのdoPost（素材登録）
     yt-dlp + ffmpeg でSNS URL→GIF

[体重自動送信] Eufy体重計 → Appleヘルスケア → iOSショートカット(毎朝) → GAS doPost
```

## このリポジトリ（gifserver）

- `gifserver.py` … CLIP→GIF本体。Python標準ライブラリのみ（+外部コマンド ffmpeg / yt-dlp）
- `Dockerfile` … Render用（python:3.12-slim + ffmpeg + yt-dlp）
- デプロイ: **git push origin main するだけ**（Renderが自動デプロイ、2〜3分）
- 本番URL: https://gifserver-py-1.onrender.com/?key=ACCESS_KEY
- Render環境変数: `GAS_URL`（GASのexec URL）/ `GAS_SECRET`（API_SECRETと同値）/ `ACCESS_KEY`（ページの簡易パスワード）
- Render Secret File `cookies.txt`（YouTube用。期限切れしたら再エクスポート）
- 主要エンドポイント:
  - `POST /api/fetch` … yt-dlpでURL取得
  - `POST /api/render` … ffmpegでGIF書き出し（パレット2パス）
  - `POST /api/exercises` … GASから種目一覧を取得（プルダウン用）
  - `POST /api/register` … GIFをGASへPOSTして素材登録（9MB上限）
- UIはPAGE変数内のHTML。`?ex=種目名` で種目プルダウンを自動選択

## BODY LOG（GAS側）

- 実体はGASエディタ上の2ファイル: `Code.gs` と `index.html`（このリポジトリには未収載。
  取り込む場合は bodylog/ ディレクトリを作って管理し、変更後はGASエディタへ手動貼り付け）
- スプレッドシートのシート構成:
  - `コンディション`: 日付/体重(kg)/睡眠時間(h)/疲労度(1-5)/体調スコア(1-5)/メモ/記録時刻
  - `トレーニング`: 日付/種目/重量(kg)/回数/セット数/記録時刻
  - `種目マスタ`: 種目名/ファイルID/ファイル名/更新日（素材はDriveに保存、lh3.googleusercontent.com/d/{id} で表示）
- Code.gsの要点:
  - `API_SECRET` … 外部連携の合言葉（doPost認証）。gifserverのGAS_SECRETと必ず一致させる
  - `doPost` のアクション: 体重受信（デフォルト）/ `listExercises` / `uploadMedia`
  - `getInitData` … 起動時データを1回で返す（高速化のため。個別呼び出しに戻さない）
  - 同日コンディションは上書き保存。体重のみ更新(upsertWeight_)は他項目を保持
- index.htmlの要点:
  - タブ3つ: 記録 / トレーニング / まとめ（シート選択式）
  - トレーニング: 日付→この日の記録(編集/削除/📷)→「＋種目を追加」でプルダウン行追加
  - 冒頭の `GIF_TOOL_URL` にRenderのURL(?key=付き)を設定
  - まとめ: SUMMARYやグラフは意図的に廃止済み。復活させない

## GASのデプロイ手順（最重要・事故多発ポイント）

1. GASエディタでファイルを上書き → Ctrl+S
2. デプロイ → **デプロイを管理** → 鉛筆 → バージョン「**新バージョン**」→ デプロイ
   - 「新しいデプロイ」を作るとURLが変わってしまうので使わない
   - アクセス設定は「**全員**」を維持（外部連携に必須。API_SECRETで保護）
3. 反映されない場合の切り分け: シークレットウィンドウで確認 → 表示されればキャッシュ
※将来的に clasp を導入すればターミナルから push/deploy 可能。導入したらこの節を更新すること

## 既知の注意点・過去の地雷

- **再デプロイ忘れ**が不具合原因の9割。コード変更後は必ず新バージョンでデプロイ
- GASの新規Drive機能追加時は appsscript.json の oauthScopes に権限追加＋setup等の実行で再承認が必要
  （現在: spreadsheets, drive。UrlFetchApp使用時は external_request も）
- GIFは9MB上限（register側で弾く）。フォーム素材は6秒以内・320〜480pxを推奨
- YouTubeはクラウドIPだとボット判定 → cookies.txt で回避（切れたら再取得）
- Render無料枠は15分でスリープ。復帰に1分弱かかるのは仕様
- iOSのinput[type=date]は appearance:none 必須（外すと枠からはみ出る）
- スプレッドシートID等の秘密情報はコミットしない。API_SECRET/ACCESS_KEYの値もコードにハードコードしない（環境変数）

## よくあるタスクの型

- 「gifserverの〇〇を直して」→ 編集 → コミット → push（Renderが自動デプロイ）まで一気に実行してよい
- 「BODY LOGの〇〇を直して」→ bodylog/ に取り込み済みならファイル編集まで。GASへの貼り付けと再デプロイはReoが手動（claspが入るまで）。変更後は「GASに貼って新バージョンでデプロイして」と明確にリマインドすること
