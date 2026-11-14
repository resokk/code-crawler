"""Fail-closed parsing of captured PL/Plus bytes with source diagnostics."""

from dataclasses import dataclass

from antlr4 import CommonTokenStream, InputStream, ParserRuleContext
from antlr4.atn.PredictionMode import PredictionMode
from antlr4.error.Errors import ParseCancellationException
from antlr4.error.ErrorStrategy import BailErrorStrategy

from code_crawler.antlr_source import AntlrSourceMap, SourceErrors
from code_crawler.incremental import SourceInput
from code_crawler.plplus.PlpLexer import PlpLexer
from code_crawler.plplus.PlpParser import PlpParser
from code_crawler.ucm import Position, SourceDiagnostic, SourceRange


@dataclass(frozen=True)
class PlplusParseResult:
    tree: ParserRuleContext | None
    mapping: AntlrSourceMap | None
    diagnostics: tuple[SourceDiagnostic, ...]
    tokens: tuple
    prediction_mode: str


def parse_plplus(source: SourceInput) -> PlplusParseResult:
    """Try SLL then LL, retaining final lexer/parser errors without console output."""
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
            code="plplus.INVALID_UTF8",
            message="Source is not valid UTF-8",
            source_range=SourceRange(
                source_file_id=source.file.id,
                start=position(error.start),
                end=position(error.end),
            ),
        )
        return PlplusParseResult(None, None, (diagnostic,), (), "NONE")
    mapping = AntlrSourceMap(source, text)
    for mode in ("SLL", "LL"):
        lexer = PlpLexer(InputStream(text))
        lexer.removeErrorListeners()
        lex_errors = SourceErrors(mapping, "LEXER_ERROR", "plplus")
        lexer.addErrorListener(lex_errors)
        stream = CommonTokenStream(lexer)
        parser = PlpParser(stream)
        parser.removeErrorListeners()
        parse_errors = SourceErrors(mapping, "SYNTAX_ERROR", "plplus")
        parser.addErrorListener(parse_errors)
        parser._interp.predictionMode = (
            PredictionMode.SLL if mode == "SLL" else PredictionMode.LL
        )
        if mode == "SLL":
            parser._errHandler = BailErrorStrategy()
        try:
            tree = parser.compilationUnit()
        except ParseCancellationException:
            if mode == "SLL":
                continue
            tree = None
            parse_errors.diagnostics.append(
                SourceDiagnostic(
                    severity="ERROR",
                    code="plplus.SYNTAX_ERROR",
                    message="PL/Plus parse cancelled",
                )
            )
        diagnostics = tuple(lex_errors.diagnostics + parse_errors.diagnostics)
        if mode == "SLL" and diagnostics:
            continue
        return PlplusParseResult(tree, mapping, diagnostics, tuple(stream.tokens), mode)
    raise RuntimeError("PL/Plus parser did not complete")
