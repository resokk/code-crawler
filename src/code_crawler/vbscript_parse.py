"""Bounded ANTLR parsing of captured UTF-8 VBScript; never execute source."""

from dataclasses import dataclass

from antlr4 import CommonTokenStream, InputStream, ParserRuleContext, Token
from antlr4.atn.PredictionMode import PredictionMode
from antlr4.error.Errors import ParseCancellationException
from antlr4.error.ErrorStrategy import BailErrorStrategy
from antlr4.ListTokenSource import ListTokenSource

from code_crawler.antlr_source import AntlrSourceMap, SourceErrors
from code_crawler.incremental import SourceInput
from code_crawler.ucm import SourceDiagnostic
from code_crawler.vbscript.VBScriptLexer import VBScriptLexer
from code_crawler.vbscript.VBScriptParser import VBScriptParser

MAX_BYTES = 2 * 1024 * 1024
MAX_TOKENS = 100_000
MAX_NESTING = 64


@dataclass(frozen=True)
class VbscriptParseResult:
    tree: ParserRuleContext | None
    mapping: AntlrSourceMap | None
    diagnostics: tuple[SourceDiagnostic, ...]


class _Errors(SourceErrors):
    def syntaxError(self, *args) -> None:
        if len(self.diagnostics) < 50:
            super().syntaxError(*args)


def parse_vbscript(source: SourceInput) -> VbscriptParseResult:
    """Return grammar diagnostics; reject oversize, bad encoding and recovered trees."""

    def failure(code: str, message: str) -> VbscriptParseResult:
        return VbscriptParseResult(
            None,
            None,
            (
                SourceDiagnostic(
                    severity="ERROR",
                    code="vbscript." + code,
                    message=message,
                ),
            ),
        )

    if len(source.content) > MAX_BYTES:
        return failure("RESOURCE_LIMIT", "VBScript source exceeds 2 MiB")
    try:
        text = source.content.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return failure("INVALID_UTF8", "VBScript source must be UTF-8")
    if "\x00" in text:
        return failure("INVALID_CHARACTER", "NUL is not permitted in VBScript source")
    mapping = AntlrSourceMap(source, text)
    lexer = VBScriptLexer(InputStream(text))
    lexer.removeErrorListeners()
    errors = _Errors(mapping, "LEXER_ERROR", "vbscript")
    lexer.addErrorListener(errors)
    tokens, nesting = [], 0
    for _ in range(MAX_TOKENS + 1):
        token = lexer.nextToken()
        tokens.append(token)
        nesting += int(token.text == "(") - int(token.text == ")")
        if nesting > MAX_NESTING:
            return failure("RESOURCE_LIMIT", "VBScript parenthesis nesting exceeds 64")
        if token.type == Token.EOF:
            break
    else:
        return failure("RESOURCE_LIMIT", "VBScript source exceeds 100000 tokens")
    if errors.diagnostics:
        return VbscriptParseResult(None, mapping, tuple(errors.diagnostics))
    stream = CommonTokenStream(ListTokenSource(tokens))
    for mode in (PredictionMode.SLL, PredictionMode.LL):
        stream.seek(0)
        parser = VBScriptParser(stream)
        parser.removeErrorListeners()
        diagnostics = _Errors(mapping, "SYNTAX_ERROR", "vbscript")
        parser.addErrorListener(diagnostics)
        parser._interp.predictionMode = mode
        if mode == PredictionMode.SLL:
            parser._errHandler = BailErrorStrategy()
        try:
            tree = parser.program()
        except ParseCancellationException:
            continue
        except RecursionError:
            return failure(
                "RESOURCE_LIMIT", "VBScript syntax nesting exceeds parser limit"
            )
        if diagnostics.diagnostics:
            return VbscriptParseResult(None, mapping, tuple(diagnostics.diagnostics))
        return VbscriptParseResult(tree, mapping, ())
    return failure("SYNTAX_ERROR", "VBScript parser could not complete")
