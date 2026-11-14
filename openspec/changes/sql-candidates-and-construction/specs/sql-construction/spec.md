# SQL construction requirements

- Discovery MUST сохранять SQL без execution sink и MUST NOT создавать EXECUTES_SQL.
- Construction MUST принадлежать Symbol и иметь непустые уникальные variants.
- Fragment concatenation MUST совпадать с text; dynamic MUST иметь partial reasons.
- Lexical constants MUST учитывать owner, local/parameter shadowing и this receiver.
- Branches MUST сохранять варианты; path overflow MUST быть явной ошибкой.
- Unknown transforms MUST давать partial, а literal __unknown__ MUST оставаться STATIC.
- Storage/readiness MUST сохранять order, ranges, reasons и immutable lifecycle.
- No-change incremental indexing MUST переносить эквивалентные construction facts.
