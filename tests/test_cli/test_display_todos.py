"""show_todos 渲染测试（P1-1）"""

from mini_claude.cli.display import display


TODOS = [
    {"content": "读代码", "status": "completed"},
    {"content": "写实现", "status": "in_progress", "active_form": "编码中"},
    {"content": "跑回归 <script>", "status": "pending"},
]


def test_show_todos_renders_all_statuses(capsys):
    display.show_todos(TODOS)
    out = capsys.readouterr().out

    assert "Todos" in out
    assert "读代码" in out
    assert "编码中" in out  # in_progress 用 active_form
    assert "写实现" not in out  # in_progress 不显示原 content
    assert "跑回归" in out


def test_show_todos_escapes_markup(capsys):
    """todo 内容是 LLM 生成的，rich 标记必须被转义（ISSUE-020 同款教训）"""
    display.show_todos([{"content": "处理 [bold red]危险[/] 标记", "status": "pending"}])
    out = capsys.readouterr().out

    assert "[bold red]危险[/]" in out  # 原样可见，未被渲染成样式


def test_show_todos_empty_clears(capsys):
    display.show_todos([])
    assert "清空" in capsys.readouterr().out


def test_show_todos_none_is_noop(capsys):
    display.show_todos(None)
    assert capsys.readouterr().out == ""
