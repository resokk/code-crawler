# Source range offset cache

Adapter result validation split the whole file into lines for every SourceRange.
Build line start offsets once per file and reuse them for every diagnostic, fact
and Evidence range. Additionally reject positions that pass the end of their line
or fall inside a multi-byte UTF-8 character. No adapter contract or storage change.
