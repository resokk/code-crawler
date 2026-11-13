"""Разбор PL/Plus (ЦФТ): функции, запросы к классам, вызовы операций, запись своих реквизитов."""

from dataclasses import dataclass, field

from antlr4 import CommonTokenStream, InputStream, ParserRuleContext
from antlr4.atn.PredictionMode import PredictionMode
from antlr4.error.Errors import ParseCancellationException
from antlr4.error.ErrorStrategy import BailErrorStrategy, DefaultErrorStrategy
from antlr4.tree.Tree import TerminalNode

from code_crawler.plplus.PlpLexer import PlpLexer
from code_crawler.plplus.PlpParser import PlpParser

_OPERATIONS = {
    "SelectQueryContext": "select",
    "LocateStatementContext": "select",
    "InsertStatementContext": "insert",
    "UpdateStatementContext": "update",
    "DeleteStatementContext": "delete",
}
_ROLES = {
    "WhereClauseContext": "where",
    "HavingClauseContext": "having",
    "GroupByClauseContext": "group",
    "OrderByClauseContext": "order",
}
_SUBPROGRAMS = ("ProcedureDeclarationContext", "FunctionDeclarationContext")


@dataclass
class Function:
    name: str
    start_line: int
    end_line: int
    parent: int | None  # индекс объемлющей функции


@dataclass
class Query:
    owner: int | None  # индекс функции; None — код вне функций
    operation: str
    text: str
    line: int
    # класс ЦФТ -> способы доступа ("read", "insert", "update", "delete")
    classes: dict[str, set[str]] = field(default_factory=dict)
    # (класс, реквизит) -> роли
    attributes: dict[tuple[str, str], set[str]] = field(default_factory=dict)


@dataclass
class Call:
    owner: int | None
    target: tuple[str, ...]  # (класс, операция) или (класс, операция, функция)
    line: int


@dataclass
class Unit:
    functions: list[Function] = field(default_factory=list)
    queries: list[Query] = field(default_factory=list)
    calls: list[Call] = field(default_factory=list)
    # имена, с которых начинаются цепочки в коде: среди них вызовы функций своего файла
    # или своей операции — (индекс функции-владельца, имя) -> строка первого упоминания
    local_names: dict[tuple[int | None, str], int] = field(default_factory=dict)
    # реквизиты своего объекта, которым код присваивает значение: `[ATTR] := ...`
    own_writes: set[str] = field(default_factory=set)
    syntax_errors: int = 0


def parse(text: str) -> Unit:
    lexer = PlpLexer(InputStream(text))
    lexer.removeErrorListeners()
    stream = CommonTokenStream(lexer)
    parser = PlpParser(stream)
    parser.removeErrorListeners()
    # Быстрый режим SLL разбирает почти всё; полный LL нужен только файлам с ошибками.
    parser._interp.predictionMode = PredictionMode.SLL
    parser._errHandler = BailErrorStrategy()
    try:
        tree = parser.compilationUnit()
    except ParseCancellationException:
        stream.seek(0)
        parser.reset()
        parser._errHandler = DefaultErrorStrategy()
        parser._interp.predictionMode = PredictionMode.LL
        tree = parser.compilationUnit()
    unit = Unit(syntax_errors=parser.getNumberOfSyntaxErrors())
    _walk(tree, None, False, unit, text)
    return unit


def _kind(ctx: object) -> str:
    return type(ctx).__name__


def _rules(ctx: ParserRuleContext, kind: str) -> list[ParserRuleContext]:
    return [child for child in ctx.children or [] if _kind(child) == kind]


def _tokens(ctx: ParserRuleContext) -> list[str]:
    return [
        child.getText().lower()
        for child in ctx.children or []
        if isinstance(child, TerminalNode)
    ]


def _bracket(text: str) -> str:
    """`[Name]` -> `NAME`."""
    return text[1:-1].strip().upper()


def _walk(
    ctx: ParserRuleContext, owner: int | None, in_query: bool, unit: Unit, text: str
) -> None:
    kind = _kind(ctx)
    if kind in _SUBPROGRAMS and _rules(ctx, "SubprogramBodyContext"):
        name = _rules(ctx, "IdentifierContext")
        if name and ctx.stop is not None:
            unit.functions.append(
                Function(
                    name[0].getText().upper(), ctx.start.line, ctx.stop.line, owner
                )
            )
            owner = len(unit.functions) - 1
    elif kind in _OPERATIONS and not in_query:
        query = _query(ctx, owner, text)
        if query.classes:
            unit.queries.append(query)
        in_query = True
    elif kind == "NameChainContext":
        target = _call_target(ctx)
        if target:
            unit.calls.append(Call(owner, target, ctx.start.line))
        elif ctx.start.text.isidentifier():
            unit.local_names.setdefault((owner, ctx.start.text.upper()), ctx.start.line)
    elif kind == "AssignmentOrCallContext" and ":=" in _tokens(ctx):
        chain = _rules(ctx, "NameChainContext")
        prefix = _rules(chain[0], "NamePrefixContext") if chain else []
        if prefix and prefix[0].getText().startswith("["):
            suffixes = _rules(chain[0], "NameSuffixContext")
            if not suffixes or not suffixes[0].getText().startswith("::"):
                unit.own_writes.add(_bracket(prefix[0].getText()))
    for child in ctx.children or []:
        if isinstance(child, ParserRuleContext):
            _walk(child, owner, in_query, unit, text)


def _call_target(chain: ParserRuleContext) -> tuple[str, ...] | None:
    """`::[CLASS].[METHOD]…` и `[CLASS]::[METHOD]…` — обращение к операции класса."""
    prefix = _rules(chain, "NamePrefixContext")
    suffixes = [suffix.getText() for suffix in _rules(chain, "NameSuffixContext")]
    if not prefix or not suffixes:
        return None
    head = prefix[0].getText()
    if head.startswith("::[") and suffixes[0].startswith(".["):
        target = [_bracket(head[2:]), _bracket(suffixes[0][1:])]
    elif head.startswith("[") and suffixes[0].startswith("::["):
        target = [_bracket(head), _bracket(suffixes[0][2:])]
    else:
        return None
    if not all(part and "]" not in part for part in target):
        return None
    if (
        len(suffixes) > 1
        and suffixes[1].startswith(".")
        and suffixes[1][1:].isidentifier()
    ):
        target.append(suffixes[1][1:].upper())
    return tuple(target)


def _class_of(reference: ParserRuleContext | None) -> str | None:
    """Класс ЦФТ, если ссылка — это `::[CLASS]` (а не реквизит-коллекция объекта)."""
    chain = _rules(reference, "NameChainContext") if reference is not None else []
    if _kind(reference) == "NameChainContext":
        chain = [reference]
    if not chain:
        return None
    prefix = _rules(chain[0], "NamePrefixContext")
    head = prefix[0].getText() if prefix else ""
    suffixes = _rules(chain[0], "NameSuffixContext")
    if not head.startswith("::[") or any(
        not s.getText().startswith("(") for s in suffixes
    ):
        return None
    return _bracket(head[2:])


def _statement_of(ctx: ParserRuleContext) -> ParserRuleContext | None:
    node = ctx.parentCtx
    while node is not None and _kind(node) not in _OPERATIONS:
        node = node.parentCtx
    return node


def _alias(statement: ParserRuleContext) -> str | None:
    identifiers = _rules(statement, "IdentifierContext")
    return identifiers[-1].getText().lower() if identifiers else None


def _descendants(ctx: ParserRuleContext, kind: str) -> list[ParserRuleContext]:
    found: list[ParserRuleContext] = []
    stack = [ctx]
    while stack:
        node = stack.pop()
        for child in node.children or []:
            if isinstance(child, ParserRuleContext):
                if _kind(child) == kind:
                    found.append(child)
                stack.append(child)
    return found


def _query(ctx: ParserRuleContext, owner: int | None, text: str) -> Query:
    stop = ctx.stop.stop if ctx.stop is not None else ctx.start.stop
    query = Query(
        owner, _OPERATIONS[_kind(ctx)], text[ctx.start.start : stop + 1], ctx.start.line
    )
    aliases: dict[str, str] = {}

    def add(
        name: str | None, alias: str | None, statement: ParserRuleContext | None
    ) -> None:
        if name is None:
            return
        operation = _OPERATIONS.get(_kind(statement), "select")
        query.classes.setdefault(name, set()).add(
            "read" if operation == "select" else operation
        )
        if alias:
            aliases[alias] = name

    for item in _descendants(ctx, "SourceItemContext"):
        statement = _statement_of(item)
        own_alias = _rules(item, "IdentifierContext")
        alias = own_alias[0].getText().lower() if own_alias else _alias(statement)
        references = _rules(item, "ReferenceContext")
        add(_class_of(references[0]) if references else None, alias, statement)
    for insert in [ctx, *_descendants(ctx, "InsertStatementContext")]:
        if _kind(insert) == "InsertStatementContext":
            chains = _rules(insert, "NameChainContext")
            add(_class_of(chains[-1]) if chains else None, _alias(insert), insert)

    for chain in _descendants(ctx, "NameChainContext"):
        prefix = _rules(chain, "NamePrefixContext")
        suffixes = _rules(chain, "NameSuffixContext")
        name = aliases.get(prefix[0].getText().lower()) if prefix else None
        if name is None or not suffixes or not suffixes[0].getText().startswith(".["):
            continue
        attribute = _bracket(suffixes[0].getText()[1:])
        query.attributes.setdefault((name, attribute), set()).add(_role(chain))
    return query


def _role(chain: ParserRuleContext) -> str:
    node, child = chain.parentCtx, chain
    while node is not None and _kind(node) not in _OPERATIONS:
        if _kind(node) in _ROLES:
            return _ROLES[_kind(node)]
        if _kind(node) == "SetItemContext":
            # Левая часть `x.[A] = v` — запись, правая — чтение.
            return (
                "write" if _rules(node, "ReferenceContext")[:1] == [child] else "select"
            )
        node, child = node.parentCtx, node
    return "select"
