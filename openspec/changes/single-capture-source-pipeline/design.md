# Design

`_Worktree` is the captured source inventory: commit, branch, dirty flag, the Git
listing, SourceInput bytes and a stat signature (inode, size, mtime, ctime) per
file. `index_sources` and `index_java_*` pass it to `index_incremental(captured=)`.

`_verify` replaces the final full re-capture: it compares HEAD, branch, dirty and
the Git listing, then lstat-s every listed file; only files whose signature changed
are re-read and compared by SHA-256, so a touch without a content change passes.

Known limit: an in-place rewrite that preserves inode, size, mtime and ctime is not
detected (the same limit as Git's stat cache). Legacy migration uses `_verify` too.
