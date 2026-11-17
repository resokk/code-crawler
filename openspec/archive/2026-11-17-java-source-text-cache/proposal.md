# Java source text cache

Repeated Node.text/UTF-8 decoding occurs during parsing, symbol extraction and
path-sensitive SQL recovery. Cache decoded text only during one synchronous
file operation, inside its worker thread; release keys/text at operation end.

Preserve _text(None), empty text, UTF-8 replacement behavior, complete UCM facts
and existing path budgets. No global cross-file cache, new dependencies, schema
migration, literal-based pruning or path merging. Measure hits, time and peak RSS
before claiming an end-to-end improvement.
