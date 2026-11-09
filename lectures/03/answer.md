# 第3回 解答

## 演習

- 第1回（素のLLM）とエージェントの回答の違い：
  - 第1回の素のLLM（`app.ask`）では、講座固有の「`lecNN-start` タグ」や「宿題の3レベル」について事前知識がないため、「分からない」と答えるか一般的な推測でもっともらしく答えていた（ハルシネーション）。
  - 一方、第3回のエージェント（`app.agent`）は回答前に `search_glossary` ツールを呼び出して `data/glossary.json` を検索するため、「各回の演習開始時点のコードに付けているGitタグ（例：`lec03-start`）であり、前の回が終わっていなくてもこのタグからブランチを作れば演習を始められる」という講座固有の正確な定義と、関係する回（第1回）を根拠に基づいて回答できた。
- `--trace` で見えたツール呼び出し（ツール名と引数）：
  - 「LoRAとQLoRAの違いは？」に対して：
    - `[tool call]   search_glossary({"query": "LoRA"})`
    - `[tool call]   search_glossary({"query": "QLoRA"})`
  - 「第2回の内容から確認問題を1問出して」に対して：
    - `[tool call]   make_quiz({"lecture": 2})`
- 1つの質問での LLM 呼び出し回数（`requests`）：
  - `requests=2`（1回目の呼び出しでモデルがどのツールをどの引数で呼ぶかを判断し、ツールの実行結果を受け取った2回目の呼び出しで最終回答を生成するため）。用語の関連語をさらに追加検索した場合は `requests=3` になる。
- 追加したツールと、docstring に書いた説明：
  - 追加したツール：`make_quiz(lecture: int) -> str`
  - docstring に書いた説明：
    ```text
    指定した回（1始まりの整数）の用語から1つを選び、確認問題と答えを返す。

    「第2回の内容から確認問題を出して」「理解度を確かめたい」など、
    特定の回の復習クイズや確認問題を出してほしいと頼まれたときに使う。
    ```

## 宿題

- 取り組んだレベル：実装
- やったこと：
  1. `app/tools.py` に、学習したテーマ（`topic: str`）と内容（`content: str`）を受け取って `learning_log/` フォルダ配下に日時付きの Markdown ファイル（`YYYYMMDD_HHMMSS_<topic>.md`）として保存する `save_learning_log` ツールを実装した。
  2. `app/agent.py` で `Agent` の `output_type` に `[str, DeferredToolRequests]` を設定し、`agent.tool_plain(tools.save_learning_log, requires_approval=True)` として登録することで、ファイル保存の前に実行を承認待ち（Human-in-the-Loop）で一時停止するようにした。
  3. `app/agent.py` の `main()` で、エージェントの出力が `DeferredToolRequests` だった場合に CLI で利用者に保存してよいか（`[y/N]`）を確認し、`y` なら `True`、それ以外なら `ToolDenied("利用者が保存をキャンセルしました。")` を `DeferredToolResults` に詰めて `message_history=result.all_messages()` とともに `run_sync` を再開するループを実装した。
  4. `tests/test_tools.py` と `tests/test_agent.py` に、`save_learning_log` 単体のテストおよび `TestModel` を用いて承認時にファイルが保存され・拒否時（`ToolDenied`）には保存されないことを検証するテストを追加した。
- 結果：
  - CLI での実行と `--trace` の出力（承認して保存した場合）：
    ```text
    $ uv run python -m app.agent --trace "LoRAについて学んだこと（低ランク行列の積で重みの更新分を表し、少ないパラメータで効率よく追加学習するPEFT手法）を学習ログに保存して"
    [model] gemini-3.5-flash-lite
    [確認] save_learning_log({'content': '低ランク行列の積で重みの更新分を表し、少ないパラメータで効率よく追加学習するPEFT手法', 'topic': 'LoRA'}) を実行して保存しますか？ [y/N]: y
    「LoRA」についての学習記録を `learning_log/` フォルダに保存しました。

    （関係する回：第2回・第3回）

    --- trace ---
    [tool call]   search_glossary({'query': 'LoRA'})
    [tool return] search_glossary -> [{"term": "LoRA", "lecture": 2, "definition": "事前学習済みの重みは固定したまま、重みの更新分を2つの小さな行列の積（低ランク行列）で表し…
    [tool call]   save_learning_log({'content': '低ランク行列の積で重みの更新分を表し、少ないパラメータで効率よく追加学習するPEFT手法', 'topic': 'LoRA'})
    [tool return] save_learning_log -> 学習記録を learning_log/20261109_161500_LoRA.md に保存しました。…
    [usage] RunUsage(requests=3, input_tokens=..., output_tokens=...)
    ```
  - 確認で `n` を入力してキャンセルした場合：
    ```text
    [確認] save_learning_log({'content': '...', 'topic': 'LoRA'}) を実行して保存しますか？ [y/N]: n
    利用者の確認により、学習記録の保存をキャンセルしました。（関係する回：第2回・第3回）
    ```
  - テスト実行結果（`uv run pytest -q`）：
    - `test_save_learning_log`、`test_save_learning_log_requires_approval_and_saves_when_approved`、`test_save_learning_log_does_not_save_when_denied` を含む全テストがパスすることを確認した。
- 気づき・疑問：
  - 読み取り専用のツール（`search_glossary` や `get_lecture_summary`）はエージェントが自律的に呼んでよいが、ファイルの書き込みや外部送信など「副作用があり取り消しにくい操作」には `requires_approval=True` で Human-in-the-Loop（人間の承認）を挟むことで、プロンプトインジェクションやモデルの誤判断による意図しない書き込みを確実に防げることが分かった。
  - Pydantic AI では、承認待ちを単なる `input()` の副作用としてツール関数の中に直接書くのではなく、`DeferredToolRequests` と `DeferredToolResults`（＋`message_history`）として状態を切り出して再開する設計になっているため、CLI だけでなく Web アプリや非同期 UI、さらには `TestModel` を使った自動テストでも入力待ちでハングせずに綺麗にテストできる点が非常に優れていると感じた。
