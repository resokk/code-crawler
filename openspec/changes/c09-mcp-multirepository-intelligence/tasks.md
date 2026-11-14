# Tasks: MCP-инструменты межрепозиторного Code Intelligence

**Priority:** P1  
**Dependencies:** A02,C03,C04,C06,C08

- [ ] 1. Воспроизвести исходное ограничение/сценарий на фиксированном fixture и описать expected output.
- [ ] 2. Описать точный контракт полей/API, правила versioning и backwards compatibility.
- [ ] 3. Реализовать: Добавить MCP tools search_global, resolve_external_reference, trace_cross_repository, impact_analysis с версионированным context.
- [ ] 4. Реализовать: В каждом запросе проверять principal ACL, max depth/limit/fanout/time, input selectors и cancellation.
- [ ] 5. Реализовать: Стандартизировать вывод candidates, resolution, evidence path, source snapshot, coverage, truncation, explainability.
- [ ] 6. Реализовать: Сделать error handling без утечки недоступных репозиториев; docs с реальными примерами запросов.
- [ ] 7. Добавить сценарий acceptance test: Global candidate search
- [ ] 8. Добавить сценарий acceptance test: Impact analysis
- [ ] 9. Добавить сценарий acceptance test: ACL enforcement
- [ ] 10. Добавить сценарий acceptance test: Limits
- [ ] 11. Добавить negative tests: разные snapshots/repos, ambiguity, partial resolution, denied access и rollback.
- [ ] 12. Если меняется storage — отдельная migration + PostgreSQL 15 integration tests; никакой DDL вне миграций.
- [ ] 13. Обновить docs и Coverage/Resolution/Evidence, проверить отсутствие ложных DEFINITE/STATIC_PROVEN связей.
- [ ] 14. Запустить ruff, pytest/PG15 CI; зафиксировать coverage и benchmark при необходимости.
- [ ] 15. По завершении перенести change в archive, не удаляя его спецификации.
