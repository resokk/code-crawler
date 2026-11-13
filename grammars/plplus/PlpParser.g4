/*
 * PL/PLUS (ЦФТ, *.plp) — парсер.
 *
 * Покрывает все виды исходников метода/представления:
 *   public.plp / private.plp   — спецификация и тело библиотеки (объявления);
 *   execute.plp / validate.plp — секция объявлений + тело begin..end;
 *   condition.plp              — `type main is select ...;` (представление).
 *
 * Макросы (&NAME) не раскрываются: вызов макроса разбирается как оператор,
 * объявление или первичное выражение. Поэтому не разбираются места, где
 * макрос раскрывается в незавершённую конструкцию, например
 *   &For_all(i, t) ... end loop;      (макрос открывает цикл)
 *   &SelectDocs and x.[A] = 1 ...     (макрос — начало запроса)

 */
parser grammar PlpParser;

options { tokenVocab = PlpLexer; }

compilationUnit
    : unitItem* CRITERIA_ORDER* EOF
    ;

// тело execute/validate: `begin ... end;` (в конце файла `;` может отсутствовать);
// встречаются и операторы прямо на верхнем уровне, без begin
//
// Блок верхнего уровня вынесен отдельно (а не через statement → block),
// чтобы альтернативы различались по первому токену.
unitItem
    : declaration
    | (DECLARE declaration*)? body SEMI*
    | label* simpleStatement
    ;

// ===================================================================== declarations

declaration
    : pragmaStatement
    | typeDeclaration
    | subtypeDeclaration
    | cursorDeclaration
    | exceptionDeclaration
    | procedureDeclaration
    | functionDeclaration
    | variableDeclaration
    | macroStatement
    ;

pragmaStatement
    : PRAGMA anyName (LPAREN (argument (COMMA argument)*)? RPAREN)? SEMI?
    ;

variableDeclaration
    : identifier (CONSTANT | CONST)? (IN OUT? | OUT)? typeSpec (NOT NULL_)? defaultValue? SEMI
    ;

defaultValue
    : (ASSIGN | DEFAULT) expression
    ;

exceptionDeclaration
    : identifier EXCEPTION SEMI
    ;

typeDeclaration
    : TYPE identifier (IS | AS) typeDefinition SEMI+   // в представлениях встречается `;;`
    ;

typeDefinition
    : RECORD LPAREN fieldDeclaration (COMMA fieldDeclaration)* RPAREN                 # recordType
    | TABLE OF typeSpec (NOT NULL_)? (INDEX BY typeSpec)?                              # tableType
    | (VARRAY | VARYING ARRAY) LPAREN expression RPAREN OF typeSpec (NOT NULL_)?      # varrayType
    | REF CURSOR (RETURN typeSpec)?                                                    # refCursorType
    | selectQuery                                                                      # viewType
    | typeSpec                                                                         # aliasType
    ;

fieldDeclaration
    : identifier typeSpec (NOT NULL_)? defaultValue?
    ;

subtypeDeclaration
    : SUBTYPE identifier IS typeDefinition SEMI
    ;

cursorDeclaration
    : CURSOR identifier parameterList? (RETURN typeSpec)? (IS selectQuery)? SEMI
    ;

procedureDeclaration
    : PROCEDURE identifier parameterList? subprogramModifier* ((IS | AS) subprogramBody | (IS | AS)? SEMI)
    ;

functionDeclaration
    : FUNCTION identifier parameterList? (RETURN | RETURNING) typeSpec subprogramModifier*
      ((IS | AS) subprogramBody | (IS | AS)? SEMI)
    ;

// deterministic, pipelined, ...
subprogramModifier
    : ID
    ;

subprogramBody
    : declaration* body SEMI
    ;

parameterList
    : LPAREN (parameter (COMMA parameter)*)? RPAREN
    ;

parameter
    : identifier (IN OUT? | OUT)? NOCOPY? typeSpec defaultValue?
    ;

// `ref [CLASS]`, `[CLASS]`, `varchar2(100)`, `x%type`, `::[C].[LIB].rec`, `[C]::lib.rec`
typeSpec
    : REF? typeName (LPAREN expression (COMMA expression)* anyName? RPAREN)?
      (WITH ID? ID ID)?                     // timestamp with [local] time zone
    ;

typeName
    : (namePrefix | MACRO) (DOT anyName | DOT BRACKET_ID | DCOLON (BRACKET_ID | anyName) | PERCENT anyName)*
    ;

// ===================================================================== bodies & statements

body
    : BEGIN statements exceptionSection? END identifier?
    ;

exceptionSection
    : EXCEPTION exceptionHandler*
    ;

exceptionHandler
    : WHEN exceptionName (OR exceptionName)* ALL? THEN statements
    ;

exceptionName
    : OTHERS
    | nameChain
    ;

statements
    : statement*
    ;

statement
    : label* (block | simpleStatement)
    ;

label
    : LLABEL identifier RLABEL
    ;

simpleStatement
    : varStatement
    | ifStatement
    | loopStatement
    | caseStatement
    | locateStatement
    | selectStatement
    | updateStatement
    | deleteStatement
    | insertStatement
    | nullStatement
    | exitStatement
    | continueStatement
    | returnStatement
    | gotoStatement
    | raiseStatement
    | openStatement
    | fetchStatement
    | closeStatement
    | transactionStatement
    | executeImmediateStatement
    | pragmaStatement
    | macroStatement
    | assignmentOrCall
    ;

block
    : (DECLARE declaration*)? body SEMI
    ;

// var x number;  — объявление переменной посреди операторов
varStatement
    : VAR variableDeclaration
    ;

// `&debug(...)`, `&For_all(i, t)` — точка с запятой у вызова макроса необязательна
// у присваивания `;` обязательна: иначе выражение могло бы
// продолжиться следующим оператором и предсказание удлинилось бы
macroStatement
    : macroChain ((EQ reference)* ASSIGN expression SEMI | SEMI?)
    ;

// a := v;  a = b := v;  proc(x);
assignmentOrCall
    : nameChain ((EQ reference)* ASSIGN expression)? SEMI
    ;

ifStatement
    : IF expression THEN statements
      (ELSIF expression THEN statements)*
      (ELSE statements)?
      END IF SEMI
    ;

loopStatement
    : (WHILE expression | FOR forHeader)? LOOP statements END LOOP identifier? SEMI
    ;

forHeader
    : identifier IN REVERSE? expression RANGE expression whereClause?       # numericFor
    | identifier IN CURSOR? querySource whereClause? orderByClause?         # objectFor
    | LPAREN selectQuery RPAREN                                             # queryFor
    ;

caseStatement
    : CASE expression? (WHEN expression THEN statements)+ (ELSE statements)? END CASE? SEMI   # sqlCaseStatement
    | CASE expression OF caseBranch* (ELSE statements)? END CASE? SEMI                        # plpCaseStatement
    ;

// :'A', 'B': операторы
caseBranch
    : COLON expression (COMMA expression)* COLON statements
    ;

nullStatement
    : NULL_ SEMI
    ;

exitStatement
    : EXIT identifier? (WHEN expression)? SEMI
    ;

continueStatement
    : CONTINUE identifier? (WHEN expression)? SEMI
    ;

returnStatement
    : RETURN expression? SEMI
    ;

gotoStatement
    : GOTO identifier SEMI
    ;

raiseStatement
    : RAISE nameChain? SEMI
    ;

openStatement
    : OPEN nameChain (FOR (selectQuery | expression) (USING argument (COMMA argument)*)?)? SEMI
    ;

fetchStatement
    : FETCH nameChain (BULK COLLECT)? INTO nameChain (COMMA nameChain)* (LIMIT expression)? SEMI
    ;

closeStatement
    : CLOSE nameChain SEMI
    ;

transactionStatement
    : COMMIT SEMI
    | ROLLBACK (TO SAVEPOINT? identifier)? SEMI
    | SAVEPOINT identifier SEMI
    ;

executeImmediateStatement
    : EXECUTE IMMEDIATE expression
      ((BULK COLLECT)? INTO nameChain (COMMA nameChain)*)?
      (USING argument (COMMA argument)*)?
      SEMI
    ;

// ===================================================================== PL/PLUS data access

// locate x in ::[CLASS] all where ...;
locateStatement
    : LOCATE EXACT? identifier IN querySource whereClause? orderByClause? SEMI
    ;

// select x(x) in ::[CLASS] where ... into v;
selectStatement
    : selectQuery lockClause? intoClause SEMI
    ;

// lock nowait(x%id)
lockClause
    : LOCK nameChain?
    ;

intoClause
    : (BULK COLLECT)? INTO reference (COMMA reference)*
    ;

// return x into v;  returning x%id into v;
returningClause
    : (RETURN | RETURNING) expression (COMMA expression)* intoClause
    ;

// update x(x.[A] = v) in ::[CLASS] all where ...;
// update for i in 1..n loop x(x.[A] = t(i)) in ::[CLASS] where ...;
updateStatement
    : UPDATE (FOR identifier IN expression RANGE expression LOOP)?
      identifier LPAREN setItem (COMMA setItem)* RPAREN
      IN querySource whereClause? returningClause? SEMI
    ;

// delete x in ::[CLASS] all where ...;
deleteStatement
    : DELETE (FOR identifier IN expression RANGE expression LOOP)?
      identifier IN querySource whereClause? returningClause? SEMI
    ;

// insert into ::[CLASS] [for i in a..b loop] x(x.[A] = v, ...);
// insert obj into ::[CLASS];
insertStatement
    : INSERT INTO nameChain (FOR identifier IN expression RANGE expression LOOP)?
      identifier LPAREN setItem (COMMA setItem)* RPAREN returningClause? SEMI
    | INSERT nameChain INTO nameChain returningClause? SEMI
    ;

// слева всегда атрибут: x.[A] = v, x%id = v; произвольное выражение
// здесь внесло бы `=` в FOLLOW выражения и удлинило бы предсказание
setItem
    : reference (EQ | ASSIGN) expression
    ;

selectQuery
    : SELECT DISTINCT? identifier LPAREN DISTINCT? (selectItem (COMMA selectItem)*)? RPAREN
      (IN querySource)?
      whereClause?
      hierarchicalClause?
      groupByClause?
      havingClause?
      orderByClause?
      (setOperator selectQuery)?
    | LPAREN selectQuery RPAREN (setOperator selectQuery)?
    ;

selectItem
    : expression (COLON? identifier)?
    ;

setOperator
    : UNION ALL?
    | MINUS
    | INTERSECT
    ;

// ::[A], (::[B] all : b) all
querySource
    : sourceItem (COMMA sourceItem)* (ALL | COLLECTIONS)?
    ;

sourceItem
    : reference (ALL | COLLECTIONS)?
    | LPAREN reference (ALL | COLLECTIONS)? COLON? identifier RPAREN
    | LPAREN selectQuery RPAREN (COLON? identifier)?
    ;

whereClause
    : WHERE expression
    ;

hierarchicalClause
    : CONNECT BY expression (START WITH? expression)?
    | START WITH? expression CONNECT BY expression
    ;

groupByClause
    : GROUP BY expression (COMMA expression)*
    ;

havingClause
    : HAVING expression
    ;

orderByClause
    : ORDER BY orderItem (COMMA orderItem)*
    ;

orderItem
    : expression (ASC | DESC)? (NULLS (FIRST | LAST))?
    ;

// ===================================================================== expressions

// Уровни разделены (логика → условие → арифметика), чтобы `and` из
// `between x and y` не попадал в FOLLOW правила expression: иначе SLL
// на каждом `and` просматривает условие до конца.
expression
    : NOT expression                                                           # notExpression
    | expression AND expression                                                # andExpression
    | expression OR expression                                                 # orExpression
    | condition                                                                # conditionExpression
    ;

// левая факторизация: оператор условия определяется по первому токену хвоста
condition
    : valueExpression conditionSuffix*      // встречается и `not x is null > 0`
    ;

conditionSuffix
    : (EQ | NOT_EQUAL | LT | GT | LE | GE) valueExpression                    # comparisonCondition
    | IS NOT? NULL_                                                            # isNullCondition
    | NOT? LIKE valueExpression (ESCAPE valueExpression)?                      # likeCondition
    | NOT? BETWEEN valueExpression AND valueExpression                         # betweenCondition
    | NOT? IN LPAREN (selectQuery | expression (COMMA expression)*) RPAREN     # inCondition
    | NOT? IN macroChain                                                       # inMacroCondition
    ;

valueExpression
    : primary                                                                  # primaryExpression
    | <assoc = right> valueExpression POWER valueExpression                    # powerExpression
    | (PLUS | MINUS_SIGN) valueExpression                                      # unaryExpression
    | valueExpression (STAR | SLASH) valueExpression                           # multiplicativeExpression
    | valueExpression (PLUS | MINUS_SIGN | CONCAT) valueExpression             # additiveExpression
    ;

primary
    : literal
    | caseExpression
    | EXISTS LPAREN selectQuery RPAREN
    | (ANY | SOME | ALL) LPAREN selectQuery RPAREN
    | PRIOR primary
    | LPAREN selectQuery RPAREN nameSuffix*
    | LPAREN expression (COMMA expression)* RPAREN
    | macroChain
    | nameChain
    ;

caseExpression
    : CASE expression? (WHEN expression THEN expression)+ (ELSE expression)? END
    ;

literal
    : NUMBER
    | STRING
    | TRUE
    | FALSE
    | NULL_
    ;

// a.[B].[C], ::[CLASS]([CODE] = 'X'), x%id, t(i).f, [C]::[M].proc(a)
nameChain
    : namePrefix nameSuffix*
    ;

namePrefix
    : DCOLON (BRACKET_ID | identifier)
    | BRACKET_ID
    | identifier
    ;

nameSuffix
    : nameSuffixNoCall
    | LPAREN (argument (COMMA argument)*)? RPAREN
    ;

nameSuffixNoCall
    : DOT (anyName | BRACKET_ID | MACRO)
    | DCOLON (BRACKET_ID | anyName)
    | PERCENT LOCATE LPAREN locateArgument RPAREN
    | PERCENT PERCENT? anyName
    | PERCENT? POINTER (LPAREN (argument (COMMA argument)*)? RPAREN)? BRACKET_ID?   // ref%->(::[CLASS])[ATTR]
    | ARROW (BRACKET_ID | anyName)          // this=>[METHOD](...)
    | AT anyName
    ;

// цель into, источник выборки, левая часть присваивания
reference
    : nameChain
    | macroChain
    ;

// &NAME, &NAME(args), &L.proc(x), &T%id
// `::` после макроса не допускается: `&debug(...)` без `;` и следующий
// оператор `::[C].f(...)` иначе склеивались бы в одну цепочку
macroChain
    : MACRO (macroArguments macroSuffix* | (macroSuffixNoCall macroSuffix*)?)
    ;

macroSuffix
    : macroSuffixNoCall
    | LPAREN (argument (COMMA argument)*)? RPAREN
    ;

macroSuffixNoCall
    : DOT (anyName | BRACKET_ID | MACRO)
    | PERCENT anyName
    ;

macroArguments
    : LPAREN macroArgument? (COMMA macroArgument?)* RPAREN
    ;

// Аргумент макроса — обычно выражение, но макрос подставляется текстом,
// поэтому встречаются и фрагменты: `%id`, `.attr`, `select`, `'текст' x`.
// Точка с запятой и `:=` внутри аргументов намеренно не допускаются:
// иначе предсказание ANTLR начинает просматривать файл до конца.
//
// Альтернативы различаются по первому токену, а «хвост» после выражения
// начинается с токена, которым выражение продолжиться не может, —
// иначе каждый аргумент &debug(...) просматривался бы до конца.
macroArgument
    : argument (macroTailStart macroFragment*)?
    | macroLooseStart macroFragment*
    ;

// не может начинать выражение
macroLooseStart
    : PERCENT anyName
    | DOT (anyName | BRACKET_ID)
    | COLON | EQ | NOT_EQUAL | LT | GT | LE | GE | STAR | SLASH | CONCAT
    | AND | OR | IS | IN | LIKE | BETWEEN
    | macroKeyword
    ;

// не может продолжать выражение
macroTailStart
    : identifier
    | literal
    | COLON
    | macroKeyword
    ;

// зарезервированные слова, которые не начинают и не продолжают выражение
macroKeyword
    : BEGIN | BY | DECLARE | ELSE | ELSIF | END | EXCEPTION | EXIT | FOR | FUNCTION
    | GOTO | HAVING | IF | INTERSECT | INTO | LOOP | OF | OUT | PRAGMA | PROCEDURE
    | RAISE | REF | RETURN | SELECT | THEN | TO | UNION | WHEN | WHILE
    ;

macroFragment
    : PERCENT anyName
    | DOT (anyName | BRACKET_ID)
    | anyName
    | BRACKET_ID
    | literal
    | COLON | EQ | NOT_EQUAL | LT | GT | LE | GE | PLUS | MINUS_SIGN | STAR | SLASH | CONCAT
    | macroArguments
    ;

// p => v, p == v (именованный параметр PL/PLUS)
argument
    : (anyName (ARROW | EQEQ))? DISTINCT? (expression | STAR)
    ;

// ::[CLASS]%locate(x [exact] [all] where ...)
locateArgument
    : identifier EXACT? (ALL | COLLECTIONS)? whereClause?
    ;

// ===================================================================== names

// ключевые слова, допустимые в роли обычного идентификатора
identifier
    : ID
    | QUOTED_ID
    | ANY | ARRAY | AS | ASC | BULK | CLOSE | COLLECT | COLLECTIONS | COMMIT | CONNECT
    | CONST | CONSTANT | CONTINUE | CURSOR | DEFAULT | DELETE | DESC | ESCAPE
    | EXACT | EXECUTE | EXISTS | FETCH | FIRST | GROUP | IMMEDIATE | INDEX | INSERT
    | LAST | LIMIT | LOCATE | LOCK | MINUS | NOCOPY | NULLS | OPEN | OTHERS | PRIOR
    | RETURNING | REVERSE | ROLLBACK | SAVEPOINT | SOME | START | SUBTYPE
    | TABLE | TYPE | UPDATE | USING | VAR | VARRAY | VARYING | WITH
    ;

// после `.`, `::`, `%` и в pragma допустимо любое слово
anyName
    : identifier
    | ALL | AND | BEGIN | BETWEEN | BY | CASE | DECLARE | DISTINCT | ELSE | ELSIF
    | END | EXCEPTION | EXIT | FALSE | FOR | FUNCTION | GOTO | HAVING | IF | IN
    | INTERSECT | INTO | IS | LIKE | LOOP | NOT | NULL_ | OF | OR | ORDER | OUT
    | PRAGMA | PROCEDURE | RAISE | REF | RETURN | SELECT | THEN | TO | TRUE
    | UNION | WHEN | WHERE | WHILE
    ;
