# UCM incremental indexing

## ADDED Requirements

### Requirement: Авторитетный inventory
#### Scenario: Dirty worktree и необычные пути
- GIVEN committed regular Java file с пробелом/переводом строки в имени, symlink и untracked file.
- WHEN bytes tracked файла меняются без изменения HEAD.
- THEN inventory сохраняет точный path/bytes, fingerprint меняется, dirty=true, untracked и symlink отсутствуют; detached HEAD даёт branch=null.

#### Scenario: Безопасная граница root
- GIVEN tracked каталог заменён symlink на внешний каталог.
- WHEN выполняется capture.
- THEN внешний файл не читается и не попадает в inventory.

#### Scenario: Git conflict
- GIVEN unresolved merge conflict.
- WHEN выполняется capture.
- THEN операция отклоняется.

### Requirement: FileAnalysis контракт
#### Scenario: Недопустимый путь или SourceFile override
- GIVEN traversal/absolute/noncanonical path или dependency, либо SourceFile в analyzer entities.
- WHEN создаётся FileAnalysis.
- THEN validation отклоняет результат.

### Requirement: Транзитивная invalidation
#### Scenario: Metadata dependency
- GIVEN A→B→config и независимый C.
- WHEN fingerprint config меняется.
- THEN reanalyze содержит только A/B, C переиспользуется, commit может остаться прежним.

#### Scenario: Добавление negative dependency и циклы file dependencies
- GIVEN A зависит от отсутствующего файла, B зависит от A, A также зависит от B.
- WHEN отсутствующий файл становится tracked.
- THEN A/B инвалидируются транзитивно без бесконечного обхода.

#### Scenario: Profile и language
- GIVEN неизменные bytes.
- WHEN analysis_version/profile меняется.
- THEN все поддерживаемые файлы переанализируются.
- WHEN меняется language файла.
- THEN он отмечен changed.
- WHEN отличается только Git diff hint при одинаковых fingerprints/profile.
- THEN он может переиспользоваться.

### Requirement: Reuse immutable facts
#### Scenario: Нет изменений
- GIVEN опубликованный snapshot с полным manifest.
- WHEN повторяется build с тем же профилем.
- THEN callback не вызывается, все parser files reused, UCM facts нового snapshot равны прежним, pointer остаётся прежним до отдельной публикации.

#### Scenario: Structural references и rename
- GIVEN A.TypeRef→B, SQL Value в A и независимый C.
- WHEN B меняется и commit обновляется.
- THEN Git diff показывает B, A/B переанализируются.
- WHEN B переименован.
- THEN старые owned IDs B исчезают, новый файл добавляется, A переанализируется и сохраняет unresolved reference при отсутствии старой цели; SQL Value остаётся прежним.
- WHEN тот же worktree разбирается полностью.
- THEN полный и инкрементальный UCM графы совпадают.

#### Scenario: Baseline без manifest
- GIVEN опубликованный foundation snapshot без incremental profile и недоступный baseline commit.
- WHEN выполняется incremental build.
- THEN все текущие supported files разбираются, а не переиспользуются неизвестные facts.

### Requirement: Атомарная новая версия
#### Scenario: Сбой анализа, source drift или неполный callback
- GIVEN прежний опубликованный snapshot.
- WHEN parser падает, файл меняется во время callback или результат не покрывает все requested files.
- THEN build отклоняется, pointer и прежние facts остаются.

#### Scenario: Ошибка manifest COPY
- GIVEN новый build после успешного baseline.
- WHEN запись manifest падает после canonical INSERT.
- THEN facts нового snapshot и его profile/ownership откатываются вместе; старая публикация сохранена.

#### Scenario: Immutable manifest
- GIVEN новый snapshot прошёл validation.
- WHEN удаляется его ownership metadata.
- THEN guard запрещает запись.
