# Baseline regressions

## ADDED Requirements

### Requirement: Обнаружение SQL отделено в отчёте от доказанного выполнения
Baseline SHALL фиксировать текущую ложную связь без объявления её целевым поведением.

#### Scenario: SQL только объявлен
- GIVEN метод с неиспользованной строкой DELETE.
- WHEN строится legacy-граф.
- THEN запрос сохраняется и метод получает ошибочное ребро executes.

### Requirement: Конфликт констант воспроизводим
#### Scenario: Два класса с одинаковым именем поля
- GIVEN классы A и B с разными TABLE и методами чтения.
- WHEN разбирается файл.
- THEN оба метода ошибочно используют последнюю TABLE.

### Requirement: Неоднозначность перегрузок воспроизводима
#### Scenario: Перегруженные методы
- GIVEN методы m(int) и m(String).
- WHEN извлекаются символы.
- THEN оба сохраняются с одинаковым qualified_name A.m.

### Requirement: Потеря quoted identity воспроизводима
#### Scenario: Quoted и обычная таблица
- GIVEN запросы к "Users" и users.
- WHEN анализируется SQL.
- THEN оба ошибочно имеют ключ users.

### Requirement: Восстановление AST не останавливает соседние файлы
#### Scenario: Синтаксическая ошибка
- GIVEN некорректный Java-файл и корректный соседний файл.
- WHEN строится граф.
- THEN оба файла присутствуют, корректный метод извлечён, parser diagnostic отсутствует в failed.

### Requirement: Источник dirty worktree явно зафиксирован
#### Scenario: Изменён tracked-файл
- GIVEN локальный commit, изменённый tracked Java-файл и новый untracked-файл.
- WHEN список repos.files передан indexer.build.
- THEN граф содержит текущие tracked bytes, untracked отсутствует, HEAD прежний и изменения сохранены.

### Requirement: Конфликт basename воспроизводим без БД
#### Scenario: Разные пути с одним basename
- GIVEN два локальных каталога app и существующая запись первого источника.
- WHEN регистрируется второй источник.
- THEN resolve выдаёт одинаковые имена и register отклоняет второй источник до INSERT.

### Requirement: Динамический SQL сохраняет неполноту
#### Scenario: Неизвестный параметр строки
- GIVEN SQL со статическими таблицей и колонками и динамическим значением.
- WHEN строится граф.
- THEN неизвестное значение заменено __unknown__, partial=true, parsed=true и известные accesses сохранены без фиктивной колонки placeholder.
