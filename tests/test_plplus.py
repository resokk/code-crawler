from antlr4 import CommonTokenStream, InputStream

from code_crawler.plplus.PlpLexer import PlpLexer
from code_crawler.plplus.PlpParser import PlpParser


def test_generated_parser_accepts_plplus_source() -> None:
    source = """
        function f(p in number) return number is
          r number;
        begin
          select x(x.[A]) in ::[CLASS] where x.[B] = p into r;
          update x(x.[A] = 1) in ::[CLASS] all where x.[C] = 'q';
          return r;
        end;
    """
    parser = PlpParser(CommonTokenStream(PlpLexer(InputStream(source))))

    tree = parser.compilationUnit()

    assert parser.getNumberOfSyntaxErrors() == 0
    assert "selectStatement" in tree.toStringTree(recog=parser)
