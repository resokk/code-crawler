# Generated from GroovyParser.g4 by ANTLR 4.13.2
from antlr4 import *
if "." in __name__:
    from .GroovyParser import GroovyParser
else:
    from GroovyParser import GroovyParser

# This class defines a complete generic visitor for a parse tree produced by GroovyParser.

class GroovyParserVisitor(ParseTreeVisitor):

    # Visit a parse tree produced by GroovyParser#compilationUnit.
    def visitCompilationUnit(self, ctx:GroovyParser.CompilationUnitContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#scriptStatements.
    def visitScriptStatements(self, ctx:GroovyParser.ScriptStatementsContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#scriptStatement.
    def visitScriptStatement(self, ctx:GroovyParser.ScriptStatementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#packageDeclaration.
    def visitPackageDeclaration(self, ctx:GroovyParser.PackageDeclarationContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#importDeclaration.
    def visitImportDeclaration(self, ctx:GroovyParser.ImportDeclarationContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#typeDeclaration.
    def visitTypeDeclaration(self, ctx:GroovyParser.TypeDeclarationContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#modifier.
    def visitModifier(self, ctx:GroovyParser.ModifierContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#modifiersOpt.
    def visitModifiersOpt(self, ctx:GroovyParser.ModifiersOptContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#modifiers.
    def visitModifiers(self, ctx:GroovyParser.ModifiersContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#classOrInterfaceModifiersOpt.
    def visitClassOrInterfaceModifiersOpt(self, ctx:GroovyParser.ClassOrInterfaceModifiersOptContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#classOrInterfaceModifiers.
    def visitClassOrInterfaceModifiers(self, ctx:GroovyParser.ClassOrInterfaceModifiersContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#classOrInterfaceModifier.
    def visitClassOrInterfaceModifier(self, ctx:GroovyParser.ClassOrInterfaceModifierContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#variableModifier.
    def visitVariableModifier(self, ctx:GroovyParser.VariableModifierContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#variableModifiersOpt.
    def visitVariableModifiersOpt(self, ctx:GroovyParser.VariableModifiersOptContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#variableModifiers.
    def visitVariableModifiers(self, ctx:GroovyParser.VariableModifiersContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#typeParameters.
    def visitTypeParameters(self, ctx:GroovyParser.TypeParametersContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#typeParameter.
    def visitTypeParameter(self, ctx:GroovyParser.TypeParameterContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#typeBound.
    def visitTypeBound(self, ctx:GroovyParser.TypeBoundContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#typeList.
    def visitTypeList(self, ctx:GroovyParser.TypeListContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#classDeclaration.
    def visitClassDeclaration(self, ctx:GroovyParser.ClassDeclarationContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#classBody.
    def visitClassBody(self, ctx:GroovyParser.ClassBodyContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#enumConstants.
    def visitEnumConstants(self, ctx:GroovyParser.EnumConstantsContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#enumConstant.
    def visitEnumConstant(self, ctx:GroovyParser.EnumConstantContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#classBodyDeclaration.
    def visitClassBodyDeclaration(self, ctx:GroovyParser.ClassBodyDeclarationContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#memberDeclaration.
    def visitMemberDeclaration(self, ctx:GroovyParser.MemberDeclarationContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#methodDeclaration.
    def visitMethodDeclaration(self, ctx:GroovyParser.MethodDeclarationContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#compactConstructorDeclaration.
    def visitCompactConstructorDeclaration(self, ctx:GroovyParser.CompactConstructorDeclarationContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#methodName.
    def visitMethodName(self, ctx:GroovyParser.MethodNameContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#returnType.
    def visitReturnType(self, ctx:GroovyParser.ReturnTypeContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#fieldDeclaration.
    def visitFieldDeclaration(self, ctx:GroovyParser.FieldDeclarationContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#variableDeclarators.
    def visitVariableDeclarators(self, ctx:GroovyParser.VariableDeclaratorsContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#variableDeclarator.
    def visitVariableDeclarator(self, ctx:GroovyParser.VariableDeclaratorContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#variableDeclaratorId.
    def visitVariableDeclaratorId(self, ctx:GroovyParser.VariableDeclaratorIdContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#variableInitializer.
    def visitVariableInitializer(self, ctx:GroovyParser.VariableInitializerContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#variableInitializers.
    def visitVariableInitializers(self, ctx:GroovyParser.VariableInitializersContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#emptyDims.
    def visitEmptyDims(self, ctx:GroovyParser.EmptyDimsContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#emptyDimsOpt.
    def visitEmptyDimsOpt(self, ctx:GroovyParser.EmptyDimsOptContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#standardType.
    def visitStandardType(self, ctx:GroovyParser.StandardTypeContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#type.
    def visitType(self, ctx:GroovyParser.TypeContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#classOrInterfaceType.
    def visitClassOrInterfaceType(self, ctx:GroovyParser.ClassOrInterfaceTypeContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#generalClassOrInterfaceType.
    def visitGeneralClassOrInterfaceType(self, ctx:GroovyParser.GeneralClassOrInterfaceTypeContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#standardClassOrInterfaceType.
    def visitStandardClassOrInterfaceType(self, ctx:GroovyParser.StandardClassOrInterfaceTypeContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#primitiveType.
    def visitPrimitiveType(self, ctx:GroovyParser.PrimitiveTypeContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#typeArguments.
    def visitTypeArguments(self, ctx:GroovyParser.TypeArgumentsContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#typeArgument.
    def visitTypeArgument(self, ctx:GroovyParser.TypeArgumentContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#annotatedQualifiedClassName.
    def visitAnnotatedQualifiedClassName(self, ctx:GroovyParser.AnnotatedQualifiedClassNameContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#qualifiedClassNameList.
    def visitQualifiedClassNameList(self, ctx:GroovyParser.QualifiedClassNameListContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#formalParameters.
    def visitFormalParameters(self, ctx:GroovyParser.FormalParametersContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#formalParameterList.
    def visitFormalParameterList(self, ctx:GroovyParser.FormalParameterListContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#thisFormalParameter.
    def visitThisFormalParameter(self, ctx:GroovyParser.ThisFormalParameterContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#formalParameter.
    def visitFormalParameter(self, ctx:GroovyParser.FormalParameterContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#methodBody.
    def visitMethodBody(self, ctx:GroovyParser.MethodBodyContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#qualifiedName.
    def visitQualifiedName(self, ctx:GroovyParser.QualifiedNameContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#qualifiedNameElement.
    def visitQualifiedNameElement(self, ctx:GroovyParser.QualifiedNameElementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#qualifiedNameElements.
    def visitQualifiedNameElements(self, ctx:GroovyParser.QualifiedNameElementsContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#qualifiedClassName.
    def visitQualifiedClassName(self, ctx:GroovyParser.QualifiedClassNameContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#qualifiedStandardClassName.
    def visitQualifiedStandardClassName(self, ctx:GroovyParser.QualifiedStandardClassNameContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#integerLiteralAlt.
    def visitIntegerLiteralAlt(self, ctx:GroovyParser.IntegerLiteralAltContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#floatingPointLiteralAlt.
    def visitFloatingPointLiteralAlt(self, ctx:GroovyParser.FloatingPointLiteralAltContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#stringLiteralAlt.
    def visitStringLiteralAlt(self, ctx:GroovyParser.StringLiteralAltContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#booleanLiteralAlt.
    def visitBooleanLiteralAlt(self, ctx:GroovyParser.BooleanLiteralAltContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#nullLiteralAlt.
    def visitNullLiteralAlt(self, ctx:GroovyParser.NullLiteralAltContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#gstring.
    def visitGstring(self, ctx:GroovyParser.GstringContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#gstringValue.
    def visitGstringValue(self, ctx:GroovyParser.GstringValueContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#gstringPath.
    def visitGstringPath(self, ctx:GroovyParser.GstringPathContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#lambdaExpression.
    def visitLambdaExpression(self, ctx:GroovyParser.LambdaExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#standardLambdaExpression.
    def visitStandardLambdaExpression(self, ctx:GroovyParser.StandardLambdaExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#lambdaParameters.
    def visitLambdaParameters(self, ctx:GroovyParser.LambdaParametersContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#standardLambdaParameters.
    def visitStandardLambdaParameters(self, ctx:GroovyParser.StandardLambdaParametersContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#lambdaBody.
    def visitLambdaBody(self, ctx:GroovyParser.LambdaBodyContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#closure.
    def visitClosure(self, ctx:GroovyParser.ClosureContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#closureOrLambdaExpression.
    def visitClosureOrLambdaExpression(self, ctx:GroovyParser.ClosureOrLambdaExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#blockStatementsOpt.
    def visitBlockStatementsOpt(self, ctx:GroovyParser.BlockStatementsOptContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#blockStatements.
    def visitBlockStatements(self, ctx:GroovyParser.BlockStatementsContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#annotationsOpt.
    def visitAnnotationsOpt(self, ctx:GroovyParser.AnnotationsOptContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#annotation.
    def visitAnnotation(self, ctx:GroovyParser.AnnotationContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#elementValues.
    def visitElementValues(self, ctx:GroovyParser.ElementValuesContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#annotationName.
    def visitAnnotationName(self, ctx:GroovyParser.AnnotationNameContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#elementValuePairs.
    def visitElementValuePairs(self, ctx:GroovyParser.ElementValuePairsContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#elementValuePair.
    def visitElementValuePair(self, ctx:GroovyParser.ElementValuePairContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#elementValuePairName.
    def visitElementValuePairName(self, ctx:GroovyParser.ElementValuePairNameContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#elementValue.
    def visitElementValue(self, ctx:GroovyParser.ElementValueContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#elementValueArrayInitializer.
    def visitElementValueArrayInitializer(self, ctx:GroovyParser.ElementValueArrayInitializerContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#block.
    def visitBlock(self, ctx:GroovyParser.BlockContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#blockStatement.
    def visitBlockStatement(self, ctx:GroovyParser.BlockStatementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#localVariableDeclaration.
    def visitLocalVariableDeclaration(self, ctx:GroovyParser.LocalVariableDeclarationContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#variableDeclaration.
    def visitVariableDeclaration(self, ctx:GroovyParser.VariableDeclarationContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#typeNamePairs.
    def visitTypeNamePairs(self, ctx:GroovyParser.TypeNamePairsContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#typeNamePair.
    def visitTypeNamePair(self, ctx:GroovyParser.TypeNamePairContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#variableNames.
    def visitVariableNames(self, ctx:GroovyParser.VariableNamesContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#conditionalStatement.
    def visitConditionalStatement(self, ctx:GroovyParser.ConditionalStatementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#ifElseStatement.
    def visitIfElseStatement(self, ctx:GroovyParser.IfElseStatementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#switchStatement.
    def visitSwitchStatement(self, ctx:GroovyParser.SwitchStatementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#forStmtAlt.
    def visitForStmtAlt(self, ctx:GroovyParser.ForStmtAltContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#whileStmtAlt.
    def visitWhileStmtAlt(self, ctx:GroovyParser.WhileStmtAltContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#doWhileStmtAlt.
    def visitDoWhileStmtAlt(self, ctx:GroovyParser.DoWhileStmtAltContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#continueStatement.
    def visitContinueStatement(self, ctx:GroovyParser.ContinueStatementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#breakStatement.
    def visitBreakStatement(self, ctx:GroovyParser.BreakStatementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#yieldStatement.
    def visitYieldStatement(self, ctx:GroovyParser.YieldStatementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#tryCatchStatement.
    def visitTryCatchStatement(self, ctx:GroovyParser.TryCatchStatementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#assertStatement.
    def visitAssertStatement(self, ctx:GroovyParser.AssertStatementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#blockStmtAlt.
    def visitBlockStmtAlt(self, ctx:GroovyParser.BlockStmtAltContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#conditionalStmtAlt.
    def visitConditionalStmtAlt(self, ctx:GroovyParser.ConditionalStmtAltContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#loopStmtAlt.
    def visitLoopStmtAlt(self, ctx:GroovyParser.LoopStmtAltContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#tryCatchStmtAlt.
    def visitTryCatchStmtAlt(self, ctx:GroovyParser.TryCatchStmtAltContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#synchronizedStmtAlt.
    def visitSynchronizedStmtAlt(self, ctx:GroovyParser.SynchronizedStmtAltContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#returnStmtAlt.
    def visitReturnStmtAlt(self, ctx:GroovyParser.ReturnStmtAltContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#throwStmtAlt.
    def visitThrowStmtAlt(self, ctx:GroovyParser.ThrowStmtAltContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#breakStmtAlt.
    def visitBreakStmtAlt(self, ctx:GroovyParser.BreakStmtAltContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#continueStmtAlt.
    def visitContinueStmtAlt(self, ctx:GroovyParser.ContinueStmtAltContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#yieldStmtAlt.
    def visitYieldStmtAlt(self, ctx:GroovyParser.YieldStmtAltContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#labeledStmtAlt.
    def visitLabeledStmtAlt(self, ctx:GroovyParser.LabeledStmtAltContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#assertStmtAlt.
    def visitAssertStmtAlt(self, ctx:GroovyParser.AssertStmtAltContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#localVariableDeclarationStmtAlt.
    def visitLocalVariableDeclarationStmtAlt(self, ctx:GroovyParser.LocalVariableDeclarationStmtAltContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#expressionStmtAlt.
    def visitExpressionStmtAlt(self, ctx:GroovyParser.ExpressionStmtAltContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#emptyStmtAlt.
    def visitEmptyStmtAlt(self, ctx:GroovyParser.EmptyStmtAltContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#catchClause.
    def visitCatchClause(self, ctx:GroovyParser.CatchClauseContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#catchType.
    def visitCatchType(self, ctx:GroovyParser.CatchTypeContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#finallyBlock.
    def visitFinallyBlock(self, ctx:GroovyParser.FinallyBlockContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#resources.
    def visitResources(self, ctx:GroovyParser.ResourcesContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#resourceList.
    def visitResourceList(self, ctx:GroovyParser.ResourceListContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#resource.
    def visitResource(self, ctx:GroovyParser.ResourceContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#switchBlockStatementGroup.
    def visitSwitchBlockStatementGroup(self, ctx:GroovyParser.SwitchBlockStatementGroupContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#switchLabel.
    def visitSwitchLabel(self, ctx:GroovyParser.SwitchLabelContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#forControl.
    def visitForControl(self, ctx:GroovyParser.ForControlContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#enhancedForControl.
    def visitEnhancedForControl(self, ctx:GroovyParser.EnhancedForControlContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#classicalForControl.
    def visitClassicalForControl(self, ctx:GroovyParser.ClassicalForControlContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#forInit.
    def visitForInit(self, ctx:GroovyParser.ForInitContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#forUpdate.
    def visitForUpdate(self, ctx:GroovyParser.ForUpdateContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#castParExpression.
    def visitCastParExpression(self, ctx:GroovyParser.CastParExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#parExpression.
    def visitParExpression(self, ctx:GroovyParser.ParExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#expressionInPar.
    def visitExpressionInPar(self, ctx:GroovyParser.ExpressionInParContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#expressionList.
    def visitExpressionList(self, ctx:GroovyParser.ExpressionListContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#expressionListElement.
    def visitExpressionListElement(self, ctx:GroovyParser.ExpressionListElementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#enhancedStatementExpression.
    def visitEnhancedStatementExpression(self, ctx:GroovyParser.EnhancedStatementExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#commandExprAlt.
    def visitCommandExprAlt(self, ctx:GroovyParser.CommandExprAltContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#postfixExpression.
    def visitPostfixExpression(self, ctx:GroovyParser.PostfixExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#switchExpression.
    def visitSwitchExpression(self, ctx:GroovyParser.SwitchExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#switchBlockStatementExpressionGroup.
    def visitSwitchBlockStatementExpressionGroup(self, ctx:GroovyParser.SwitchBlockStatementExpressionGroupContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#switchExpressionLabel.
    def visitSwitchExpressionLabel(self, ctx:GroovyParser.SwitchExpressionLabelContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#postfixExprAlt.
    def visitPostfixExprAlt(self, ctx:GroovyParser.PostfixExprAltContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#unaryNotExprAlt.
    def visitUnaryNotExprAlt(self, ctx:GroovyParser.UnaryNotExprAltContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#shiftExprAlt.
    def visitShiftExprAlt(self, ctx:GroovyParser.ShiftExprAltContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#castExprAlt.
    def visitCastExprAlt(self, ctx:GroovyParser.CastExprAltContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#switchExprAlt.
    def visitSwitchExprAlt(self, ctx:GroovyParser.SwitchExprAltContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#multipleAssignmentExprAlt.
    def visitMultipleAssignmentExprAlt(self, ctx:GroovyParser.MultipleAssignmentExprAltContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#exclusiveOrExprAlt.
    def visitExclusiveOrExprAlt(self, ctx:GroovyParser.ExclusiveOrExprAltContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#additiveExprAlt.
    def visitAdditiveExprAlt(self, ctx:GroovyParser.AdditiveExprAltContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#regexExprAlt.
    def visitRegexExprAlt(self, ctx:GroovyParser.RegexExprAltContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#conditionalExprAlt.
    def visitConditionalExprAlt(self, ctx:GroovyParser.ConditionalExprAltContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#powerExprAlt.
    def visitPowerExprAlt(self, ctx:GroovyParser.PowerExprAltContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#relationalExprAlt.
    def visitRelationalExprAlt(self, ctx:GroovyParser.RelationalExprAltContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#logicalAndExprAlt.
    def visitLogicalAndExprAlt(self, ctx:GroovyParser.LogicalAndExprAltContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#assignmentExprAlt.
    def visitAssignmentExprAlt(self, ctx:GroovyParser.AssignmentExprAltContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#unaryAddExprAlt.
    def visitUnaryAddExprAlt(self, ctx:GroovyParser.UnaryAddExprAltContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#multiplicativeExprAlt.
    def visitMultiplicativeExprAlt(self, ctx:GroovyParser.MultiplicativeExprAltContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#inclusiveOrExprAlt.
    def visitInclusiveOrExprAlt(self, ctx:GroovyParser.InclusiveOrExprAltContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#logicalOrExprAlt.
    def visitLogicalOrExprAlt(self, ctx:GroovyParser.LogicalOrExprAltContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#equalityExprAlt.
    def visitEqualityExprAlt(self, ctx:GroovyParser.EqualityExprAltContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#andExprAlt.
    def visitAndExprAlt(self, ctx:GroovyParser.AndExprAltContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#castExprAltOfCastOperandExpression.
    def visitCastExprAltOfCastOperandExpression(self, ctx:GroovyParser.CastExprAltOfCastOperandExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#postfixExprAltOfCastOperandExpression.
    def visitPostfixExprAltOfCastOperandExpression(self, ctx:GroovyParser.PostfixExprAltOfCastOperandExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#unaryNotExprAltOfCastOperandExpression.
    def visitUnaryNotExprAltOfCastOperandExpression(self, ctx:GroovyParser.UnaryNotExprAltOfCastOperandExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#unaryAddExprAltOfCastOperandExpression.
    def visitUnaryAddExprAltOfCastOperandExpression(self, ctx:GroovyParser.UnaryAddExprAltOfCastOperandExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#commandExpression.
    def visitCommandExpression(self, ctx:GroovyParser.CommandExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#commandArgument.
    def visitCommandArgument(self, ctx:GroovyParser.CommandArgumentContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#pathExpression.
    def visitPathExpression(self, ctx:GroovyParser.PathExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#pathElement.
    def visitPathElement(self, ctx:GroovyParser.PathElementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#namePart.
    def visitNamePart(self, ctx:GroovyParser.NamePartContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#dynamicMemberName.
    def visitDynamicMemberName(self, ctx:GroovyParser.DynamicMemberNameContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#indexPropertyArgs.
    def visitIndexPropertyArgs(self, ctx:GroovyParser.IndexPropertyArgsContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#namedPropertyArgs.
    def visitNamedPropertyArgs(self, ctx:GroovyParser.NamedPropertyArgsContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#identifierPrmrAlt.
    def visitIdentifierPrmrAlt(self, ctx:GroovyParser.IdentifierPrmrAltContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#literalPrmrAlt.
    def visitLiteralPrmrAlt(self, ctx:GroovyParser.LiteralPrmrAltContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#gstringPrmrAlt.
    def visitGstringPrmrAlt(self, ctx:GroovyParser.GstringPrmrAltContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#newPrmrAlt.
    def visitNewPrmrAlt(self, ctx:GroovyParser.NewPrmrAltContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#thisPrmrAlt.
    def visitThisPrmrAlt(self, ctx:GroovyParser.ThisPrmrAltContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#superPrmrAlt.
    def visitSuperPrmrAlt(self, ctx:GroovyParser.SuperPrmrAltContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#parenPrmrAlt.
    def visitParenPrmrAlt(self, ctx:GroovyParser.ParenPrmrAltContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#closureOrLambdaExpressionPrmrAlt.
    def visitClosureOrLambdaExpressionPrmrAlt(self, ctx:GroovyParser.ClosureOrLambdaExpressionPrmrAltContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#listPrmrAlt.
    def visitListPrmrAlt(self, ctx:GroovyParser.ListPrmrAltContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#mapPrmrAlt.
    def visitMapPrmrAlt(self, ctx:GroovyParser.MapPrmrAltContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#builtInTypePrmrAlt.
    def visitBuiltInTypePrmrAlt(self, ctx:GroovyParser.BuiltInTypePrmrAltContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#identifierPrmrAltOfNamedPropertyArgPrimary.
    def visitIdentifierPrmrAltOfNamedPropertyArgPrimary(self, ctx:GroovyParser.IdentifierPrmrAltOfNamedPropertyArgPrimaryContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#literalPrmrAltOfNamedPropertyArgPrimary.
    def visitLiteralPrmrAltOfNamedPropertyArgPrimary(self, ctx:GroovyParser.LiteralPrmrAltOfNamedPropertyArgPrimaryContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#gstringPrmrAltOfNamedPropertyArgPrimary.
    def visitGstringPrmrAltOfNamedPropertyArgPrimary(self, ctx:GroovyParser.GstringPrmrAltOfNamedPropertyArgPrimaryContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#parenPrmrAltOfNamedPropertyArgPrimary.
    def visitParenPrmrAltOfNamedPropertyArgPrimary(self, ctx:GroovyParser.ParenPrmrAltOfNamedPropertyArgPrimaryContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#listPrmrAltOfNamedPropertyArgPrimary.
    def visitListPrmrAltOfNamedPropertyArgPrimary(self, ctx:GroovyParser.ListPrmrAltOfNamedPropertyArgPrimaryContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#mapPrmrAltOfNamedPropertyArgPrimary.
    def visitMapPrmrAltOfNamedPropertyArgPrimary(self, ctx:GroovyParser.MapPrmrAltOfNamedPropertyArgPrimaryContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#identifierPrmrAltOfNamedArgPrimary.
    def visitIdentifierPrmrAltOfNamedArgPrimary(self, ctx:GroovyParser.IdentifierPrmrAltOfNamedArgPrimaryContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#literalPrmrAltOfNamedArgPrimary.
    def visitLiteralPrmrAltOfNamedArgPrimary(self, ctx:GroovyParser.LiteralPrmrAltOfNamedArgPrimaryContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#gstringPrmrAltOfNamedArgPrimary.
    def visitGstringPrmrAltOfNamedArgPrimary(self, ctx:GroovyParser.GstringPrmrAltOfNamedArgPrimaryContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#identifierPrmrAltOfCommandPrimary.
    def visitIdentifierPrmrAltOfCommandPrimary(self, ctx:GroovyParser.IdentifierPrmrAltOfCommandPrimaryContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#literalPrmrAltOfCommandPrimary.
    def visitLiteralPrmrAltOfCommandPrimary(self, ctx:GroovyParser.LiteralPrmrAltOfCommandPrimaryContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#gstringPrmrAltOfCommandPrimary.
    def visitGstringPrmrAltOfCommandPrimary(self, ctx:GroovyParser.GstringPrmrAltOfCommandPrimaryContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#list.
    def visitList(self, ctx:GroovyParser.ListContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#map.
    def visitMap(self, ctx:GroovyParser.MapContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#mapEntryList.
    def visitMapEntryList(self, ctx:GroovyParser.MapEntryListContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#namedPropertyArgList.
    def visitNamedPropertyArgList(self, ctx:GroovyParser.NamedPropertyArgListContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#mapEntry.
    def visitMapEntry(self, ctx:GroovyParser.MapEntryContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#namedPropertyArg.
    def visitNamedPropertyArg(self, ctx:GroovyParser.NamedPropertyArgContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#namedArg.
    def visitNamedArg(self, ctx:GroovyParser.NamedArgContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#mapEntryLabel.
    def visitMapEntryLabel(self, ctx:GroovyParser.MapEntryLabelContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#namedPropertyArgLabel.
    def visitNamedPropertyArgLabel(self, ctx:GroovyParser.NamedPropertyArgLabelContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#namedArgLabel.
    def visitNamedArgLabel(self, ctx:GroovyParser.NamedArgLabelContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#creator.
    def visitCreator(self, ctx:GroovyParser.CreatorContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#dim.
    def visitDim(self, ctx:GroovyParser.DimContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#arrayInitializer.
    def visitArrayInitializer(self, ctx:GroovyParser.ArrayInitializerContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#anonymousInnerClassDeclaration.
    def visitAnonymousInnerClassDeclaration(self, ctx:GroovyParser.AnonymousInnerClassDeclarationContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#createdName.
    def visitCreatedName(self, ctx:GroovyParser.CreatedNameContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#nonWildcardTypeArguments.
    def visitNonWildcardTypeArguments(self, ctx:GroovyParser.NonWildcardTypeArgumentsContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#typeArgumentsOrDiamond.
    def visitTypeArgumentsOrDiamond(self, ctx:GroovyParser.TypeArgumentsOrDiamondContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#arguments.
    def visitArguments(self, ctx:GroovyParser.ArgumentsContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#argumentList.
    def visitArgumentList(self, ctx:GroovyParser.ArgumentListContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#enhancedArgumentListInPar.
    def visitEnhancedArgumentListInPar(self, ctx:GroovyParser.EnhancedArgumentListInParContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#firstArgumentListElement.
    def visitFirstArgumentListElement(self, ctx:GroovyParser.FirstArgumentListElementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#argumentListElement.
    def visitArgumentListElement(self, ctx:GroovyParser.ArgumentListElementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#enhancedArgumentListElement.
    def visitEnhancedArgumentListElement(self, ctx:GroovyParser.EnhancedArgumentListElementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#stringLiteral.
    def visitStringLiteral(self, ctx:GroovyParser.StringLiteralContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#className.
    def visitClassName(self, ctx:GroovyParser.ClassNameContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#identifier.
    def visitIdentifier(self, ctx:GroovyParser.IdentifierContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#builtInType.
    def visitBuiltInType(self, ctx:GroovyParser.BuiltInTypeContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#keywords.
    def visitKeywords(self, ctx:GroovyParser.KeywordsContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#rparen.
    def visitRparen(self, ctx:GroovyParser.RparenContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#nls.
    def visitNls(self, ctx:GroovyParser.NlsContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by GroovyParser#sep.
    def visitSep(self, ctx:GroovyParser.SepContext):
        return self.visitChildren(ctx)



del GroovyParser