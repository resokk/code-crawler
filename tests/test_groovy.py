from antlr4 import CommonTokenStream, InputStream

from code_crawler.groovy.GroovyLexer import GroovyLexer
from code_crawler.groovy.GroovyParser import GroovyParser


def parse(source: str) -> tuple[int, str]:
    lexer = GroovyLexer(InputStream(source))
    lexer.removeErrorListeners()
    parser = GroovyParser(CommonTokenStream(lexer))
    parser.removeErrorListeners()
    tree = parser.compilationUnit()
    return parser.getNumberOfSyntaxErrors(), tree.toStringTree(recog=parser)


def test_generated_parser_accepts_groovy_source() -> None:
    errors, tree = parse(
        '''
        package a.b

        class Repo {
            static final String TABLE = "users"

            List find(String name, int limit) {
                def q = "select id from ${TABLE} where name = $name"
                def matches = name =~ /ab+c/
                def half = limit / 2
                rows.each { r -> println r.id }
                sql.execute """
                    insert into audit (user_id) values (${half})
                """
                return sql.rows(q.toString(), [
                    1,
                    2
                ])
            }
        }
        '''
    )

    assert errors == 0
    assert tree.count("(methodDeclaration") == 1
    assert tree.count("(gstring ") == 2


def test_broken_source_reports_errors_instead_of_raising() -> None:
    errors, _ = parse("class A { void m( { ) } ]")

    assert errors > 0
