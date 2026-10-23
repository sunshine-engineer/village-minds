"""Check maintained-source headers and documentation without importing the game.

File: scripts/check_consistency.py
Maintainer: sunshine-engineer
Modified: 2026-10-23
"""

import ast
import re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIRECTORIES = ("village", "scripts", "tests")
REQUIRED_FIELDS = ("File", "Maintainer", "Modified")


def check_python(path):
    """Check one Python module and every nested class/function documentation contract.

    Args:
        path: Maintained Python source path inside the repository.

    Returns:
        Pair of validation error strings and the number of documented definitions.

    Raises:
        SyntaxError: If source is not valid Python.
        OSError: If source cannot be read.
    """
    relative = path.relative_to(ROOT).as_posix()
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative)
    module_doc = ast.get_docstring(tree) or ""
    errors = []
    for field in REQUIRED_FIELDS:
        if not re.search(rf"^{field}: .+", module_doc, re.MULTILINE):
            errors.append(f"{relative}: missing module {field} metadata")
    if f"File: {relative}" not in module_doc:
        errors.append(f"{relative}: incorrect module file name")
    modified = re.search(r"^Modified: (.+)$", module_doc, re.MULTILINE)
    if modified:
        try:
            date.fromisoformat(modified.group(1))
        except ValueError:
            errors.append(f"{relative}: Modified must be an ISO date")
    definitions = 0
    for node in ast.walk(tree):
        if not isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        definitions += 1
        doc = ast.get_docstring(node) or ""
        label = f"{relative}:{node.lineno} {node.name}"
        if not doc.strip():
            errors.append(f"{label}: missing docstring")
            continue
        if isinstance(node, ast.ClassDef):
            continue
        parameters = [
            argument.arg
            for argument in (
                *node.args.posonlyargs,
                *node.args.args,
                *node.args.kwonlyargs,
            )
            if argument.arg not in ("self", "cls")
        ]
        parameters.extend(
            argument.arg
            for argument in (node.args.vararg, node.args.kwarg)
            if argument is not None
        )
        for parameter in parameters:
            if not re.search(rf"^\s+\*{{0,2}}{parameter}:\s+\S", doc, re.MULTILINE):
                errors.append(f"{label}: undocumented parameter {parameter}")
        if not any(section in doc for section in ("Returns:", "Yields:")):
            errors.append(f"{label}: missing return/side-effect contract")
    return errors, definitions


def check_text_headers():
    """Validate metadata in maintained Markdown and comment-capable root/workflow files.

    Returns:
        List of missing or incorrect header-field diagnostics.

    Raises:
        OSError: If a maintained text file cannot be read.
    """
    errors = []
    paths = [
        *ROOT.glob("*.md"),
        *(ROOT / "docs").glob("*.md"),
        *(ROOT / ".github" / "workflows").glob("*.yml"),
        *(ROOT / ".github" / "workflows").glob("*.yaml"),
        *[
            ROOT / name
            for name in (
                ".editorconfig",
                ".env.example",
                ".gitignore",
                "pyproject.toml",
                "compose.yaml",
            )
        ],
    ]
    for path in paths:
        relative = path.relative_to(ROOT).as_posix()
        header = path.read_text(encoding="utf-8").splitlines()[:9]
        fields = {}
        for line in header:
            match = re.match(r"(?:# )?(File|Purpose|Maintainer|Modified): (.+)$", line)
            if match:
                fields[match.group(1)] = match.group(2)
        for field in (*REQUIRED_FIELDS, "Purpose"):
            if field not in fields:
                errors.append(f"{relative}: missing text header {field}")
        if fields.get("File") != relative:
            errors.append(f"{relative}: incorrect text header file name")
        if "Modified" in fields:
            try:
                date.fromisoformat(fields["Modified"])
            except ValueError:
                errors.append(f"{relative}: Modified must be an ISO date")
    return errors


def main():
    """Audit source documentation, print coverage and fail for missing contracts.

    Returns:
        None; exits nonzero when headers or definition documentation are incomplete.

    Raises:
        SystemExit: If any maintained source file fails a consistency check.
    """
    errors = []
    files = definitions = 0
    for directory in SOURCE_DIRECTORIES:
        for path in sorted((ROOT / directory).rglob("*.py")):
            issues, count = check_python(path)
            errors.extend(issues)
            files += 1
            definitions += count
    errors.extend(check_text_headers())
    for error in errors:
        print(error)
    print(f"{files} Python files; {definitions} definitions; {len(errors)} issues")
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
