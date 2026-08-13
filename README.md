# 予定返信AI v4.5（貼り付けから返信までを短縮）

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
parsers/ambiguity_parser.py    # 曖昧・未対応・矛盾の検証
parsers/compound_parser.py     # 複合条件・優先順位
services/candidate_service.py  # 候補抽出
services/availability_service.py # 通常時間からbusyを差し引く
services/reply_service.py      # 表示・返信文
integrations/openai_parser.py  # AI解析
integrations/google_calendar.py # Google CalendarのOAuth・free/busy取得
ui/availability_forms.py       # 空き時間登録データの変換
tests/                         # 自動テスト
```

`scheduler.py` と `ai_parser.py` は旧コードとの互換用です。今後の新規コードでは各フォルダを直接importしてください。

## v4.5で追加した主な仕様

- 相手のメッセージ入力を画面の最上段へ移し、空き時間設定は折りたたみ内へ整理
- 返信文を第三者表現から、そのまま送れる短い一人称表現へ変更
- 返信の雰囲気を「友人向け・ふつう・丁寧」から選択
- 「少し待ってもらう」「今回は断る」の即返信を用意
- 生成後も返信文を編集でき、コピー用表示からワンクリックでコピー
- Google Calendar OAuth連携とfree/busy取得を実装
- Googleから取得する情報は予定の題名・内容ではなくbusy時間だけ
- Googleのbusyを、通常時間からの自動計算と従来の直接登録の両方へ適用

## Google Calendar連携の設定

1. Google CloudでCalendar APIを有効にします。
2. OAuth同意画面を設定し、ウェブアプリケーション用のOAuthクライアントを作成します。
3. StreamlitアプリのURLを、末尾の`/`を含めて承認済みリダイレクトURIへ登録します。
4. Streamlit Community CloudのSecretsへ次を設定します。

```toml
GOOGLE_CLIENT_ID = "...apps.googleusercontent.com"
GOOGLE_CLIENT_SECRET = "..."
GOOGLE_REDIRECT_URI = "https://your-app.streamlit.app/"
GOOGLE_CALENDAR_IDS = "primary"
GOOGLE_TIME_ZONE = "Asia/Tokyo"
```

認可情報は現在のブラウザセッション内だけに保持します。永続ログインや利用者ごとの通常時間保存は、ユーザー認証とデータベース導入後の対象です。

## v4.4で追加した主な仕様

- 曜日ごとの「通常対応可能時間」を登録
- 仕事・学校・アルバイトなど毎週繰り返すbusy時間
- 夏休み・学期などに合わせた固定予定の適用開始日・終了日
- 食事・通院などの単発busy時間
- `実際の空き時間 = 通常対応時間 - 固定予定 - 単発予定`の区間計算
- 重複するbusy、終日、日付またぎbusyに対応
- Google Calendarのfree/busy取得結果を `BusyInterval` として同じ計算に入れられる構造
- 従来の「空き時間を直接登録」方式と旧APIも維持

## v4.3で追加した主な仕様

- 空き時間に開始日と終了日を持たせ、宿泊・旅行など複数日の連続候補に対応
- `22時から翌1時`、`23:30〜翌1:30`などの日付またぎ時刻
- `明日から3日間`、`3日以内`、`8月15、16、18日`、`2026.8.20`
- `1時間以内`、`1時間以上`、`1時間半〜2時間半`、`2泊3日`などの所要時間
- `又は`・`or`・組み合わせた共通条件、第三希望までの優先順位
- 日付と曜日の矛盾、過去日、未対応表現、解析条件がない文への聞き返し
- 旧来の `Availability(日付, 開始, 終了)` 呼び出しはそのまま利用可能

## v4.2で追加した主な仕様

- `火曜の夜か水曜の午前`を、対応関係を保った別グループとして解析
- `月曜なら18時以降、火曜なら20時以降`などの条件分岐
- `火曜か水曜の夜`など、同種候補の末尾にある共通条件を継承
- `できれば火曜、無理なら水曜`の第一希望・第二希望
- `第一希望は金曜夜、第二希望は土曜午後`の明示的優先順位
- 第一希望に空きがない場合、第二希望を代替候補として表示
- 修飾範囲が不明な複合条件と、複数回予定の可能性がある表現への聞き返し

複合条件はルール解析でグループ化してから候補計算します。AI解析が有効でも、ルールで
複合条件を確定できた場合は、そのグループを崩さずルール解析結果を利用します。

## v4.1で追加した主な仕様

- `火曜以外`、`水曜は無理`などの除外曜日
- `18時半`、`18時30分`、`18時から2時間`
- `19時前後`を開始時刻の前後10分として処理
- `1〜2時間`の所要時間範囲
- 週明け＝月・火、月初＝1〜5日、月末＝25日〜末日
- 月を省略した日付、`明日以降`、`明日まで`
- `今度`、`近いうち`への聞き返しまたは柔らかい返信
- 午前・午後が不明な1〜11時への聞き返し

AI解析を選択した場合も、既知の曖昧表現はルール解析で先に判定します。AI解析結果も
`resolved`、`needs_clarification`、`soft_invitation`のいずれかを返します。

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
