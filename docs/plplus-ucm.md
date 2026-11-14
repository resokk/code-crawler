# PL/Plus UCM adapter

`PlplusSourceAdapter` (`plplus/1`) маршрутизирует captured `.plp` bytes через
существующую ANTLR 4.13.2 грамматику. UTF-8 strict, SLL-first/LL fallback;
lexer/parser diagnostics сохраняются в SourceAnalysis с UTF-8 byte columns и
exclusive end. Syntax/encoding errors подавляют semantic facts файла.
Generated sources и legacy `plp.parse`/CLI `index` не меняются.

## Symbols and calls

Каждый файл имеет FILE scope и синтетического section owner. Для пути
`.../CLASS/methods/OP/src/SECTION.plp` или `.../CLASS/criteria/VIEW/src/SECTION.plp`
сохраняются source-derived CFT class и operation/view symbols. Их identity включает
полный путь секции: это source owners, не доказанная единая runtime definition.
Вне такого пути владелец явно `<unit:path>`, класс ЦФТ не угадывается.

Из AST извлекаются procedures/functions (включая forward specs и nested bodies),
parameters, variables, lexical scopes и declaration/read/write/call occurrences.
Unquoted identifiers case-insensitive; quoted identifiers сохраняют case.
Lexical variable references разрешаются только при однозначном visible binding.
Loops вводят собственную область. Поля record/types, cursor record shapes,
exception names и alias/property chains не выдаются за доказанные lexical targets.

Short calls ищут lexical declarations и top-level definitions той же операции;
explicit CFT calls — source definitions из того же namespace export root.
CALLS relations имеют PARTIAL/AMBIGUOUS candidates и UNKNOWN certainty, не compiler
proof применимости перегрузки. Missing targets — typed ExternalReferences.
prepare строит каталог из captured bytes; его fingerprint входит в analysis_version,
чтобы добавление/удаление/изменение definitions инвалидировало stale candidates.
Каталог хранит только definitions; parse tree файла живёт лишь на время его
обработки, поэтому каждый файл разбирается дважды — для каталога и для анализа.

## CFT accesses

PL/Plus queries не передаются в sqlglot и не создают SQL_STATEMENT/DATA_ACCESS.
CFT class/attribute selectors представлены unresolved ExternalReferences:
`cft.class::CLASS`, `cft.attribute::CLASS::ATTR` (или `cft.attribute::<unknown>::ATTR`).
Связанные occurrences имеют READ/WRITE, Evidence.rule задаёт operation/role:
`cft.READ.CLASS`, `cft.UPDATE.CLASS`, `cft.READ.ATTRIBUTE.where`,
`cft.WRITE.ATTRIBUTE.write` и аналогичные select/group/having/order роли.
Class UPDATE/INSERT/DELETE targets — writes; predicates и RHS attribute values — reads.

Alias binding ограничен lexical query scope; nested queries не смешивают aliases.
Ambiguous aliases/collection/pointer sources остаются unknown, correlation за
пределами однозначного lexical alias не угадывается. Bare `[ATTR]` в операции
связывается с source-derived own class, за пределами export path — unknown.
Physical `z#...`/`c_...`, standard operation implicit DML, DB schema/version identity
не выводятся без metadata. Native `execute immediate` не анализируется этим adapter.

## Coverage and integration

Parser diagnostics COMPLETE только для корректного source; symbols, calls и CFT
accesses PARTIAL. Макросы не раскрываются; macro/preprocessor tokens дают WARNING,
ветки conditional compilation не объявляются полной runtime coverage. SQL hidden
inside macros, PL/SQL-only syntax, type inference, cross-language linking и CFT
metadata resolution вне контракта.

CLI `adapters list` публикует descriptor; `index-sources` включает PL/Plus вместе
с Java и Groovy. Snapshot остаётся BUILDING до отдельной validation/publication.
Storage использует существующие Symbol/Scope/Occurrence/Relation/ExternalReference
entities и SourceAnalysis, без новой миграции. Unit и PostgreSQL integration tests
проверяют source provenance, recovery, CFT accesses, catalog invalidation и roundtrip.
