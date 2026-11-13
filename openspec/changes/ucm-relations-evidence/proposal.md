# UCM relations and evidence

## Проблема и цель

Нужен нормативный контракт связей, который не выдаёт неоднозначные или неполные результаты за доказанные зависимости. Вводим RelationKind registry, Evidence, Resolution, Certainty и Coverage.

## Границы

Контракт, локальная валидация и проверка endpoints по переданному каталогу. Без изменения анализаторов, миграций, исполнения SQL, глобального resolver и ExternalReference. Существующие TypeRef/Occurrence остаются совместимыми.
