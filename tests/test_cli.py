import pytest
from rich.console import Console

from code_crawler import cli


@pytest.fixture
def console(monkeypatch: pytest.MonkeyPatch) -> Console:
    console = Console(record=True, width=80)
    monkeypatch.setattr(cli, "console", console)
    return console


def test_operation_reports_success(console: Console) -> None:
    with cli.operation("Индексация") as progress:
        task = progress.add_task("Файлы", total=2)
        progress.advance(task, 2)

    assert "✓ Индексация" in console.export_text()


def test_operation_reports_failure_and_exits(console: Console) -> None:
    with pytest.raises(SystemExit) as exit_info, cli.operation("Индексация"):
        raise RuntimeError("нет доступа к БД")

    assert exit_info.value.code == 1
    assert "✗ Индексация: нет доступа к БД" in console.export_text()
