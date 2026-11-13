# Решение

ExternalReference — EntityEnvelope в repository источника. Оно содержит локальный EntityRef source, discriminator-based selector SYMBOL/HTTP/DATABASE, optional repository_hint/version_hint, фиксированный UNRESOLVED, reason, evidence, certainty и coverage.

Selector хранит признаки цели, не ID другой сущности. SymbolSelector различает неизвестную сигнатуру (null) и известную пустую (). HTTP selector сохраняет method/path/service; query/fragment в path запрещены. Database selector сохраняет logical connection alias, schema/table без потери регистра. Канонизация типов, URL templates и quoted semantics относится к адаптерам.

ID задаётся ключом callsite/occurrence, не selector: одинаковая внешняя цель может наблюдаться в нескольких местах. Hints не являются доказательством resolution. Документ запрещает resolved target и candidates через extra=forbid. Query-time resolution будет отдельным результатом, опубликованный факт не меняется.

EXTERNAL_DEPENDENCY связывает локальный source с локальным ExternalReference. RESOLVED такой Relation подтверждает только локальный endpoint; CALLS не допускает ExternalReference как target. Правила старых Relations не ослаблены. Certainty ExternalReference оценивает обнаружение зависимости, поэтому STATIC_PROVEN не означает разрешённую внешнюю цель. UNSUPPORTED coverage требует UNKNOWN.

validate_external_reference проверяет source и evidence files по локальному каталогу без обращения к другим индексам. JSON Schema расширена аддитивно; прошлые документы сохраняют совместимость. Существование hints/селекторов во внешних сервисах не проверяется. PostgreSQL storage и query-time resolver входят в последующие changes.
