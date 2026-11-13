from code_crawler import db


def test_diff_migrations_splits_pending_and_unknown() -> None:
    known = ["0001_a.sql", "0002_b.sql", "0003_c.sql"]

    assert db.diff_migrations(known, {"0001_a.sql", "0009_z.sql"}) == (
        ["0002_b.sql", "0003_c.sql"],
        ["0009_z.sql"],
    )
    assert db.diff_migrations(known, set(known)) == ([], [])
