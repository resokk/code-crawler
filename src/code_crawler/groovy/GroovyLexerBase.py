"""Базовый класс лексера Groovy: поведение, которое грамматика вызывает из действий и предикатов.

Перенесено на Python из Apache Groovy (GroovyLexer.g4, AbstractLexer, SemanticPredicates).
"""

import sys
import unicodedata
from typing import TextIO

from antlr4 import InputStream, Lexer, Token

# После этих токенов `/` — деление, а не начало строки-регулярки.
_NO_REGEX_AFTER = (
    "DEC",
    "INC",
    "THIS",
    "RBRACE",
    "RBRACK",
    "RPAREN",
    "GStringEnd",
    "NullLiteral",
    "StringLiteral",
    "BooleanLiteral",
    "IntegerLiteral",
    "FloatingPointLiteral",
    "Identifier",
    "CapitalizedIdentifier",
)


class GroovySyntaxError(Exception):
    pass


class GroovyLexerBase(Lexer):
    def __init__(
        self, input: InputStream | None = None, output: TextIO = sys.stdout
    ) -> None:
        super().__init__(input, output)
        # Индексатору нужен разбор и с ошибками, поэтому лексер их не бросает.
        self.errorIgnored = True
        self.tokenIndex = 0
        self.lastTokenType = 0
        self.invalidDigitCount = 0
        # Открытые скобки: (текст скобки, тип токена перед ней).
        self._parens: list[tuple[str, int]] = []
        self._no_regex_after = {getattr(self, name) for name in _NO_REGEX_AFTER}

    def emitToken(self, token: Token) -> None:
        self.tokenIndex += 1
        if token.channel == Token.DEFAULT_CHANNEL:
            self.lastTokenType = token.type
        if token.type == self.RollBackOne:
            # Символ, которым закончилось имя в GString, читается заново уже в прежнем режиме.
            self._input.seek(self._tokenStartCharIndex)
            self._interp.line = self._tokenStartLine
            self._interp.column = self._tokenStartColumn
        super().emitToken(token)

    def popMode(self) -> int:
        # Закрывающая скобка без открывающей: остаёмся в текущем режиме.
        if not self._modeStack:
            return self._mode
        return super().popMode()

    def rollBackOneAction(self) -> None:
        last = self._input.LA(-1)
        if self._input.LA(1) == Token.EOF and last in (ord('"'), ord("/")):
            self._type = self.GStringEnd
        else:
            self._channel = Token.HIDDEN_CHANNEL

    def isRegexAllowed(self) -> bool:
        return self.lastTokenType not in self._no_regex_after

    def enterParen(self) -> None:
        self._parens.append((self.text, self.lastTokenType))

    def exitParen(self) -> None:
        if self._parens:
            self._parens.pop()

    def _inside_parens(self) -> bool:
        # Переводы строк игнорируются внутри ( ), [ ] и ?[ ], но не внутри { }
        # и не в скобках try (...).
        if not self._parens:
            return False
        text, before = self._parens[-1]
        return (text == "(" and before != self.TRY) or text in ("[", "?[")

    def ignoreTokenInsideParens(self) -> None:
        if self._inside_parens():
            self._channel = Token.HIDDEN_CHANNEL

    def ignoreMultiLineCommentConditionally(self) -> None:
        if self._inside_parens() or not self._followed_by_whitespace():
            self._channel = Token.HIDDEN_CHANNEL

    def _followed_by_whitespace(self) -> bool:
        index = 1
        while (char := self._input.LA(index)) not in (ord("\r"), ord("\n"), Token.EOF):
            if char not in (ord(" "), ord("\t"), 0x0C, 0x0B):
                return False
            index += 1
        return True

    def addComment(self, kind: int) -> None:
        pass

    def require(
        self, condition: bool, message: str, offset: int, with_position: bool
    ) -> None:
        if condition:
            return
        if with_position:
            message = f"{message} @ line {self.line}, column {self.column + 1 + offset}"
        raise GroovySyntaxError(message)

    def isFollowedBy(self, *chars: str) -> bool:
        return self._input.LA(1) in {ord(char) for char in chars}

    def isFollowedByJavaLetterInGString(self) -> bool:
        char = self._input.LA(1)
        if char == ord("$") or char < 0:
            return False
        if char <= 0x7F:
            return chr(char) == "{" or chr(char) == "_" or chr(char).isalpha()
        return self.isJavaIdentifierPart(char)

    @staticmethod
    def isUpperCase(code_point: int) -> bool:
        return code_point >= 0 and chr(code_point).isupper()

    @staticmethod
    def isJavaIdentifierStart(code_point: int) -> bool:
        if code_point < 0:
            return False
        char = chr(code_point)
        return char.isidentifier() or unicodedata.category(char) == "Sc"

    @staticmethod
    def isJavaIdentifierPart(code_point: int) -> bool:
        if code_point < 0:
            return False
        char = chr(code_point)
        return ("a" + char).isidentifier() or unicodedata.category(char) == "Sc"

    isJavaIdentifierStartAndNotIdentifierIgnorable = isJavaIdentifierStart
    isJavaIdentifierPartAndNotIdentifierIgnorable = isJavaIdentifierPart

    @staticmethod
    def toCodePoint(high: int, low: int) -> int:
        return 0x10000 + ((high - 0xD800) << 10) + (low - 0xDC00)
