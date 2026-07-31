# 予定返信AI・試作版

登録した空き時間と、相手から届いた日程調整メッセージを照合し、返信候補を生成するローカルWebアプリです。

## 現時点でできること

- 空いている日付・時間を登録
- 「来週の平日夜」「明後日18時以降」などを解析
- 条件に合う候補を最大5件抽出
- 相手へ送る返信文を生成
- OpenAI APIキーがなくても基本動作を確認可能

予定を勝手に確定したり、LINE・Google Calendarへ書き込んだりはしません。

## Windowsでの起動方法

### 1. Pythonをインストール

Python 3.11以上をインストールします。インストール時に `Add Python to PATH` を有効にしてください。

### 2. PowerShellでフォルダへ移動

```powershell
cd "解凍したフォルダの場所\ai_schedule_mvp"
```

### 3. 仮想環境と必要ライブラリを準備

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

PowerShellで実行が拒否された場合は、そのウィンドウ内だけ次を実行します。

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.venv\Scripts\Activate.ps1
```

### 4. 起動

```powershell
streamlit run app.py
```

ブラウザが自動で開きます。開かない場合は、PowerShellに表示された `Local URL` をブラウザで開いてください。

## AI解析を有効にする方法（任意）

1. `.streamlit/secrets.toml.example` をコピーし、ファイル名を `secrets.toml` に変更します。
2. `OPENAI_API_KEY` に自分のAPIキーを入力します。
3. アプリを再起動します。

APIキーは他人に送らず、GitHubにも公開しないでください。API利用には別途料金が発生する場合があります。

## 次に追加する機能

1. Google Calendar OAuth認証
2. FreeBusy APIで予定名を取得せず、埋まっている時間だけ照合
3. 候補を本人が承認する画面
4. LINE公式アカウントをグループに追加し、Webhook経由で候補を返信
5. 双方が同意した場合のみカレンダーへ予定を登録
