# Java calls

## ADDED Requirements

### Requirement: Проверяемая локальная applicability
#### Scenario: Overloads, widening и recursion
- GIVEN m(int)/m(String), wide(long)/wide(double), литералы и recursive call.
- WHEN выполняется resolution.
- THEN выбирается supported unique declared target, primitive widening выбирает доминирующий вариант, self-call сохраняется с Evidence/INFERRED/PARTIAL Coverage.

#### Scenario: Несколько аргументов
- GIVEN m(int,long)/m(long,int) и два int arguments.
- WHEN проверяются conversions.
- THEN результат AMBIGUOUS, сумма costs или declaration order не выбирает target.

#### Scenario: Unknown/null/varargs
- GIVEN unknown expression, null и varargs expansion.
- WHEN полноты типов недостаточно.
- THEN возвращаются AMBIGUOUS/PARTIAL candidates без target; единственный применимый String overload для null может быть выбран, String/Object null ambiguity сохраняется.

### Requirement: Repository receivers и imports
#### Scenario: Сквозная цепочка
- GIVEN Controller→Service→Repository с типизированными fields в разных файлах одного package.
- WHEN выполняется resolution.
- THEN CALLS связывает handle→run→save.

#### Scenario: Imports/static/chaining
- GIVEN single-type import, public static factory и method call через return type.
- WHEN receiver и signature известны.
- THEN оба declared calls разрешены.

#### Scenario: Explicit static import
- GIVEN imported static method в catalog либо внешнем class.
- WHEN выполняется unqualified invocation.
- THEN локальный target может быть выбран, внешний сохраняет qualified ExternalReference.

#### Scenario: Namespace и shadowing
- GIVEN одноимённый default-package и same-package type либо local type shadowing member type.
- WHEN определяется receiver.
- THEN выбирается same-package type, а local shadow не подменяется global/member target.

### Requirement: Неподдерживаемое не подтверждается
#### Scenario: Inheritance/static/access/generics
- GIVEN inheritance, instance method через class/static context, private foreign method, generic type variable или wildcard type.
- WHEN выполняется resolution вне supported coverage.
- THEN подтверждённый target не создаётся.

#### Scenario: Generic array type variable
- GIVEN method type variable T[][] и одноимённый repository class T.
- WHEN разрешается argument type.
- THEN variable не подменяется class, результат PARTIAL.

### Requirement: Внешние факты и согласованность
#### Scenario: External dependency
- GIVEN imported external receiver без repository target.
- WHEN выполняется resolution.
- THEN ExternalReference UNRESOLVED и EXTERNAL_DEPENDENCY сохраняются, selector signature неизвестна, CALLS не имеет resolved external target.

#### Scenario: Occurrence и reference
- GIVEN resolved method invocation.
- WHEN читаются CALL occurrence и REFERENCES.
- THEN status/target согласованы с CALLS.

### Requirement: Catalog profile и source stability
#### Scenario: Body/catalog changes
- GIVEN одинаковые method signatures с body/comment edit либо изменённая signature.
- WHEN сравниваются analyzer profiles.
- THEN body edit сохраняет profile, signature change меняет его.
- WHEN callback получает bytes другого capture.
- THEN stale catalog отклоняется.

### Requirement: PostgreSQL и incremental integration
#### Scenario: Сохранение и dependencies
- GIVEN полный call chain и unrelated file.
- WHEN snapshot загружен/валидирован/опубликован, затем меняется тело Repository.
- THEN CALLS/Evidence сохранены; зависимые Controller/Service переанализируются, unrelated reused, pointer не меняется до publish.

#### Scenario: Новый type заменяет external reference
- GIVEN опубликованная unresolved call к отсутствующему Client.
- WHEN Client появляется в tracked catalog.
- THEN profile вызывает full rebuild, ExternalReference заменён локальным resolved CALLS.

#### Scenario: Partial results и profile guard
- GIVEN ambiguous, partial и external calls.
- WHEN snapshot проходит storage restore.
- THEN статусы/candidates/ExternalReference сохранены без target.
- WHEN caller передаёт несовпадающий analyzer version.
- THEN incremental build отклоняется до записи.
