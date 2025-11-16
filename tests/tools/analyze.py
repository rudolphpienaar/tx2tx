#!/usr/bin/env python3
"""Automated code analysis script"""

import ast
import os
import sys
from pathlib import Path
from typing import List, Dict, Any

class CodeAnalyzer(ast.NodeVisitor):
    def __init__(self, filename):
        self.filename = filename
        self.issues = []
        self.imports_in_functions = []
        self.magic_numbers = []
        self.long_functions = []
        self.missing_docstrings = []
        self.current_function = None
        self.function_lengths = {}

    def visit_FunctionDef(self, node):
        self.current_function = node.name

        # Check for missing docstrings
        if not ast.get_docstring(node):
            self.missing_docstrings.append({
                'function': node.name,
                'line': node.lineno
            })

        # Count lines in function
        if hasattr(node, 'end_lineno'):
            length = node.end_lineno - node.lineno
            if length > 100:
                self.long_functions.append({
                    'function': node.name,
                    'line': node.lineno,
                    'length': length
                })

        self.generic_visit(node)
        self.current_function = None

    def visit_Import(self, node):
        if self.current_function:
            self.imports_in_functions.append({
                'function': self.current_function,
                'line': node.lineno,
                'module': [alias.name for alias in node.names]
            })
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        if self.current_function:
            self.imports_in_functions.append({
                'function': self.current_function,
                'line': node.lineno,
                'module': node.module,
                'names': [alias.name for alias in node.names]
            })
        self.generic_visit(node)

    def visit_Num(self, node):
        # Look for magic numbers (excluding 0, 1, -1)
        if hasattr(node, 'n') and isinstance(node.n, (int, float)):
            if node.n not in [0, 1, -1, 0.0, 1.0]:
                self.magic_numbers.append({
                    'value': node.n,
                    'line': node.lineno
                })
        self.generic_visit(node)

def analyze_file(filepath):
    """Analyze a single Python file"""
    print(f"\n{'='*60}")
    print(f"Analyzing: {filepath}")
    print('='*60)

    with open(filepath, 'r') as f:
        try:
            tree = ast.parse(f.read(), filepath)
        except SyntaxError as e:
            print(f"SYNTAX ERROR: {e}")
            return

    analyzer = CodeAnalyzer(filepath)
    analyzer.visit(tree)

    # Report findings
    issues_found = False

    if analyzer.imports_in_functions:
        issues_found = True
        print(f"\n⚠️  Imports inside functions ({len(analyzer.imports_in_functions)}):")
        for imp in analyzer.imports_in_functions[:5]:
            print(f"  Line {imp['line']}: {imp.get('module', imp.get('module'))} in {imp['function']}()")

    if analyzer.long_functions:
        issues_found = True
        print(f"\n⚠️  Long functions ({len(analyzer.long_functions)}):")
        for func in analyzer.long_functions[:5]:
            print(f"  Line {func['line']}: {func['function']}() - {func['length']} lines")

    if analyzer.magic_numbers:
        issues_found = True
        print(f"\n⚠️  Magic numbers found ({len(analyzer.magic_numbers)}):")
        unique_numbers = {}
        for num in analyzer.magic_numbers:
            val = num['value']
            if val not in unique_numbers:
                unique_numbers[val] = []
            unique_numbers[val].append(num['line'])
        for val, lines in list(unique_numbers.items())[:10]:
            print(f"  {val}: lines {', '.join(map(str, lines[:3]))}")

    if analyzer.missing_docstrings:
        print(f"\n📝 Functions without docstrings ({len(analyzer.missing_docstrings)}):")
        for func in analyzer.missing_docstrings[:5]:
            print(f"  Line {func['line']}: {func['function']}()")

    if not issues_found and not analyzer.missing_docstrings:
        print("\n✅ No major issues found!")

    return analyzer

def main():
    # Analyze key files
    files_to_analyze = [
        'tx2tx/server/main.py',
        'tx2tx/client/main.py',
        'tx2tx/x11/display.py',
        'tx2tx/x11/pointer.py',
        'tx2tx/common/types.py',
    ]

    os.chdir('/data/data/com.termux/files/home/src/tx2tx')

    for filepath in files_to_analyze:
        if Path(filepath).exists():
            analyze_file(filepath)
        else:
            print(f"⚠️  File not found: {filepath}")

if __name__ == '__main__':
    main()
