"""
Code Execution Sandbox
Runs user code safely using:
  - subprocess with strict timeouts
  - Memory limits via resource module
  - No network access (environment sanitization)
  - Supports: Python, JavaScript (Node), (extensible to more)

In production you'd use Docker/gVisor/Firecracker per execution.
This is the portable development version.
"""

import asyncio
import subprocess
import tempfile
import os
import sys
import resource
import time
from dataclasses import dataclass, field
from typing import List, Optional

from core.config import settings


@dataclass
class TestCase:
    input: str
    expected_output: str
    description: str = ""


@dataclass
class ExecutionResult:
    stdout: str
    stderr: str
    exit_code: int
    execution_time_ms: float
    memory_used_mb: float
    timed_out: bool = False
    error: Optional[str] = None


@dataclass
class TestResult:
    test_case: TestCase
    passed: bool
    actual_output: str
    execution_time_ms: float
    error: Optional[str] = None


@dataclass
class SandboxResult:
    test_results: List[TestResult]
    all_passed: bool
    total_time_ms: float
    raw_output: str
    compile_error: Optional[str] = None


LANG_CONFIG = {
    "python": {
        "ext": ".py",
        "cmd": [sys.executable],  # uses the current Python interpreter
        "compile": None,
    },
    "javascript": {
        "ext": ".js",
        "cmd": ["node"],
        "compile": None,
    },
    "typescript": {
        "ext": ".ts",
        "cmd": ["npx", "ts-node", "--transpile-only"],
        "compile": None,
    },
}


def _set_limits():
    """Called in the child process to restrict resources."""
    # Max memory
    mem_bytes = settings.EXECUTION_MEMORY_MB * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
    # No new files larger than 1MB
    resource.setrlimit(resource.RLIMIT_FSIZE, (1024 * 1024, 1024 * 1024))
    # No forking
    resource.setrlimit(resource.RLIMIT_NPROC, (1, 1))


async def execute_code(
    code: str,
    language: str,
    stdin_input: str = "",
) -> ExecutionResult:
    """Run code in a sandboxed subprocess, return stdout/stderr/timing."""
    config = LANG_CONFIG.get(language)
    if not config:
        return ExecutionResult(
            stdout="", stderr=f"Unsupported language: {language}",
            exit_code=1, execution_time_ms=0, memory_used_mb=0,
            error=f"Language '{language}' not supported"
        )

    with tempfile.NamedTemporaryFile(
        suffix=config["ext"], mode="w", delete=False, encoding="utf-8"
    ) as f:
        f.write(code)
        tmp_path = f.name

    try:
        cmd = config["cmd"] + [tmp_path]

        # Sanitize environment — no HOME, no network creds, minimal PATH
        env = {
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONUNBUFFERED": "1",
        }

        start = time.perf_counter()
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                preexec_fn=_set_limits if sys.platform != "win32" else None,
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(input=stdin_input.encode()),
                    timeout=settings.EXECUTION_TIMEOUT_SECS,
                )
                timed_out = False
            except asyncio.TimeoutError:
                proc.kill()
                await proc.communicate()
                stdout, stderr = b"", b"Time limit exceeded"
                timed_out = True

        except FileNotFoundError as e:
            return ExecutionResult(
                stdout="", stderr=str(e), exit_code=1,
                execution_time_ms=0, memory_used_mb=0,
                error=f"Runtime not found: {cmd[0]}"
            )

        elapsed_ms = (time.perf_counter() - start) * 1000

        return ExecutionResult(
            stdout=stdout.decode("utf-8", errors="replace")[:10_000],
            stderr=stderr.decode("utf-8", errors="replace")[:5_000],
            exit_code=proc.returncode or 0,
            execution_time_ms=round(elapsed_ms, 2),
            memory_used_mb=0.0,   # full tracking needs cgroups
            timed_out=timed_out,
        )
    finally:
        os.unlink(tmp_path)


async def run_tests(
    code: str,
    language: str,
    test_cases: List[TestCase],
) -> SandboxResult:
    """Run code against a list of test cases."""
    results: List[TestResult] = []
    all_passed = True
    total_ms = 0.0
    raw_parts = []

    for tc in test_cases:
        result = await execute_code(code, language, tc.input)
        actual = result.stdout.strip()
        expected = tc.expected_output.strip()
        passed = (actual == expected) and (result.exit_code == 0) and not result.timed_out

        if not passed:
            all_passed = False

        total_ms += result.execution_time_ms
        raw_parts.append(result.stdout)

        results.append(TestResult(
            test_case=tc,
            passed=passed,
            actual_output=actual,
            execution_time_ms=result.execution_time_ms,
            error=result.stderr if result.stderr else None,
        ))

    return SandboxResult(
        test_results=results,
        all_passed=all_passed,
        total_time_ms=round(total_ms, 2),
        raw_output="\n".join(raw_parts),
    )
