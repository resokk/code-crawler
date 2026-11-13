/*
 * PL/PLUS (ЦФТ, *.plp) — лексер.
 */
lexer grammar PlpLexer;

options { caseInsensitive = true; }

// ---------------------------------------------------------------- keywords
ALL          : 'all';
ANY          : 'any';
AND          : 'and';
ARRAY        : 'array';
AS           : 'as';
ASC          : 'asc';
BEGIN        : 'begin';
BETWEEN      : 'between';
BULK         : 'bulk';
BY           : 'by';
CASE         : 'case';
CLOSE        : 'close';
COLLECT      : 'collect';
COLLECTIONS  : 'collections';
COMMIT       : 'commit';
CONNECT      : 'connect';
CONST        : 'const';
CONSTANT     : 'constant';
CONTINUE     : 'continue';
CURSOR       : 'cursor';
DECLARE      : 'declare';
DEFAULT      : 'default';
DELETE       : 'delete';
DESC         : 'desc';
DISTINCT     : 'distinct';
ELSE         : 'else';
ELSIF        : 'elsif';
END          : 'end';
ESCAPE       : 'escape';
EXACT        : 'exact';
EXCEPTION    : 'exception';
EXECUTE      : 'execute';
EXISTS       : 'exists';
EXIT         : 'exit';
FALSE        : 'false';
FETCH        : 'fetch';
FIRST        : 'first';
FOR          : 'for';
FUNCTION     : 'function';
GOTO         : 'goto';
GROUP        : 'group';
HAVING       : 'having';
IF           : 'if';
IMMEDIATE    : 'immediate';
IN           : 'in';
INDEX        : 'index';
INSERT       : 'insert';
INTERSECT    : 'intersect';
INTO         : 'into';
IS           : 'is';
LAST         : 'last';
LIKE         : 'like';
LIMIT        : 'limit';
LOCK         : 'lock';
LOCATE       : 'locate';
LOOP         : 'loop';
MINUS        : 'minus';
NOCOPY       : 'nocopy';
NOT          : 'not';
NULL_        : 'null';
NULLS        : 'nulls';
OF           : 'of';
OPEN         : 'open';
OR           : 'or';
ORDER        : 'order';
OTHERS       : 'others';
OUT          : 'out';
PRAGMA       : 'pragma';
PRIOR        : 'prior';
PROCEDURE    : 'procedure';
RAISE        : 'raise';
RECORD       : 'record';
REF          : 'ref';
RETURN       : 'return';
RETURNING    : 'returning';
REVERSE      : 'reverse';
ROLLBACK     : 'rollback';
SAVEPOINT    : 'savepoint';
SELECT       : 'select';
SOME         : 'some';
START        : 'start';
SUBTYPE      : 'subtype';
TABLE        : 'table';
THEN         : 'then';
TO           : 'to';
TRUE         : 'true';
TYPE         : 'type';
UNION        : 'union';
UPDATE       : 'update';
USING        : 'using';
VAR          : 'var';
VARRAY       : 'varray';
VARYING      : 'varying';
WHEN         : 'when';
WHERE        : 'where';
WHILE        : 'while';
WITH         : 'with';

// ---------------------------------------------------------------- operators
ASSIGN       : ':=';
EQEQ         : '==';
ARROW        : '=>';
RANGE        : '..';
DCOLON       : '::';
CONCAT       : '||';
POWER        : '**';
NOT_EQUAL    : '!=' | '<>' | '^=' | '~=';
LE           : '<=';
GE           : '>=';
POINTER      : '->';
LLABEL       : '<<';
RLABEL       : '>>';
LPAREN       : '(';
RPAREN       : ')';
COMMA        : ',';
SEMI         : ';';
DOT          : '.';
COLON        : ':';
PERCENT      : '%';
PLUS         : '+';
MINUS_SIGN   : '-';
STAR         : '*';
SLASH        : '/';
EQ           : '=';
LT           : '<';
GT           : '>';
AT           : '@';

// ---------------------------------------------------------------- literals & names
NUMBER
    : DIGIT+ ('.' DIGIT+)? EXPONENT?
    | '.' DIGIT+ EXPONENT?
    ;

STRING       : '\'' ('\'\'' | ~'\'')* '\'';

// [CLASS], [ATTR], [1], [ ] — квалификаторы метамодели ЦФТ
BRACKET_ID   : '[' ~[\]\r\n']* ']';

// &MACRO, &BASE$SETVARS, &METHOD$
MACRO        : '&' ID_START ID_PART*;

QUOTED_ID    : '"' ~["\r\n]+ '"';

ID           : ID_START ID_PART*;

// Служебная строка сортировки представления после запроса: |DATE_CONTACT D|NAME A
CRITERIA_ORDER : '|' [\p{L}_] ~[\r\n]*;

// ---------------------------------------------------------------- hidden
// Условная компиляция в комментариях: --#ifdef X ... --#else ... --#endif.
// Ветка --#else скрывается целиком, разбирается основная ветка.
PREPROC_ELSE  : '--#' [ \t]* 'else' .*? '--#' [ \t]* 'end' [ \t]* 'if'? -> channel(HIDDEN);
LINE_COMMENT  : '--' ~[\r\n]*            -> channel(HIDDEN);
BLOCK_COMMENT : '/*' .*? '*/'            -> channel(HIDDEN);
WS            : [ \t\r\n\f\u00A0\uFEFF]+ -> channel(HIDDEN);

fragment DIGIT    : [0-9];
fragment EXPONENT : 'e' [+-]? DIGIT+;
fragment ID_START : [\p{L}_];
fragment ID_PART  : [\p{L}\p{N}_$#];
