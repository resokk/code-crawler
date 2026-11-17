# Java SQL flow copy-on-write

Forking eagerly copies every variable/value even when neither branch modifies it.
Share the binding graph until a write, preserving all existing SQL candidates,
constructions, evidence, partial reasons and the current path budget (256).

No literal filter, path merging, limit change, SQL/alias inference or database
migration. Existing builder-alias uncertainty remains explicit. Compare complete
fact payloads and timing/RSS with both current main and historical deepcopy.
