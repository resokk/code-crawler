# JPA/ORM semantic analysis

Opt-in JavaOrmAnalyzer/index_java_orm расширяет Java/SQL/database graph typed
ORM_MAPPING, ORM_QUERY и ORM_OPERATION. Jakarta/Javax persistence annotations и
EntityManager/Query APIs проверяются по namespace/receiver type, а не basename.
Custom @Entity/@Query или одноимённые методы не становятся persistence facts.

Entity/Table/Column/Id/Version/Transient и field/property access сохраняются с
original Java symbols и logical identifier names. Field/property access выбирается
по @Access/@Id; mixed/unknown access, inheritance, relationships, embedded/secondary
mappings и naming conventions не угадываются. Default names — JPA logical defaults,
а не автоматически snake_case physical names.

persist/merge/remove/find/getReference/refresh/flush — отдельные ORM invocation
intents, без утверждения flush/commit/runtime reachability или SQL execution.
JPQL/entity/property references интерпретируются относительно ORM catalog, не как
physical SQL table/column names. Query declarations/creation не означают execution;
getResultList/getSingleResult/getResultStream/executeUpdate — execution sites.
Named queries сохраняют declaration/reference distinction и ambiguity.

Native queries остаются SQL и получают SQL construction/statement/access/execution
facts при terminal call. JPQL не превращается в SQL_EXECUTE. Schema identity
использует explicit EntityManager assignments и выбранный immutable context;
physical naming требует explicit IDENTITY policy. UNKNOWN naming strategy,
unsupported routing/ORM features и unknown targets сохраняют причины неполноты.

## Mapping profile

Supported annotations: Jakarta/Javax Entity/Table/Column/Id/Version/Transient,
Access/AccessType, MappedSuperclass/Embeddable и NamedQuery/NamedNativeQuery containers.
Spring Data JPA `org.springframework.data.jpa.repository.Query` учитывает literal
nativeQuery flag; неизвестный flag даёт UNKNOWN domain, не default JPQL guess.
Explicit/FQN imports и однозначные persistence wildcard imports распознаются;
неизвестный/конфликтующий wildcard namespace и source-defined lookalikes не выбираются
по basename. Known Java util wildcard не создаёт ambiguity persistence API.

Field/property mode задаётся Access либо уникальным Id/EmbeddedId placement.
Unknown/mixed placement и отсутствие identifier в выбранном mode дают PARTIAL.
Static/transient/@Transient members исключаются; property names следуют JavaBeans
get/is и acronym rule. Basic/Id/Version names/Column flags сохраняются; Id без
explicit nullable flag логически non-null. Relationships/embedded/secondary/inherited
mappings остаются partial и не разворачиваются в угаданные tables/columns/cascades.
Generated identifiers, converters, XML overrides и provider registration не доказываются.

JpaCatalog имеет repository-wide entity names и named definitions. JPQL custom
Entity(name) не подменяется Java simple class name. Qualified HQL class names,
constructor expressions, relationship navigation/fetch joins, vendor syntax и
Criteria API не объявляются полным JPQL compiler coverage. SELECT/UPDATE/DELETE
разбираются в bounded SQLGlot AST subset, но имена разрешаются исключительно по
entity/property mappings; unknown/ambiguous names остаются explicit relations.
JPQL bulk writes обозначают intent, не callbacks или generated SQL effects.

## Invocation/query profile

EntityManager persist/merge/remove/find/getReference/refresh/flush проверяются по
receiver namespace и argument shape. Targets берутся из declared Java entity type
или class literal. Query creation/NamedQuery/Spring annotation не создают invocation
execution. Terminal getResultList/getSingleResult/getSingleResultOrNull/
getResultStream/executeUpdate дают ORM_OPERATION. Return types/flush timing,
managed state, dirty checking, lazy loading, transactions и commit не выводятся.

Local Query/TypedQuery/var handles и aliases/reassignments связывают creation и
terminal; fluent setParameter/setMaxResults/setFirstResult/setHint/setFlushMode/
setLockMode сохраняют query origin. Передача handle в unknown call оставляет
последующий origin unresolved. Interprocedural returned handles и неизвестные query
parameters не угадываются. Branch-dependent native/JPQL origins дают partial
query/native execution links. Named references связываются с declarations по имени,
несколько declarations не выбираются произвольно; persistence-unit registration
и runtime visibility остаются ограничением static repository catalog.

Native terminal создаёт SQL_EXECUTE и links к SQL_CONSTRUCTION/SQL_STATEMENT,
включая native `select 1`, не проходящий общий discovery heuristic. Unknown native
SQL сохраняет execution site с unresolved construction/statements. Declarations
и class-level named native SQL сохраняют statements даже без execution. Shared
semantic builder и database contexts сохраняют typed access facts; JPQL-only sites
не создают SQL_EXECUTE. Contextless declaration records отличны от конкретных
execution-context resolutions. JPA result-set mappings и setParameter value lineage
остаются вне этого покрытия.

## Context, API и lifecycle

`index_java_orm(conn, repository_id, root, assignments=(), dialect="postgres", naming_policy="UNKNOWN")`
строит BUILDING snapshot. Caller отдельно вызывает validate_snapshot/publish_snapshot.
ConnectionAssignment использует EntityManager Symbol.logical_key и существующий
ConnectionContext/database version. Native SQL разрешается по SQL/context profile;
logical ORM table identity требует explicit `naming_policy="IDENTITY"`.
Default UNKNOWN сохраняет ORM_DATABASE_TARGET unresolved даже при known @Table,
поскольку external physical naming strategy может менять explicit logical names.
Ни один policy не доказывает generated SQL или фактическое выполнение/запись.

Profile `java.jpa/1:` включает logical mappings/named definitions/source coordinates,
physical policy и предыдущие Java/schema/SQL fingerprints. Named definition changes
инвалидируют callers; cross-file references входят в ownership/dependency manifests.
No-change facts переносятся без повторного анализа. Base analysis/native facts
кешируются только внутри immutable captured-source analyzer, не server session.

Миграция 0013 хранит mappings/query/operations/names/reasons в normalized typed
extensions, без opaque metadata JSONB. Deferred FK, immutable guards и readiness
checks сохраняют owner/class/CALL/API/effect/query/context consistency. Legacy
parsers/CLI writer сохраняются; новые facts доступны через opt-in API.
