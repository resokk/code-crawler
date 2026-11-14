"""ANTLR codepoint offsets mapped to immutable UTF-8 source ranges."""

from bisect import bisect_right

from antlr4 import ParserRuleContext, Token
from antlr4.error.ErrorListener import ErrorListener

from code_crawler.incremental import SourceInput
from code_crawler.ucm import Position, SourceDiagnostic, SourceRange


class AntlrSourceMap:
    def __init__(self, source: SourceInput, text: str) -> None:
        self.source = source
        self.text = text
        self.bytes = [0]
        self.lines = [0]
        for index, char in enumerate(text):
            self.bytes.append(self.bytes[-1] + len(char.encode("utf-8")))
            if char == "\n":
                self.lines.append(index + 1)

    def position(self, offset: int) -> Position:
        if not 0 <= offset <= len(self.text):
            raise ValueError("ANTLR character offset outside captured source")
        line = bisect_right(self.lines, offset) - 1
        return Position(
            line=line + 1, byte_column=self.bytes[offset] - self.bytes[self.lines[line]]
        )

    def span(self, start: int, end: int) -> SourceRange:
        return SourceRange(
            source_file_id=self.source.file.id,
            start=self.position(start),
            end=self.position(end),
        )

    def range(self, node: ParserRuleContext | Token) -> SourceRange | None:
        start = (
            node.start
            if isinstance(node, Token)
            else node.start.start
            if node.start
            else -1
        )
        stop = (
            node.stop
            if isinstance(node, Token)
            else node.stop.stop
            if node.stop
            else -1
        )
        if start < 0 or stop < start - 1 or start > len(self.text):
            return None
        return self.span(start, min(len(self.text), max(start, stop + 1)))

    def text_of(self, node: ParserRuleContext | Token) -> str:
        start = node.start if isinstance(node, Token) else node.start.start
        stop = node.stop if isinstance(node, Token) else node.stop.stop
        return (
            self.text[start : stop + 1] if 0 <= start <= stop < len(self.text) else ""
        )


class SourceErrors(ErrorListener):
    def __init__(
        self, mapping: AntlrSourceMap, kind: str, language: str = "groovy"
    ) -> None:
        self.mapping = mapping
        self.kind = kind
        self.language = language
        self.diagnostics: list[SourceDiagnostic] = []

    def syntaxError(self, recognizer, offendingSymbol, line, column, msg, e) -> None:
        location = (
            self.mapping.range(offendingSymbol)
            if isinstance(offendingSymbol, Token)
            else None
        )
        if location is None and 1 <= line <= len(self.mapping.lines):
            start = self.mapping.lines[line - 1] + column
            if 0 <= start <= len(self.mapping.text):
                location = self.mapping.span(
                    start, min(start + 1, len(self.mapping.text))
                )
        self.diagnostics.append(
            SourceDiagnostic(
                severity="ERROR",
                code=self.language + "." + self.kind,
                message=msg,
                source_range=location,
            )
        )
