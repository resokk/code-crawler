# Generated from PlpParser.g4 by ANTLR 4.13.2
from antlr4 import *
if "." in __name__:
    from .PlpParser import PlpParser
else:
    from PlpParser import PlpParser

# This class defines a complete generic visitor for a parse tree produced by PlpParser.

class PlpParserVisitor(ParseTreeVisitor):

    # Visit a parse tree produced by PlpParser#compilationUnit.
    def visitCompilationUnit(self, ctx:PlpParser.CompilationUnitContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#unitItem.
    def visitUnitItem(self, ctx:PlpParser.UnitItemContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#declaration.
    def visitDeclaration(self, ctx:PlpParser.DeclarationContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#pragmaStatement.
    def visitPragmaStatement(self, ctx:PlpParser.PragmaStatementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#variableDeclaration.
    def visitVariableDeclaration(self, ctx:PlpParser.VariableDeclarationContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#defaultValue.
    def visitDefaultValue(self, ctx:PlpParser.DefaultValueContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#exceptionDeclaration.
    def visitExceptionDeclaration(self, ctx:PlpParser.ExceptionDeclarationContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#typeDeclaration.
    def visitTypeDeclaration(self, ctx:PlpParser.TypeDeclarationContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#recordType.
    def visitRecordType(self, ctx:PlpParser.RecordTypeContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#tableType.
    def visitTableType(self, ctx:PlpParser.TableTypeContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#varrayType.
    def visitVarrayType(self, ctx:PlpParser.VarrayTypeContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#refCursorType.
    def visitRefCursorType(self, ctx:PlpParser.RefCursorTypeContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#viewType.
    def visitViewType(self, ctx:PlpParser.ViewTypeContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#aliasType.
    def visitAliasType(self, ctx:PlpParser.AliasTypeContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#fieldDeclaration.
    def visitFieldDeclaration(self, ctx:PlpParser.FieldDeclarationContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#subtypeDeclaration.
    def visitSubtypeDeclaration(self, ctx:PlpParser.SubtypeDeclarationContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#cursorDeclaration.
    def visitCursorDeclaration(self, ctx:PlpParser.CursorDeclarationContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#procedureDeclaration.
    def visitProcedureDeclaration(self, ctx:PlpParser.ProcedureDeclarationContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#functionDeclaration.
    def visitFunctionDeclaration(self, ctx:PlpParser.FunctionDeclarationContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#subprogramModifier.
    def visitSubprogramModifier(self, ctx:PlpParser.SubprogramModifierContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#subprogramBody.
    def visitSubprogramBody(self, ctx:PlpParser.SubprogramBodyContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#parameterList.
    def visitParameterList(self, ctx:PlpParser.ParameterListContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#parameter.
    def visitParameter(self, ctx:PlpParser.ParameterContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#typeSpec.
    def visitTypeSpec(self, ctx:PlpParser.TypeSpecContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#typeName.
    def visitTypeName(self, ctx:PlpParser.TypeNameContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#body.
    def visitBody(self, ctx:PlpParser.BodyContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#exceptionSection.
    def visitExceptionSection(self, ctx:PlpParser.ExceptionSectionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#exceptionHandler.
    def visitExceptionHandler(self, ctx:PlpParser.ExceptionHandlerContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#exceptionName.
    def visitExceptionName(self, ctx:PlpParser.ExceptionNameContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#statements.
    def visitStatements(self, ctx:PlpParser.StatementsContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#statement.
    def visitStatement(self, ctx:PlpParser.StatementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#label.
    def visitLabel(self, ctx:PlpParser.LabelContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#simpleStatement.
    def visitSimpleStatement(self, ctx:PlpParser.SimpleStatementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#block.
    def visitBlock(self, ctx:PlpParser.BlockContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#varStatement.
    def visitVarStatement(self, ctx:PlpParser.VarStatementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#macroStatement.
    def visitMacroStatement(self, ctx:PlpParser.MacroStatementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#assignmentOrCall.
    def visitAssignmentOrCall(self, ctx:PlpParser.AssignmentOrCallContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#ifStatement.
    def visitIfStatement(self, ctx:PlpParser.IfStatementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#loopStatement.
    def visitLoopStatement(self, ctx:PlpParser.LoopStatementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#numericFor.
    def visitNumericFor(self, ctx:PlpParser.NumericForContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#objectFor.
    def visitObjectFor(self, ctx:PlpParser.ObjectForContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#queryFor.
    def visitQueryFor(self, ctx:PlpParser.QueryForContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#sqlCaseStatement.
    def visitSqlCaseStatement(self, ctx:PlpParser.SqlCaseStatementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#plpCaseStatement.
    def visitPlpCaseStatement(self, ctx:PlpParser.PlpCaseStatementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#caseBranch.
    def visitCaseBranch(self, ctx:PlpParser.CaseBranchContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#nullStatement.
    def visitNullStatement(self, ctx:PlpParser.NullStatementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#exitStatement.
    def visitExitStatement(self, ctx:PlpParser.ExitStatementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#continueStatement.
    def visitContinueStatement(self, ctx:PlpParser.ContinueStatementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#returnStatement.
    def visitReturnStatement(self, ctx:PlpParser.ReturnStatementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#gotoStatement.
    def visitGotoStatement(self, ctx:PlpParser.GotoStatementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#raiseStatement.
    def visitRaiseStatement(self, ctx:PlpParser.RaiseStatementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#openStatement.
    def visitOpenStatement(self, ctx:PlpParser.OpenStatementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#fetchStatement.
    def visitFetchStatement(self, ctx:PlpParser.FetchStatementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#closeStatement.
    def visitCloseStatement(self, ctx:PlpParser.CloseStatementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#transactionStatement.
    def visitTransactionStatement(self, ctx:PlpParser.TransactionStatementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#executeImmediateStatement.
    def visitExecuteImmediateStatement(self, ctx:PlpParser.ExecuteImmediateStatementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#locateStatement.
    def visitLocateStatement(self, ctx:PlpParser.LocateStatementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#selectStatement.
    def visitSelectStatement(self, ctx:PlpParser.SelectStatementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#lockClause.
    def visitLockClause(self, ctx:PlpParser.LockClauseContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#intoClause.
    def visitIntoClause(self, ctx:PlpParser.IntoClauseContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#returningClause.
    def visitReturningClause(self, ctx:PlpParser.ReturningClauseContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#updateStatement.
    def visitUpdateStatement(self, ctx:PlpParser.UpdateStatementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#deleteStatement.
    def visitDeleteStatement(self, ctx:PlpParser.DeleteStatementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#insertStatement.
    def visitInsertStatement(self, ctx:PlpParser.InsertStatementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#setItem.
    def visitSetItem(self, ctx:PlpParser.SetItemContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#selectQuery.
    def visitSelectQuery(self, ctx:PlpParser.SelectQueryContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#selectItem.
    def visitSelectItem(self, ctx:PlpParser.SelectItemContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#setOperator.
    def visitSetOperator(self, ctx:PlpParser.SetOperatorContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#querySource.
    def visitQuerySource(self, ctx:PlpParser.QuerySourceContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#sourceItem.
    def visitSourceItem(self, ctx:PlpParser.SourceItemContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#whereClause.
    def visitWhereClause(self, ctx:PlpParser.WhereClauseContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#hierarchicalClause.
    def visitHierarchicalClause(self, ctx:PlpParser.HierarchicalClauseContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#groupByClause.
    def visitGroupByClause(self, ctx:PlpParser.GroupByClauseContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#havingClause.
    def visitHavingClause(self, ctx:PlpParser.HavingClauseContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#orderByClause.
    def visitOrderByClause(self, ctx:PlpParser.OrderByClauseContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#orderItem.
    def visitOrderItem(self, ctx:PlpParser.OrderItemContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#orExpression.
    def visitOrExpression(self, ctx:PlpParser.OrExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#conditionExpression.
    def visitConditionExpression(self, ctx:PlpParser.ConditionExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#andExpression.
    def visitAndExpression(self, ctx:PlpParser.AndExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#notExpression.
    def visitNotExpression(self, ctx:PlpParser.NotExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#condition.
    def visitCondition(self, ctx:PlpParser.ConditionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#comparisonCondition.
    def visitComparisonCondition(self, ctx:PlpParser.ComparisonConditionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#isNullCondition.
    def visitIsNullCondition(self, ctx:PlpParser.IsNullConditionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#likeCondition.
    def visitLikeCondition(self, ctx:PlpParser.LikeConditionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#betweenCondition.
    def visitBetweenCondition(self, ctx:PlpParser.BetweenConditionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#inCondition.
    def visitInCondition(self, ctx:PlpParser.InConditionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#inMacroCondition.
    def visitInMacroCondition(self, ctx:PlpParser.InMacroConditionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#primaryExpression.
    def visitPrimaryExpression(self, ctx:PlpParser.PrimaryExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#powerExpression.
    def visitPowerExpression(self, ctx:PlpParser.PowerExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#additiveExpression.
    def visitAdditiveExpression(self, ctx:PlpParser.AdditiveExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#multiplicativeExpression.
    def visitMultiplicativeExpression(self, ctx:PlpParser.MultiplicativeExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#unaryExpression.
    def visitUnaryExpression(self, ctx:PlpParser.UnaryExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#primary.
    def visitPrimary(self, ctx:PlpParser.PrimaryContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#caseExpression.
    def visitCaseExpression(self, ctx:PlpParser.CaseExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#literal.
    def visitLiteral(self, ctx:PlpParser.LiteralContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#nameChain.
    def visitNameChain(self, ctx:PlpParser.NameChainContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#namePrefix.
    def visitNamePrefix(self, ctx:PlpParser.NamePrefixContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#nameSuffix.
    def visitNameSuffix(self, ctx:PlpParser.NameSuffixContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#nameSuffixNoCall.
    def visitNameSuffixNoCall(self, ctx:PlpParser.NameSuffixNoCallContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#reference.
    def visitReference(self, ctx:PlpParser.ReferenceContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#macroChain.
    def visitMacroChain(self, ctx:PlpParser.MacroChainContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#macroSuffix.
    def visitMacroSuffix(self, ctx:PlpParser.MacroSuffixContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#macroSuffixNoCall.
    def visitMacroSuffixNoCall(self, ctx:PlpParser.MacroSuffixNoCallContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#macroArguments.
    def visitMacroArguments(self, ctx:PlpParser.MacroArgumentsContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#macroArgument.
    def visitMacroArgument(self, ctx:PlpParser.MacroArgumentContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#macroLooseStart.
    def visitMacroLooseStart(self, ctx:PlpParser.MacroLooseStartContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#macroTailStart.
    def visitMacroTailStart(self, ctx:PlpParser.MacroTailStartContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#macroKeyword.
    def visitMacroKeyword(self, ctx:PlpParser.MacroKeywordContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#macroFragment.
    def visitMacroFragment(self, ctx:PlpParser.MacroFragmentContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#argument.
    def visitArgument(self, ctx:PlpParser.ArgumentContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#locateArgument.
    def visitLocateArgument(self, ctx:PlpParser.LocateArgumentContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#identifier.
    def visitIdentifier(self, ctx:PlpParser.IdentifierContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by PlpParser#anyName.
    def visitAnyName(self, ctx:PlpParser.AnyNameContext):
        return self.visitChildren(ctx)



del PlpParser