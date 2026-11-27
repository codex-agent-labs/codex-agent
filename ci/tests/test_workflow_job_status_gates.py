"""Job-level implicit ``success()`` must not silently skip work behind a mode-skipped ancestor.

GitHub adds an implicit ``success()`` to every job ``if:`` that names no status
check function (``always()``, ``success()``, ``failure()``, ``cancelled()``).
That implicit check covers every transitive ancestor, not only the direct
``needs``: a job whose direct needs all ran can still be skipped because an
earlier job was skipped by its own mode guard. ``product`` and ``android`` were
skipped this way in ordinary mode (``recovery-controls`` and
``dispatch-authorization`` are skipped there, ``workflow-lint`` and ``plan``
still run with ``always()``).
"""
from __future__ import annotations

import itertools
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github/workflows"

_UNKNOWN = object()
_STATUS_FUNCTIONS = re.compile(r"\b(?:always|success|failure|cancelled)\s*\(")
_MODE_INPUTS = ("toolingOnly", "runtimeRecoveryOnly", "sdkRecoveryOnly", "fullReuseAcceptanceOnly")
_MODES = {
    "ordinary": {},
    **{name: {name: True} for name in _MODE_INPUTS},
}
_EVENTS = ("pull_request", "merge_group", "workflow_dispatch")


def _jobs(text: str) -> dict[str, dict[str, object]]:
    lines = text.splitlines()
    start = lines.index("jobs:")
    headers = [(index, match.group(1)) for index, line in enumerate(lines[start + 1:], start + 1)
               if (match := re.fullmatch(r"  ([A-Za-z0-9_-]+):\s*", line))]
    jobs = {}
    for position, (index, name) in enumerate(headers):
        end = headers[position + 1][0] if position + 1 < len(headers) else len(lines)
        body = lines[index + 1:end]
        jobs[name] = {"needs": _needs(body), "if": _condition(body)}
    return jobs


def _needs(body: list[str]) -> tuple[str, ...]:
    for index, line in enumerate(body):
        match = re.fullmatch(r"    needs:\s*(.*?)\s*", line)
        if not match:
            continue
        value = match.group(1)
        if value.startswith("["):
            return tuple(item.strip() for item in value.strip("[]").split(",") if item.strip())
        if value:
            return (value,)
        items = []
        for item in body[index + 1:]:
            listed = re.fullmatch(r"      - ([A-Za-z0-9_-]+)\s*", item)
            if not listed:
                break
            items.append(listed.group(1))
        return tuple(items)
    return ()


def _condition(body: list[str]) -> str | None:
    for index, line in enumerate(body):
        match = re.fullmatch(r"    if:\s*(.*?)\s*", line)
        if not match:
            continue
        value = match.group(1)
        if value in {">-", ">", "|", "|-", ">+", "|+"}:
            block = []
            for item in body[index + 1:]:
                if item.strip() and not item.startswith("      "):
                    break
                block.append(item.strip())
            value = " ".join(part for part in block if part)
        elif len(value) >= 2 and value[0] == value[-1] == "'":
            value = value[1:-1].replace("''", "'")
        elif len(value) >= 2 and value[0] == value[-1] == '"':
            value = value[1:-1]
        value = value.strip()
        if value.startswith("${{") and value.endswith("}}"):
            value = value[3:-2].strip()
        return value
    return None


_TOKEN = re.compile(r"""\s*(?:
    (?P<string>'(?:[^']|'')*')
  | (?P<number>-?\d+(?:\.\d+)?)
  | (?P<op>&&|\|\||==|!=|<=|>=|[!<>()\[\],])
  | (?P<name>[A-Za-z_][A-Za-z0-9_-]*(?:\.(?:[A-Za-z0-9_-]+|\*))*)
  | (?P<property>(?:\.(?:[A-Za-z0-9_-]+|\*))+)
)""", re.VERBOSE)


def _tokens(expression: str) -> list[tuple[str, str]]:
    tokens, position = [], 0
    while position < len(expression):
        if expression[position:].strip() == "":
            break
        match = _TOKEN.match(expression, position)
        if match is None:
            raise ValueError(f"Cannot tokenize condition near: {expression[position:position + 40]!r}")
        kind = match.lastgroup
        tokens.append((kind, match.group(kind)))
        position = match.end()
    return tokens


class _Evaluator:
    """Kleene three-valued evaluation of a GitHub expression with partial context."""

    def __init__(self, expression: str, context: dict[str, object]):
        self.tokens = _tokens(expression)
        self.position = 0
        self.context = context

    def evaluate(self):
        value = self._or()
        if self.position != len(self.tokens):
            raise ValueError(f"Unparsed condition tail: {self.tokens[self.position:]}")
        return value

    def _peek(self):
        return self.tokens[self.position] if self.position < len(self.tokens) else (None, None)

    def _take(self, value=None):
        token = self._peek()
        if value is not None and token[1] != value:
            raise ValueError(f"Expected {value!r}, found {token!r}")
        self.position += 1
        return token

    def _or(self):
        value = self._and()
        while self._peek()[1] == "||":
            self._take()
            right = self._and()
            value = _or(value, right)
        return value

    def _and(self):
        value = self._comparison()
        while self._peek()[1] == "&&":
            self._take()
            right = self._comparison()
            value = _and(value, right)
        return value

    def _comparison(self):
        value = self._unary()
        while self._peek()[1] in {"==", "!=", "<", ">", "<=", ">="}:
            operator = self._take()[1]
            right = self._unary()
            if value is _UNKNOWN or right is _UNKNOWN or operator not in {"==", "!="}:
                value = _UNKNOWN
            else:
                equal = _normalize(value) == _normalize(right)
                value = equal if operator == "==" else not equal
        return value

    def _unary(self):
        if self._peek()[1] == "!":
            self._take()
            value = self._unary()
            return _UNKNOWN if value is _UNKNOWN else not _truthy(value)
        return self._primary()

    def _primary(self):
        kind, value = self._take()
        if value == "(":
            inner = self._or()
            self._take(")")
            return self._postfix(inner)
        if kind == "string":
            return self._postfix(value[1:-1].replace("''", "'"))
        if kind == "number":
            return float(value)
        if kind == "name":
            if self._peek()[1] == "(":
                self._take()
                arguments = []
                while self._peek()[1] != ")":
                    arguments.append(self._or())
                    if self._peek()[1] == ",":
                        self._take()
                self._take(")")
                return self._postfix(True if value == "always" else _UNKNOWN)
            if value in {"true", "false"}:
                return value == "true"
            if value == "null":
                return None
            return self._postfix(self.context.get(value, _UNKNOWN))
        raise ValueError(f"Unexpected token {value!r}")

    def _postfix(self, value):
        while self._peek()[1] == "[" or self._peek()[0] == "property":
            if self._take()[1] == "[":
                self._or()
                self._take("]")
            value = _UNKNOWN  # Indexing or dereferencing an evaluated value stays unknown.
        return value


def _normalize(value):
    return value.lower() if isinstance(value, str) else value


def _truthy(value):
    return bool(value) and value != 0


def _and(left, right):
    if left is not _UNKNOWN and not _truthy(left):
        return False
    if right is not _UNKNOWN and not _truthy(right):
        return False
    return _UNKNOWN if _UNKNOWN in (left, right) else True


def _or(left, right):
    if left is not _UNKNOWN and _truthy(left):
        return True
    if right is not _UNKNOWN and _truthy(right):
        return True
    return _UNKNOWN if _UNKNOWN in (left, right) else False


def _context(mode: dict[str, bool], event: str) -> dict[str, object]:
    context: dict[str, object] = {f"inputs.{name}": mode.get(name, False) for name in _MODE_INPUTS}
    context["github.event_name"] = event
    return context


def _ancestors(jobs, name, seen=None):
    seen = set() if seen is None else seen
    for parent in jobs[name]["needs"]:
        if parent not in seen:
            seen.add(parent)
            _ancestors(jobs, parent, seen)
    return seen


def implicit_success_violations(text: str) -> list[tuple[str, str, str, tuple[str, ...]]]:
    """Jobs that may run in a mode yet are skipped only by a transitive skipped ancestor."""
    jobs = _jobs(text)
    for name, job in jobs.items():
        unknown = set(job["needs"]) - set(jobs)
        if unknown:
            raise ValueError(f"{name} needs undefined jobs {sorted(unknown)}")
    violations = []
    for (mode_name, mode), event in itertools.product(_MODES.items(), _EVENTS):
        context = _context(mode, event)
        skipped: dict[str, bool] = {}

        def definitely_skipped(name):
            if name not in skipped:
                condition = jobs[name]["if"]
                own = True if condition is None else _Evaluator(condition, context).evaluate()
                implicit = condition is None or not _STATUS_FUNCTIONS.search(condition)
                skipped[name] = (own is not _UNKNOWN and not _truthy(own)) or (
                    implicit and any(definitely_skipped(parent) for parent in _ancestors(jobs, name)))
            return skipped[name]

        for name, job in jobs.items():
            condition = job["if"]
            if not job["needs"] or (condition is not None and _STATUS_FUNCTIONS.search(condition)):
                continue
            own = True if condition is None else _Evaluator(condition, context).evaluate()
            if own is not _UNKNOWN and not _truthy(own):
                continue  # The job's own guard already excludes this mode.
            if any(definitely_skipped(parent) for parent in job["needs"]):
                continue  # Documented direct-dependency skip, visible in the job's own needs.
            hidden = tuple(sorted(parent for parent in _ancestors(jobs, name) if definitely_skipped(parent)))
            if hidden:
                violations.append((name, mode_name, event, hidden))
    return violations


class WorkflowJobStatusGateTest(unittest.TestCase):
    def test_no_job_is_skipped_by_a_hidden_mode_skipped_ancestor(self) -> None:
        workflows = sorted(WORKFLOWS.glob("*.yml"))
        self.assertIn(WORKFLOWS / "product-validation.yml", workflows)
        for path in workflows:
            with self.subTest(workflow=path.name):
                self.assertEqual([], implicit_success_violations(path.read_text(encoding="utf-8")))

    def test_detector_flags_the_ordinary_mode_product_skip(self) -> None:
        workflow = """on: workflow_call
jobs:
  recovery-controls:
    if: inputs.runtimeRecoveryOnly || inputs.sdkRecoveryOnly
    runs-on: ubuntu-24.04
  plan:
    if: always() && !inputs.toolingOnly
    runs-on: ubuntu-24.04
  workflow-lint:
    if: always() && !inputs.toolingOnly
    needs: [plan, recovery-controls]
    runs-on: ubuntu-24.04
  product:
    if: >-
      !inputs.fullReuseAcceptanceOnly && (!inputs.runtimeRecoveryOnly && inputs.sdkRecoveryOnly != true &&
      needs.plan.outputs.event_authorized == 'true')
    needs: [workflow-lint, plan]
    runs-on: ubuntu-24.04
  direct:
    needs: recovery-controls
    runs-on: ubuntu-24.04
"""
        violations = implicit_success_violations(workflow)
        self.assertIn(("product", "ordinary", "pull_request", ("recovery-controls",)), violations)
        self.assertNotIn("direct", {name for name, *_ in violations})
        # Recovery modes are excluded by product's own guard, not by the hidden ancestor.
        self.assertFalse([item for item in violations if item[1] != "ordinary"])
        fixed = workflow.replace(
            "!inputs.fullReuseAcceptanceOnly && (!inputs.runtimeRecoveryOnly",
            "!inputs.fullReuseAcceptanceOnly && (always() && !cancelled() && "
            "needs.workflow-lint.result == 'success' && needs.plan.result == 'success' && !inputs.runtimeRecoveryOnly")
        self.assertEqual([], implicit_success_violations(fixed))

    def test_product_and_android_keep_every_gate_with_an_explicit_status_function(self) -> None:
        text = (WORKFLOWS / "product-validation.yml").read_text(encoding="utf-8")
        jobs = _jobs(text)
        explicit = ("always()", "!cancelled()", "needs.workflow-lint.result == 'success'",
                    "needs.plan.result == 'success'")
        common = ("!inputs.fullReuseAcceptanceOnly", "!inputs.runtimeRecoveryOnly", "inputs.sdkRecoveryOnly != true",
                  "needs.plan.outputs.event_authorized == 'true'",
                  "needs.plan.outputs.remote_build_authorized == 'true'",
                  "needs.plan.outputs.validation_reused != 'true'")
        specific = {
            "product": ("needs.plan.outputs.product_matrix != '[]'",),
            "android": ("needs.plan.outputs.reviewed_android != 'true'", "needs.plan.outputs.lane_android == 'true'"),
        }
        for name, extra in specific.items():
            with self.subTest(job=name):
                condition = jobs[name]["if"]
                self.assertEqual(("workflow-lint", "plan"), jobs[name]["needs"])
                for clause in (*explicit, *common, *extra):
                    self.assertIn(clause, condition)
                # Every clause stays conjunctive: a failed lint, plan or authorization still skips.
                self.assertNotIn("||", condition)
                self.assertTrue(condition.startswith(
                    "!inputs.fullReuseAcceptanceOnly && (!inputs.runtimeRecoveryOnly && always() && !cancelled() && "
                    "needs.workflow-lint.result == 'success' && needs.plan.result == 'success' && "))
                for mode_name, mode in _MODES.items():
                    for event in _EVENTS:
                        context = {**_context(mode, event),
                                   "needs.workflow-lint.result": "success", "needs.plan.result": "success"}
                        for failed in ("needs.workflow-lint.result", "needs.plan.result"):
                            for result in ("failure", "skipped", "cancelled"):
                                self.assertIs(False, _Evaluator(condition, {**context, failed: result}).evaluate(),
                                              (mode_name, event, failed, result))
                        if mode_name not in {"ordinary", "toolingOnly"}:  # toolingOnly skips plan itself.
                            self.assertIs(False, _Evaluator(condition, context).evaluate(), (mode_name, event))

    def test_workflow_lint_still_owns_source_and_build_logic_results(self) -> None:
        text = (WORKFLOWS / "product-validation.yml").read_text(encoding="utf-8")
        jobs = _jobs(text)
        self.assertEqual(("plan", "recovery-controls", "workflow-source-checks", "workflow-build-logic"),
                         jobs["workflow-lint"]["needs"])
        lint = text.split("\n  workflow-lint:\n", 1)[1].split("\n  workflow-source-checks:\n", 1)[0]
        self.assertIn('test "$SOURCE_RESULT" = success', lint)
        self.assertIn('test "$BUILD_LOGIC_RESULT" = success', lint)
        self.assertIn('test "$PLAN_RESULT" = success', lint)
        self.assertIn('test "$CHECKS_RESULT" = success', lint)

    def test_source_record_signs_only_after_a_fresh_successful_join(self) -> None:
        text = (WORKFLOWS / "product-validation.yml").read_text(encoding="utf-8")
        jobs = _jobs(text)
        checks, record = jobs["workflow-source-checks"], jobs["workflow-source-record"]
        self.assertEqual(("plan", "workflow-source-checks"), record["needs"])
        for condition in (checks["if"], record["if"]):
            self.assertTrue(condition.startswith("always() && !cancelled() && "))
        for mode_name, mode in _MODES.items():
            for event in _EVENTS:
                context = _context(mode, event)
                own = _Evaluator(checks["if"], context).evaluate()
                ready = {**context, "needs.plan.result": "success", "needs.workflow-source-checks.result": "success",
                         "needs.workflow-source-checks.outputs.reused": "false"}
                signed = _Evaluator(record["if"], ready).evaluate()
                with self.subTest(mode=mode_name, event=event):
                    if mode_name in {"toolingOnly", "runtimeRecoveryOnly", "sdkRecoveryOnly"}:
                        self.assertIs(False, own)
                        self.assertIs(False, signed)
                    else:
                        # Only cancellation (unknown here) can still skip the join.
                        self.assertIs(_UNKNOWN, own)
                        self.assertIs(_UNKNOWN, signed)
                    for field, values in (("needs.plan.result", ("failure", "skipped", "cancelled")),
                                          ("needs.workflow-source-checks.result", ("failure", "skipped", "cancelled")),
                                          ("needs.workflow-source-checks.outputs.reused", ("true", ""))):
                        for value in values:
                            self.assertIs(False, _Evaluator(record["if"], {**ready, field: value}).evaluate(),
                                          (field, value))


if __name__ == "__main__":
    unittest.main()
