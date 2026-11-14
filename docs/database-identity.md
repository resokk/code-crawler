# Database/schema identity

database_key задаёт явную идентичность прикладной БД независимо от code repository,
DSN и имени каталога. Schema versions импортируются атомарно и неизменяемы; версия
выбирается явно, без implicit latest. Повторный импорт того же content idempotent,
другой content под тем же version_key отклоняется. Legacy schema import сохраняется.

Typed manifest и live PostgreSQL introspection независимы от code indexing.
Catalog/schema/table/view/column names, column types/nullability/ordinal хранятся
нормализованно. Global object key включает database/version и все name parts;
одноимённые объекты разных БД, схем и версий не сливаются. Никакие credentials/DSN
не входят в identity. Quoted PostgreSQL names сравниваются с учётом SQL folding;
MySQL/T-SQL требуют explicit identifier case policy.

ConnectionContext связывает explicit connection key с database/version и ordered
search_path. Java assignment использует canonical Symbol logical_key, а не basename
или имя метода. JDBC prepared/statement aliases сохраняют connection origin.
Unknown routing/context, absent objects, partial catalog, wildcard/derived/ambiguous
columns сохраняют unresolved/partial причины. Без context catalog basename не выбирает БД.

Code snapshot содержит file-owned projections DATABASE_CONTEXT/DATABASE_OBJECT и
DATABASE_ACCESS resolution records. Global object_key одинаков между repositories;
local UCM IDs различаются по repository/file. Database object refs замкнуты внутри
snapshot, а FK ссылаются на immutable imported inventory. Исходные syntactic
DataAccess facts не переписываются: actual identity находится в отдельной
RESOLVES_DATABASE_OBJECT relation с context и Evidence.

## Независимый импорт

```bash
uv run code-crawler schema import-version --database-key orders-prod --version-key release-1
uv run code-crawler schema import-manifest schema.json
```

Первый вариант читает SOURCE_DATABASE_URL в read-only REPEATABLE READ transaction,
переиспользуя datamodel.introspect. В DATABASE_URL записывается новый catalog version;
source DB не изменяется. Сохраняются пустые nonsystem schemas, partitioned/ordinary
tables, views/materialized views/foreign tables, column types, ordinal (gaps allowed),
nullability и primary-key membership. OID не участвует в identity. Foreign keys и
comments legacy introspection не объявляются новой relation/column identity.

Manifest — strict SchemaImport, пример:

```json
{
  "database_key": "orders-prod",
  "version_key": "release-1",
  "dialect": "postgres",
  "catalog_name": "orders",
  "table_case": "EXACT",
  "column_case": "EXACT",
  "coverage": "COMPLETE",
  "schemas": [{"name": "public", "tables": [{
    "name": "users", "kind": "TABLE", "columns": [{
      "name": "id", "ordinal": 1, "data_type": "integer",
      "nullable": false, "primary_key": true
    }]
  }]}]
}
```

API: `import_schema(conn, SchemaImport) -> fingerprint`,
`introspect_schema(source, database_key, version_key) -> SchemaImport`,
`load_schema(conn, database_key, version_key) -> SchemaImport`.
Импорт владеет transaction, поэтому требует free connection. Canonical fingerprint
не зависит от порядка schemas/tables/columns, но включает всю typed metadata,
coverage и case policies. Identity/database/version не переименовываются, inventory
не дополняется после READY. Нет code snapshot, Git checkout или repository dependency
при schema import. Подготовка manifest/rows и fingerprint validation выполняются
в worker thread; DB I/O остаётся async.

## Контекст и разрешение

`ConnectionContext(connection_key, database_key, version_key, search_path)` содержит
ordered actual schema names, а не SQL setting string. Unqualified table без path
остаётся unresolved; fully qualified schema/table разрешается в той же выбранной
БД. Catalog qualifier не переключает database_key. Полный inventory позволяет
учесть отсутствие объекта в более ранней схеме; partial inventory сохраняет candidate
с PARTIAL. Неимпортированные session/system namespaces (`pg_temp`, `pg_catalog`,
information_schema, `$user`) не доказывают precedence public даже при COMPLETE
application inventory. Session SET/search_path routing и implicit temp schemas
не выводятся автоматически.

PostgreSQL UTF-8 profile folding применяется к unquoted ASCII letters, quoted
names и non-ASCII stored spelling сохраняются. PostgreSQL требует EXACT policies.
MySQL column_case требует ASCII_INSENSITIVE; table_case выбирается явно. T-SQL
policies задаются явно. ASCII_INSENSITIVE не объявляется полной vendor collation:
при non-ASCII сравнении, которое профиль не может доказать, resolution unresolved.
SQL statement dialect должен совпадать с выбранным schema version dialect.

Column identity требует known syntactic table binding и наличия колонки в inventory.
Wildcards, ambiguous join columns, derived outputs, absent tables/columns не получают
новых guessed objects. CREATE/ALTER target может отсутствовать в выбранной версии;
DDL не мутирует inventory. Foreign-table identity относится к local foreign object,
а не к предположенной remote database.

## Java adapter и хранение

`ConnectionAssignment(symbol_key=Symbol.logical_key, context=ConnectionContext(...))`
явно назначает context typed Connection/Statement/PreparedStatement или framework
receiver symbol. Для JDBC factory/prepared sites сохраняется connection origin;
statement/prepared aliases несут его дальше. Connection-expression return values,
неизвестные aliases/datasource routing и неназначенные symbols остаются unknown.
Unknown symbol keys, duplicate assignments и отсутствующие imported versions
отклоняются. Несколько possible origins дают partial/ambiguous contexts.

`index_java_database(conn, repository_id, root, assignments, dialect="postgres")`
строит BUILDING snapshot. validate_snapshot/publish_snapshot вызываются отдельно.
Profile `java.database/1:` включает выбранные fingerprints, contexts/search paths,
assignments и предыдущие lineage/semantic/catalog profiles. Для новой версии schema
достаточно нового import и explicit version selection; code change не требуется.

Миграция 0012 нормализует global inventory и snapshot projections. Каждая file-owned
projection имеет отдельный UCM ID, но object_key общий для всех repositories/files.
Contextual resolution хранит access/execution/context раздельно, поэтому одинаковый
SQL для разных connections не схлопывается в один DB target. Unknown/unused SQL
сохраняет unresolved records. Original DataAccess и lineage edges не переписываются.
FK, immutable guards и readiness invariants защищают version/object membership и
projection consistency. Published snapshot продолжает ссылаться на старую версию
после импорта новой. Legacy schema import и CLI index writer не переключаются.

EntityManager assignments и ORM physical naming используют эти же immutable
contexts в [jpa-orm.md](jpa-orm.md). Mapping names разрешаются в DB identity только
под explicit IDENTITY policy; native SQL сохраняет свой SQL name-resolution path.
