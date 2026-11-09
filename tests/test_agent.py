"""エージェントの配線テスト。

TestModel は実際のLLMを呼ばない偽モデルで、登録されたツールを全部呼んでから
ダミーの回答を返す。APIキーも利用枠も使わずに、
「ツールが登録され、呼ばれ、結果がモデルに戻るか」を確かめられる。
"""

from pydantic_ai import DeferredToolRequests, DeferredToolResults, ToolDenied
from pydantic_ai.messages import RetryPromptPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.test import TestModel

from app import tools
from app.agent import agent

BASE_TOOLS = {"search_glossary", "get_lecture_summary", "make_quiz"}


def _parts(result, kind):
    return [p for m in result.all_messages() for p in m.parts if isinstance(p, kind)]


def test_base_tools_are_registered_and_called():
    model = TestModel(call_tools=list(BASE_TOOLS))
    with agent.override(model=model):
        result = agent.run_sync("LoRAとは？")

    offered = {t.name for t in model.last_model_request_parameters.function_tools}
    assert BASE_TOOLS <= offered  # 演習でツールを足しても壊れないよう「含む」で判定
    assert "save_learning_log" in offered

    called = {p.tool_name for p in _parts(result, ToolCallPart)}
    assert BASE_TOOLS <= called
    assert len(_parts(result, ToolReturnPart)) == len(_parts(result, ToolCallPart))
    assert result.output


def test_glossary_result_reaches_the_model():
    model = TestModel(call_tools=["search_glossary"])
    with agent.override(model=model):
        result = agent.run_sync("RAGとは？")
    returns = _parts(result, ToolReturnPart)
    assert returns and returns[0].tool_name == "search_glossary"


def test_save_learning_log_requires_approval_and_saves_when_approved(tmp_path, monkeypatch):
    """save_learning_log は承認待ち（DeferredToolRequests）で一度止まり、承認すると保存されること。"""
    monkeypatch.setattr(tools, "LEARNING_LOG_DIR", tmp_path / "learning_log")
    model = TestModel(call_tools=["save_learning_log"])

    with agent.override(model=model):
        first = agent.run_sync("LoRAについて学んだことを記録して")
        assert isinstance(first.output, DeferredToolRequests)
        assert len(first.output.approvals) == 1
        call = first.output.approvals[0]
        assert call.tool_name == "save_learning_log"
        # 承認前はファイルがまだ作られていないことを確認
        assert not (tmp_path / "learning_log").exists()

        results = DeferredToolResults(approvals={call.tool_call_id: True})
        resumed = agent.run_sync(
            message_history=first.all_messages(),
            deferred_tool_results=results,
        )

    assert isinstance(resumed.output, str)
    returns = _parts(resumed, ToolReturnPart)
    assert any(r.tool_name == "save_learning_log" and "保存しました" in str(r.content) for r in returns)
    assert len(list((tmp_path / "learning_log").glob("*.md"))) == 1


def test_save_learning_log_does_not_save_when_denied(tmp_path, monkeypatch):
    """save_learning_log の承認を拒否（ToolDenied）したときはファイルが保存されないこと。"""
    monkeypatch.setattr(tools, "LEARNING_LOG_DIR", tmp_path / "learning_log")
    model = TestModel(call_tools=["save_learning_log"])

    with agent.override(model=model):
        first = agent.run_sync("LoRAについて学んだことを記録して")
        assert isinstance(first.output, DeferredToolRequests)
        call = first.output.approvals[0]

        results = DeferredToolResults(
            approvals={call.tool_call_id: ToolDenied("利用者が保存をキャンセルしました。")}
        )
        resumed = agent.run_sync(
            message_history=first.all_messages(),
            deferred_tool_results=results,
        )

    assert isinstance(resumed.output, str)
    assert not (tmp_path / "learning_log").exists()
    # 拒否された結果（ToolReturnPart または RetryPromptPart）が履歴に残っていること
    all_parts = _parts(resumed, ToolReturnPart) + _parts(resumed, RetryPromptPart)
    assert any("キャンセル" in str(p.content) for p in all_parts)
