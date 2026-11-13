# Решение

EntityType расширяется OPERATION и VALUE. Operation содержит scope_id, operation_kind, ordered tuple input_value_ids/output_value_ids и необязательную callee: TypeRef. Виды READ, ASSIGN, CONCAT, CALL, RETURN имеют нормативные кардинальности из docs/ucm.md. Порядок входов и повтор одного входа сохраняются; выходы уникальны и не пересекаются со входами, поскольку ID относится к определению значения, не к изменяемой переменной.

Value содержит LITERAL/SYMBOLIC/UNKNOWN, scalar literal, partial и optional TypeRef. Неизвестное значение сохраняется с partial=true, symbolic допускает partial. Литералы сохраняют JSON scalar type, включая null и empty string; NaN/Infinity отклоняются. Null literal определяется value_kind=LITERAL, остальные виды не несут payload. Неполное значение не заменяется подтверждённым фактом выполнения SQL.

Минимальный data flow задаётся ссылками на общие Value ID без дублирующих producer/consumer полей. Проверяются локальные кардинальности и формат ID. Существование ссылок, scope/repository consistency, единственность producer и распространение partial относятся к будущему batch validator/анализаторам. Тип цели callee использует имеющийся Resolvable контракт; конвертеры появятся позднее.

Расширение EntityDocument аддитивно; прежние документы и ID остаются совместимыми. Структурная JSON Schema регенерируется; межполевые инварианты проверяются Python model validators, как и в предыдущих changes.
