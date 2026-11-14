# Tasks: Выбор согласованного контекста версий репозиториев

**Priority:** P1  
**Dependencies:** C02 может разрабатываться параллельно

- [ ] 1. Воспроизвести исходное ограничение/сценарий на фиксированном fixture и описать expected output.
- [ ] 2. Описать точный контракт полей/API, правила versioning и backwards compatibility.
- [ ] 3. Реализовать: Реализовать resolver_contexts с режимами LATEST_INDEXED, PINNED_SNAPSHOTS, DEPLOYMENT_CONTEXT и immutable selection manifest.
- [ ] 4. Реализовать: Для pinned проверять repo ownership, readiness и наличие retained snapshot; для deployment явное mapping service/deploy to snapshot.
- [ ] 5. Реализовать: Разделить выбор версии, разрешение candidate и publication; missing versions и unknown deployments — явная ошибка/неопределённость.
- [ ] 6. Реализовать: Включать context fingerprint в кэш и Evidence path; поддержать pin retention при GC.
- [ ] 7. Добавить сценарий acceptance test: Pinned snapshots
- [ ] 8. Добавить сценарий acceptance test: Latest indexed
- [ ] 9. Добавить сценарий acceptance test: Deployment uncertainty
- [ ] 10. Добавить сценарий acceptance test: Retention
- [ ] 11. Добавить negative tests: разные snapshots/repos, ambiguity, partial resolution, denied access и rollback.
- [ ] 12. Если меняется storage — отдельная migration + PostgreSQL 15 integration tests; никакой DDL вне миграций.
- [ ] 13. Обновить docs и Coverage/Resolution/Evidence, проверить отсутствие ложных DEFINITE/STATIC_PROVEN связей.
- [ ] 14. Запустить ruff, pytest/PG15 CI; зафиксировать coverage и benchmark при необходимости.
- [ ] 15. По завершении перенести change в archive, не удаляя его спецификации.
