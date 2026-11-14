# Design

`_LineIndex` in source_adapters.py keeps one `array("Q")` of line start offsets per
captured file, filled lazily by `bytes.find` and scoped to one adapter validation
pass, so memory is released after each adapter. A position is valid when its byte
offset lies within its line (the `\n` terminator excluded, end of file allowed)
and the byte at that offset is not a UTF-8 continuation byte.

Benchmark (2000 ranges, one 5000-line file): 193 ms before, 1.3 ms after.
