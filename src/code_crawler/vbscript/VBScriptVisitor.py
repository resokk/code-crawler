# Generated from VBScript.g4 by ANTLR 4.13.2
from antlr4 import *
if "." in __name__:
    from .VBScriptParser import VBScriptParser
else:
    from VBScriptParser import VBScriptParser

# This class defines a complete generic visitor for a parse tree produced by VBScriptParser.

class VBScriptVisitor(ParseTreeVisitor):

    # Visit a parse tree produced by VBScriptParser#program.
    def visitProgram(self, ctx:VBScriptParser.ProgramContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by VBScriptParser#block.
    def visitBlock(self, ctx:VBScriptParser.BlockContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by VBScriptParser#statement.
    def visitStatement(self, ctx:VBScriptParser.StatementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by VBScriptParser#classDeclaration.
    def visitClassDeclaration(self, ctx:VBScriptParser.ClassDeclarationContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by VBScriptParser#procedureDeclaration.
    def visitProcedureDeclaration(self, ctx:VBScriptParser.ProcedureDeclarationContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by VBScriptParser#modifier.
    def visitModifier(self, ctx:VBScriptParser.ModifierContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by VBScriptParser#accessor.
    def visitAccessor(self, ctx:VBScriptParser.AccessorContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by VBScriptParser#parameters.
    def visitParameters(self, ctx:VBScriptParser.ParametersContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by VBScriptParser#parameter.
    def visitParameter(self, ctx:VBScriptParser.ParameterContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by VBScriptParser#ifStatement.
    def visitIfStatement(self, ctx:VBScriptParser.IfStatementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by VBScriptParser#forStatement.
    def visitForStatement(self, ctx:VBScriptParser.ForStatementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by VBScriptParser#doStatement.
    def visitDoStatement(self, ctx:VBScriptParser.DoStatementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by VBScriptParser#whileStatement.
    def visitWhileStatement(self, ctx:VBScriptParser.WhileStatementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by VBScriptParser#selectStatement.
    def visitSelectStatement(self, ctx:VBScriptParser.SelectStatementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by VBScriptParser#withStatement.
    def visitWithStatement(self, ctx:VBScriptParser.WithStatementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by VBScriptParser#simpleStatement.
    def visitSimpleStatement(self, ctx:VBScriptParser.SimpleStatementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by VBScriptParser#variable.
    def visitVariable(self, ctx:VBScriptParser.VariableContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by VBScriptParser#constant.
    def visitConstant(self, ctx:VBScriptParser.ConstantContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by VBScriptParser#target.
    def visitTarget(self, ctx:VBScriptParser.TargetContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by VBScriptParser#suffix.
    def visitSuffix(self, ctx:VBScriptParser.SuffixContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by VBScriptParser#arguments.
    def visitArguments(self, ctx:VBScriptParser.ArgumentsContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by VBScriptParser#expression.
    def visitExpression(self, ctx:VBScriptParser.ExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by VBScriptParser#unaryExpression.
    def visitUnaryExpression(self, ctx:VBScriptParser.UnaryExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by VBScriptParser#atom.
    def visitAtom(self, ctx:VBScriptParser.AtomContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by VBScriptParser#binaryOperator.
    def visitBinaryOperator(self, ctx:VBScriptParser.BinaryOperatorContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by VBScriptParser#identifier.
    def visitIdentifier(self, ctx:VBScriptParser.IdentifierContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by VBScriptParser#separators.
    def visitSeparators(self, ctx:VBScriptParser.SeparatorsContext):
        return self.visitChildren(ctx)



del VBScriptParser