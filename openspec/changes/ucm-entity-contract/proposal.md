# UCM entity contract

## Проблема

Legacy-граф не задаёт нормативных сущностей, идентичности и координат для независимых адаптеров.

## Цель и границы

Ввести версию 1 Entity Envelope, SourceFile, SourceRange, EntityType registry, детерминированные ID и экспорт JSON Schema. Базовые сущности CLASS, METHOD и SQL_CANDIDATE можно сериализовать и валидировать до внедрения детальной семантики.

Symbol/Scope/Occurrence, отношения и Evidence, конвертеры Java/SQL, snapshots и PostgreSQL writer остаются следующим changes. Существующие анализаторы продолжают работать через legacy-контракт.
