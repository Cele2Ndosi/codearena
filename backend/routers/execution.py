"""
Execution Router
Runs user code in the sandbox and returns results.
"""

from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Optional

from services.sandbox import execute_code, run_tests, TestCase

router = APIRouter()


class RunRequest(BaseModel):
    code: str
    language: str
    stdin: str = ""


class TestCaseModel(BaseModel):
    input: str
    expected_output: str
    description: str = ""


class TestRequest(BaseModel):
    code: str
    language: str
    test_cases: List[TestCaseModel]


@router.post("/run")
async def run_code(req: RunRequest):
    """Execute code with optional stdin, return stdout/stderr."""
    result = await execute_code(req.code, req.language, req.stdin)
    return {
        "stdout": result.stdout,
        "stderr": result.stderr,
        "exit_code": result.exit_code,
        "execution_time_ms": result.execution_time_ms,
        "timed_out": result.timed_out,
        "error": result.error,
    }


@router.post("/test")
async def test_code(req: TestRequest):
    """Run code against a suite of test cases."""
    cases = [TestCase(tc.input, tc.expected_output, tc.description) for tc in req.test_cases]
    result = await run_tests(req.code, req.language, cases)

    return {
        "all_passed": result.all_passed,
        "total_time_ms": result.total_time_ms,
        "raw_output": result.raw_output,
        "test_results": [
            {
                "description": r.test_case.description,
                "passed": r.passed,
                "input": r.test_case.input,
                "expected": r.test_case.expected_output,
                "actual": r.actual_output,
                "time_ms": r.execution_time_ms,
                "error": r.error,
            }
            for r in result.test_results
        ],
    }
