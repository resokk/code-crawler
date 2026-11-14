# Canonical e2e regressions

Полный R1 workflow проверяется в PostgreSQL 15 на committed mixed Java/Groovy/PLPlus
fixture. CLI index-sources --publish создаёт/валидирует/публикует snapshot; canonical
reader читает Java caller → SQL execution → statement → table/access и binding,
затем восстанавливает exact Evidence из archive после удаления checkout.

Проверяется наличие SQL construction у неиспользуемого literal при отсутствии
подтверждённого execution. Groovy/PLPlus reports и semantic facts читаются из той
же публикации, с исходными Coverage/uncertainty. No-change indexing даёт проверяемый
reuse и те же canonical entities; смена pointer не смешивает их с BUILDING facts.

Отдельный fault injection при публикации после indexing/validation подтверждает
rollback pointer/state и сохранность прежнего reader output. Это системная regression,
не замена unit/analyzer/storage tests. Mandatory CI включает её как integration.
