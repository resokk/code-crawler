# Java parser diagnostics

## Проблема и цель

Tree-sitter восстанавливает некорректный AST, но текущий Java API не сообщает об ошибках и хранит только строки деклараций. Нужны воспроизводимые diagnostics, точные диапазоны и provenance исходных bytes без переписывания extraction.

## Границы

Расширение Java API, file attrs и CLI diagnostics, отдельный Parser на вызов, per-file read stability. Не исправляем scope констант, overload signatures, calls и SQL execution: они остаются следующими changes. Старый java.parse API продолжает возвращать list[Symbol].
