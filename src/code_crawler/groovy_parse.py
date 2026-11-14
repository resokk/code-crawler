"""Captured-byte Groovy parsing and ANTLR character-to-UTF-8 source provenance."""

from dataclasses import dataclass

from antlr4 import CommonTokenStream, InputStream, ParserRuleContext
from antlr4.atn.PredictionMode import PredictionMode
from antlr4.error.Errors import ParseCancellationException
from antlr4.error.ErrorStrategy import BailErrorStrategy

from code_crawler.antlr_source import AntlrSourceMap as GroovySourceMap
from code_crawler.antlr_source import SourceErrors as _Errors
from code_crawler.groovy.GroovyLexer import GroovyLexer
from code_crawler.groovy.GroovyLexerBase import GroovySyntaxError
from code_crawler.groovy.GroovyParser import GroovyParser
from code_crawler.incremental import SourceInput
from code_crawler.ucm import Position, SourceDiagnostic, SourceRange


@dataclass(frozen=True)
class GroovyParseResult:
    tree: ParserRuleContext | None
    mapping: GroovySourceMap | None
    diagnostics: tuple[SourceDiagnostic, ...]
    prediction_mode: str


def parse_groovy(source: SourceInput) -> GroovyParseResult:
    """Parse immutable UTF-8 bytes, suppressing console errors and retaining LL diagnostics."""
    try:
        text = source.content.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:

        def position(offset: int) -> Position:
            prefix = source.content[:offset]
            return Position(
                line=prefix.count(b"\n") + 1,
                byte_column=len(prefix.rsplit(b"\n", 1)[-1]),
            )

        diagnostic = SourceDiagnostic(
            severity="ERROR",
            code="groovy.INVALID_UTF8",
            message="Source is not valid UTF-8",
            source_range=SourceRange(
                source_file_id=source.file.id,
                start=position(error.start),
                end=position(error.end),
            ),
        )
        return GroovyParseResult(None, None, (diagnostic,), "NONE")
    mapping = GroovySourceMap(source, text)
    for mode in ("SLL", "LL"):
        lexer = GroovyLexer(InputStream(text))
        lexer.errorIgnored = False
        lexer.removeErrorListeners()
        lex_errors = _Errors(mapping, "LEXER_ERROR")
        lexer.addErrorListener(lex_errors)
        parser = GroovyParser(CommonTokenStream(lexer))
        parser.removeErrorListeners()
        parse_errors = _Errors(mapping, "SYNTAX_ERROR")
        parser.addErrorListener(parse_errors)
        parser._interp.predictionMode = (
            PredictionMode.SLL if mode == "SLL" else PredictionMode.LL
        )
        if mode == "SLL":
            parser._errHandler = BailErrorStrategy()
        tree = None
        try:
            tree = parser.compilationUnit()
        except ParseCancellationException:
            if mode == "SLL":
                continue
            parse_errors.diagnostics.append(
                SourceDiagnostic(
                    severity="ERROR",
                    code="groovy.SYNTAX_ERROR",
                    message="Groovy parse was cancelled; no semantic facts produced",
                )
            )
        except GroovySyntaxError as error:
            start = lexer._tokenStartCharIndex
            location = (
                mapping.span(start, min(len(text), max(start, lexer.getCharIndex())))
                if 0 <= start <= len(text)
                else None
            )
            lex_errors.diagnostics.append(
                SourceDiagnostic(
                    severity="ERROR",
                    code="groovy.LEXER_ERROR",
                    message=str(error),
                    source_range=location,
                )
            )
        diagnostics = tuple(lex_errors.diagnostics + parse_errors.diagnostics)
        if mode == "SLL" and diagnostics:
            continue
        return GroovyParseResult(tree, mapping, diagnostics, mode)
    raise RuntimeError("Groovy parser did not complete either prediction mode")
