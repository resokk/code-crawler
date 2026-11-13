"""Базовый класс парсера Groovy: семантические предикаты грамматики.

Перенесено на Python из Apache Groovy (SemanticPredicates).
"""

import sys
from typing import TextIO

from antlr4 import Parser, ParserRuleContext, TokenStream

_MODIFIERS = (
    "DEF",
    "VAR",
    "NATIVE",
    "SYNCHRONIZED",
    "TRANSIENT",
    "VOLATILE",
    "PUBLIC",
    "PROTECTED",
    "PRIVATE",
    "STATIC",
    "ABSTRACT",
    "SEALED",
    "NON_SEALED",
    "FINAL",
    "STRICTFP",
    "DEFAULT",
)
# Значения pathElement.t: после выражения идут аргументы вызова или замыкание.
_ARGUMENTS = 2
_CLOSURE_OR_LAMBDA = 3


class GroovyParserBase(Parser):
    def __init__(self, input: TokenStream, output: TextIO = sys.stdout) -> None:
        super().__init__(input, output)
        self.inSwitchExpressionLevel = 0
        self._modifiers = {getattr(self, name) for name in _MODIFIERS}

    def isInvalidMethodDeclaration(self) -> bool:
        first = self._input.LT(1).type
        return (
            first
            in (
                self.Identifier,
                self.CapitalizedIdentifier,
                self.StringLiteral,
                self.YIELD,
            )
            and self._input.LT(2).type == self.LPAREN
        )

    def isInvalidLocalVariableDeclaration(self) -> bool:
        stream = self._input
        index = 2
        second = stream.LT(index).type
        if second == self.DOT:
            while True:
                index += 2
                after_name = stream.LT(index).type
                if after_name != self.DOT:
                    break
            if after_name in (self.LT, self.LBRACK):
                return False
            index -= 1
            second = stream.LT(index + 1).type
        else:
            index = 1
        token = stream.LT(index)
        third = stream.LT(index + 2).type
        return (
            token.type != self.BuiltInPrimitiveType
            and token.type not in self._modifiers
            and token.text[:1].islower()
            and third != self.ASSIGN
            and second not in (self.LT, self.LBRACK)
        )

    def isFollowingArgumentsOrClosure(self, context: ParserRuleContext) -> bool:
        if not isinstance(context, type(self).PostfixExprAltContext):
            return False
        path = context.postfixExpression().pathExpression()
        return path.t in (_ARGUMENTS, _CLOSURE_OR_LAMBDA)
