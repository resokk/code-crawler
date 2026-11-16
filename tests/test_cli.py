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


def test_stage_clock_attributes_time_between_ticks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = iter([0, 2, 5, 6, 10, 11, 20])
    monkeypatch.setattr(cli.time, "monotonic", lambda: next(now))
    clock = cli.StageClock()
    clock.tick("каталог", 2)  # 0–2: первый элемент каталога
    clock.tick("каталог", 2)  # 2–5
    clock.tick("проверка")  # 5–6: до начала несчётного этапа — ничьё время
    clock.tick("анализ", 1)  # 6–10: несчётный этап идёт до следующего тика
    clock.tick("анализ", 1)  # 10–11
    report = clock.report()  # 11–20: после последнего счётного тика

    assert clock.spent == {"каталог": 5, "прочее": 10, "проверка": 4, "анализ": 1}
    assert [line.split()[-1] for line in report] == [
        "прочее",
        "каталог",
        "проверка",
        "анализ",
    ]
    assert "50%" in report[0]


@pytest.mark.parametrize(
    "arguments",
    [
        ["snapshot", "validate", "bad-id"],
        ["snapshot", "publish", "11111111-1111-1111-1111-111111111111"],
        [
            "snapshot",
            "publish",
            "11111111-1111-1111-1111-111111111111",
            "--expected-current",
            "invalid",
        ],
    ],
)
def test_snapshot_argument_errors_fail_before_database_access(monkeypatch, arguments):
    import sys

    monkeypatch.setattr(sys, "argv", ["code-crawler", *arguments])
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 2
