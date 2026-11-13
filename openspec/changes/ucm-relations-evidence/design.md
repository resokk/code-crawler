# Решение

Relation — новая EntityEnvelope с прежней схемой логического ID. Типизированные EntityRef задают source и target/candidates через вложенный Resolution. Все отношения содержат непустые Evidence, явные Certainty и Coverage; defaults, которые превращали бы отсутствие данных в подтверждение, отсутствуют.

Resolution различает RESOLVED, UNRESOLVED, AMBIGUOUS и PARTIAL. Неподтверждённые статусы требуют reason и не содержат target; PARTIAL/AMBIGUOUS сохраняют уникальных кандидатов. STATIC_PROVEN требует RESOLVED, но RESOLVED может оставаться INFERRED/UNKNOWN. UNSUPPORTED coverage допускает только UNKNOWN/UNRESOLVED. COMPLETE означает полноту только в пределах указанной capability, не runtime certainty.

RelationKind registry immutable и задаёт допустимые пары EntityType для CONTAINS, DECLARES, REFERENCES, CALLS, CONSUMES, PRODUCES, FLOWS_TO. Проверяются также типы candidates. Нормативная таблица — docs/ucm.md. Валидатор по каталогу проверяет фактические типы, repository и существование endpoints, callable subtypes для CALLS, occurrence kind для DECLARES и SourceFile для evidence. Рекурсивные вызовы допустимы.

Evidence содержит координаты, analyzer/version, rule и description. Пока оно встроено в отношение; отдельное хранение, дедупликация и ID будут определены storage change. Ссылки на внешние репозитории будут представлены ExternalReference в следующем change; текущие отношения локальны.

Не проверяем достоверность текста evidence, границы реального файла, полноту анализа, циклы containment и все ссылки внутри связанных сущностей: это обязанности анализатора и будущей batch validation. Документная JSON Schema выражает структуру, Python validators — межполевые инварианты; EntityDocument и схема расширены аддитивно.
