# Решение

Расширяем EntityType типами SYMBOL, SCOPE, OCCURRENCE. Существующие CLASS/METHOD/SQL_CANDIDATE остаются прежними, поэтому старые JSON-документы продолжают читаться.

Symbol содержит вид декларации, qualified_name и необязательные scope_id/type_ref. METHOD/CONSTRUCTOR требуют owner_key и CallableSignature. Callable key — канонический JSON с owner, name и упорядоченными именами parameter_types. Возвращаемый тип и resolution не влияют на overload identity. Нормализация имён типов — ответственность языкового адаптера.

Scope задаёт тип области, parent_scope_id и owner_symbol_id. Occurrence обязательно содержит scope_id и точный SourceRange; оно может оставаться UNRESOLVED/AMBIGUOUS без target. RESOLVED требует target_symbol_id. TypeRef использует тот же инвариант. Кандидаты неоднозначного разрешения и доказательства будут добавлены контрактом Resolution/Evidence.

Типизированные tuple сохраняют неизменяемость сигнатуры. JSON Schema расширяется аддитивно и проверяется существующим тестом актуальности. Проверка наличия target в batch, типов целей, циклов scope и принадлежности repository пока не реализована; индивидуальный документ проверяет формат ссылок, но не существование сущностей.
