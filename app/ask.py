"""第1回: 素のLLMに会話履歴を保ちながら質問するスクリプト。

使い方:
    uv run python -m app.ask "LoRAとは何ですか？"
    uv run python -m app.ask            # 質問を省略すると、講座に固有の質問をする
    uv run python -m app.ask --reset "新しい会話を始める質問"  # 保存済み履歴を消す

ツールは使わず、同じChatセッションで会話履歴を保つ「素の」呼び出し。
講座に固有のことを聞くと、「分からない」と答えるか、一般論でもっともらしく答える
（講座の実際とは違う）ことを確かめよう。
（第3回で、用語集を検索できるエージェントにして改善する）
"""

import argparse
import json
from pathlib import Path

from google import genai
from google.genai import errors
from google.genai import types

from app.config import MODEL, api_error_message, get_api_key

# 講座に固有の質問。正しい答えは data/glossary.json の homework-levels にある
DEFAULT_QUESTION = "AIE2026の講座の宿題にある「3レベル」とは何ですか？"
HISTORY_PATH = Path.home() / ".aie2026" / "ask_history.json"


def load_history() -> list[types.Content]:
    if not HISTORY_PATH.exists():
        return []
    saved = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
    if saved.get("model") != MODEL:
        print("[履歴] 使用モデルが前回と異なるため、新しい会話を開始します")
        return []
    return [types.Content.model_validate(item) for item in saved["history"]]


def save_history(history: list[types.Content]) -> None:
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    saved = {
        "model": MODEL,
        "history": [item.model_dump(mode="json", by_alias=True, exclude_none=True) for item in history],
    }
    HISTORY_PATH.write_text(json.dumps(saved, ensure_ascii=False, indent=2), encoding="utf-8")


def ask(question: str, chat) -> str:
    response = chat.send_message(question)

    usage = response.usage_metadata
    if usage:
        print(f"[トークン数] 入力: {usage.prompt_token_count}, 出力: {usage.candidates_token_count}")

    return response.text


def main() -> None:
    parser = argparse.ArgumentParser(description="素のLLMに質問する")
    parser.add_argument("question", nargs="?", default=DEFAULT_QUESTION)
    parser.add_argument("--reset", action="store_true", help="保存済みの会話履歴を消して開始する")
    args = parser.parse_args()

    client = genai.Client(api_key=get_api_key())
    if args.reset:
        HISTORY_PATH.unlink(missing_ok=True)
    history = load_history()
    chat = client.chats.create(model=MODEL, history=history)
    print(f"[model] {MODEL}")
    if history:
        print(f"[履歴] {len(history)}件のメッセージを復元しました")
    try:
        print(f"[質問] {args.question}\n")
        print(ask(args.question, chat))
        save_history(chat.get_history())
    except errors.APIError as e:
        print(api_error_message(e.code, e.message))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
