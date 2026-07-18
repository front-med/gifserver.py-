# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## BODY LOG プロジェクト引き継ぎ書

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
- UIは白黒モノトーンに統一済み（2026-07-18〜）。外部フォント読み込みなし・font:inherit で統一

## ローカル開発・動作確認

このMac固有のツール配置（brew未導入のため静的バイナリを使用）:

- `ffmpeg` / `ffprobe` / `gh` … `~/.local/bin/`（PATHは ~/.zshrc で設定済み。スクリプト内では `export PATH="$HOME/.local/bin:$PATH"` を明示すると確実）
- `yt-dlp` / `python3` … anaconda3（`~/anaconda3/bin/`）

```bash
# 構文チェック
python3 -m py_compile gifserver.py

# ローカル起動（http://127.0.0.1:8765 が自動で開く）
python3 gifserver.py --port 8765

# E2E動作確認（サーバ起動後、直リンクmp4で fetch → render）
curl -s -X POST http://127.0.0.1:8765/api/fetch -H 'Content-Type: application/json' \
  -d '{"url":"https://test-videos.co.uk/vids/bigbuckbunny/mp4/h264/360/Big_Buck_Bunny_360_10s_1MB.mp4"}'
# → 返ってきた id を使って:
curl -s -X POST http://127.0.0.1:8765/api/render -H 'Content-Type: application/json' \
  -d '{"id":"<id>","start":0,"end":2,"width":320,"fps":12,"colors":256,"dither":"sierra2_4a","loop":true}'
```

- テスト生成物は `gif_out/`（gitignore済み）。確認後は消してよい
- UIプレビュー: PAGE をHTMLに書き出してヘッドレスChromeでスクショ確認できる
  （`python3 -c "import gifserver; open('page.html','w').write(gifserver.PAGE.replace('__ACCESS_KEY__','\"\"'))"`）
- テストフレームワーク・リンターは無し（標準ライブラリのみの単一ファイル構成）

## BODY LOG（GAS側）

- 実体はGAS上の2ファイル: `コード.js`（=Code.gs）と `index.html`。`bodylog/` に clasp で取り込み済み。
  **秘密（API_SECRET等）がハードコードされているためGASソースは gitignore**（ローカルとGAS間で直接同期）。
  手元に無ければ `clasp clone <スクリプトID>` で再取得。詳細は bodylog/README.md
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

## BODY LOG Share（共有版・マルチユーザー / bodylog-share/）

- 友人・家族に共有するための別GASプロジェクト（standalone）。本家BODY LOGとは完全分離
- 仕組み（2026-07-18〜 あいことば方式）: Web Appは「自分として実行」+「全員（匿名可）」
  → **Googleログイン・承認画面は一切不要**。初回は名前＋あいことば（PASSCODE、コード.js内）を
  入力するだけ。端末にuid(localStorage)を保存して識別し、同じ名前＋あいことばで別端末からも再開可
- データはScriptPropertiesにJSON保存（uidで完全分離・月チャンク）。全体500KB上限（家族数人なら数年分）
- 機能はコア3つのみ（記録 / トレーニング / まとめ）。素材・GIF連携・体重API・LINEレポートは本家のみ
- **コード.jsはあいことば入りのためgitignore**（index.html/appsscript.jsonはコミット対象）
- デプロイフローは bodylog/ と同じ（`clasp push` → `clasp deploy -i $(cat .deployment-id) -d "説明"`）
- ヘッダーの名前横「変更」ボタンでいつでも名前変更可（renameUser）
- 管理者ビュー: 共有版の `?view=admin`（admin.html）と、**本家まとめタブ内「メンバーの記録」**の2箇所。
  本家はUrlFetchApp→共有版doPost(adminList/adminUser)で中継。ADMIN_PASSCODE保護・閲覧のみ。
  パスキーはlocalStorage(BL_ADMIN_PASS)に保存可

## GASのデプロイ手順（clasp導入済み・2026-07-18〜）

ターミナルから完結する。GASエディタでの手動貼り付けは不要になった。

```bash
cd bodylog
# 編集後:
clasp push                                          # GASへアップロード
clasp deploy -i $(cat .deployment-id) -d "説明"     # 本番へ新バージョン発行
```

- **`-i $(cat .deployment-id)` が最重要**。付け忘れると新しいデプロイ（＝新URL）ができて事故る
- アクセス設定は「**全員**」を維持（外部連携に必須。API_SECRETで保護）
- GASエディタで直接編集した後は `clasp pull` でローカルに取り込んでから作業する
- 反映されない場合の切り分け: シークレットウィンドウで確認 → 表示されればキャッシュ
- clasp は `~/.local/bin/clasp`。認証が切れたら `clasp login`（ブラウザ承認が必要なのでReoに依頼）

## 既知の注意点・過去の地雷

- **再デプロイ忘れ**が不具合原因の9割。コード変更後は必ず新バージョンでデプロイ
- **Sheetsの日付自動変換に注意**: 「2/4」等の文字列をsetValuesすると日付Dateに化け、
  google.script.run はDate入りの戻り値を返せず**通信ごと沈黙する**（アプリ全死に見える）。
  対策済み: 書き込みは非数値文字列に `'` 前置で強制テキスト化＋読み出しでDate→文字列変換
- GASの新規Drive機能追加時は appsscript.json の oauthScopes に権限追加＋setup等の実行で再承認が必要
  （現在: spreadsheets, drive。UrlFetchApp使用時は external_request も）
- GIFは9MB上限（register側で弾く）。フォーム素材は6秒以内・320〜480pxを推奨
- YouTubeはクラウドIPだとボット判定 → cookies.txt で回避（切れたら再取得）
- Render無料枠は15分でスリープ。復帰に1分弱かかるのは仕様
- iOSのinput[type=date]は appearance:none 必須（外すと枠からはみ出る）
- スプレッドシートID等の秘密情報はコミットしない。API_SECRET/ACCESS_KEYの値もコードにハードコードしない（環境変数）

## よくあるタスクの型

- 「gifserverの〇〇を直して」→ 編集 → コミット → push（Renderが自動デプロイ）まで一気に実行してよい
- 「BODY LOGの〇〇を直して」→ bodylog/ で編集 → `clasp push` → `clasp deploy -i $(cat .deployment-id)` まで一気に実行してよい（GASソースはgitignoreなのでコミットは不要）
