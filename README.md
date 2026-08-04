# 予定返信AI v4.0（分業構成）

現在の機能を変えず、複数人が同時に作業しやすいように責務ごとに分割した版です。
Streamlit Community Cloudの起動ファイルは従来どおり `app.py` です。

## 担当の分け方

| 担当 | 主に触る場所 | 内容 |
|---|---|---|
| 画面・操作 | `ui/`、`app.py` | Streamlit画面、入力欄、結果表示 |
| 日本語ルール解析 | `parsers/` | 日付、曜日、時間帯、所要時間の解釈 |
| 日程計算 | `services/candidate_service.py` | 空き時間との照合、候補抽出、連続枠の結合 |
| 返信文 | `services/reply_service.py` | 候補の表示形式、返信文の生成 |
| AI・外部連携 | `integrations/` | OpenAI、将来のGoogle Calendar・LINE連携 |
| データ構造 | `domain/models.py` | 各機能が共通で使うデータ型 |
| テスト | `tests/` | 担当機能ごとの自動テスト |

## フォルダ構成

```text
app.py                         # Streamlitの起動入口
ui/streamlit_app.py            # 画面本体
domain/models.py               # 共通データ型
parsers/common.py              # 表記統一・漢数字
parsers/date_parser.py         # 日付・週・月
parsers/weekday_parser.py      # 曜日・前半後半
parsers/time_parser.py         # 時刻・時間帯
parsers/duration_parser.py     # 所要時間
parsers/request_parser.py      # 各解析器の統合
services/candidate_service.py  # 候補抽出
services/reply_service.py      # 表示・返信文
integrations/openai_parser.py  # AI解析
tests/                         # 自動テスト
```

`scheduler.py` と `ai_parser.py` は旧コードとの互換用です。今後の新規コードでは各フォルダを直接importしてください。

## ローカル起動

```powershell
py -3.13 -m venv .venv313
.\.venv313\Scripts\python.exe -m pip install -r requirements.txt
.\.venv313\Scripts\python.exe -m streamlit run app.py
```

## テスト

```powershell
.\.venv313\Scripts\python.exe -m unittest discover -s tests -v
```

## GitHubでの分業

各担当者は別ブランチで作業し、Pull Requestで `main` へ統合してください。

例：

```text
feature/ui-calendar-editor
feature/date-expression-rules
feature/candidate-ranking
feature/line-integration
```

同じファイルを複数人が同時に編集しないよう、上の担当表を基準に分けると衝突が減ります。
