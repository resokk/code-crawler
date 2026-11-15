// Captured-source VBScript grammar v1. Unsupported syntax fails with diagnostics.
grammar VBScript;
options { caseInsensitive = true; }

program: separators? block EOF;
block: (statement separators)* statement?;
statement: classDeclaration | procedureDeclaration | ifStatement | forStatement
         | doStatement | whileStatement | selectStatement | withStatement | simpleStatement;
classDeclaration: modifier* CLASS identifier separators block END CLASS;
procedureDeclaration
    : modifier* SUB identifier parameters? separators block END SUB
    | modifier* FUNCTION identifier parameters? separators block END FUNCTION
    | modifier* PROPERTY accessor identifier parameters? separators block END PROPERTY;
modifier: PUBLIC | PRIVATE | DEFAULT;
accessor: GET | LET | SET;
parameters: '(' (parameter (',' parameter)*)? ')';
parameter: (BYVAL | BYREF)? identifier ('(' ')')?;
ifStatement: IF expression THEN (separators block (ELSEIF expression THEN separators block)*
             (ELSE separators block)? END IF | simpleStatement (':' simpleStatement)* (ELSE simpleStatement (':' simpleStatement)*)?);
forStatement: FOR (EACH identifier IN expression | identifier '=' expression TO expression (STEP expression)?)
              separators block NEXT identifier?;
doStatement: DO ((WHILE | UNTIL) expression)? separators block LOOP ((WHILE | UNTIL) expression)?;
whileStatement: WHILE expression separators block WEND;
selectStatement: SELECT CASE expression separators
                 (CASE (ELSE | expression (',' expression)*) separators block)* END SELECT;
withStatement: WITH expression separators block END WITH;
simpleStatement
    : (DIM | PUBLIC | PRIVATE) variable (',' variable)*
    | CONST constant (',' constant)*
    | SET? target '=' expression
    | CALL? target arguments?
    | OPTION EXPLICIT
    | ON ERROR (RESUME NEXT | GOTO NUMBER)
    | EXIT (SUB | FUNCTION | PROPERTY | FOR | DO)
    | REDIM PRESERVE? variable (',' variable)*
    | ERASE identifier (',' identifier)*
    | STOP;
variable: identifier ('(' arguments? ')')?;
constant: identifier '=' expression;
target: '.'? identifier suffix*;
suffix: '.' identifier | '(' arguments? ')';
arguments: expression (',' expression?)* | ',' expression? (',' expression?)*;
expression: unaryExpression (binaryOperator unaryExpression)*;
unaryExpression: (NOT | '+' | '-')* atom suffix*;
atom: STRING | NUMBER | DATE | TRUE | FALSE | NOTHING | EMPTY | NULL | identifier
    | '(' expression ')' | NEW identifier | '.' identifier;
binaryOperator: '^' | '*' | '/' | '\\' | MOD | '+' | '-' | '&' | '=' | '<>' | '<=' | '>=' | '<' | '>'
              | IS | AND | OR | XOR | EQV | IMP;
identifier: IDENTIFIER | GET | LET;
separators: (NEWLINE | ':')+;

CLASS:'CLASS'; END:'END'; SUB:'SUB'; FUNCTION:'FUNCTION'; PROPERTY:'PROPERTY';
GET:'GET'; LET:'LET'; SET:'SET'; PUBLIC:'PUBLIC'; PRIVATE:'PRIVATE'; DEFAULT:'DEFAULT';
BYVAL:'BYVAL'; BYREF:'BYREF'; IF:'IF'; THEN:'THEN'; ELSEIF:'ELSEIF'; ELSE:'ELSE';
FOR:'FOR'; EACH:'EACH'; IN:'IN'; TO:'TO'; STEP:'STEP'; NEXT:'NEXT'; DO:'DO'; LOOP:'LOOP';
WHILE:'WHILE'; UNTIL:'UNTIL'; WEND:'WEND'; SELECT:'SELECT'; CASE:'CASE'; WITH:'WITH';
DIM:'DIM'; CONST:'CONST'; CALL:'CALL'; OPTION:'OPTION'; EXPLICIT:'EXPLICIT';
ON:'ON'; ERROR:'ERROR'; RESUME:'RESUME'; GOTO:'GOTO'; EXIT:'EXIT'; REDIM:'REDIM';
PRESERVE:'PRESERVE'; ERASE:'ERASE'; STOP:'STOP'; NEW:'NEW';
TRUE:'TRUE'; FALSE:'FALSE'; NOTHING:'NOTHING'; EMPTY:'EMPTY'; NULL:'NULL';
NOT:'NOT'; MOD:'MOD'; IS:'IS'; AND:'AND'; OR:'OR'; XOR:'XOR'; EQV:'EQV'; IMP:'IMP';
STRING: '"' ('""' | ~["\r\n])* '"';
DATE: '#' ~[#\r\n]* '#';
NUMBER: '&H' [0-9A-F]+ | '&O' [0-7]+ | [0-9]+ ('.' [0-9]+)? ('E' [+-]? [0-9]+)?;
COMMENT: ('\'' ~[\r\n]* | 'REM' ([ \t] ~[\r\n]*)?) -> skip;
IDENTIFIER: [\p{L}_] [\p{L}\p{N}_]*;
CONTINUATION: [ \t]+ '_' [ \t]* '\r'? '\n' -> skip;

BOM: '\uFEFF' -> skip;
WS: [ \t\f]+ -> skip;
NEWLINE: '\r'? '\n' | '\r';
