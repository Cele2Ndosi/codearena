"""
sandbox.py — Multi-language code execution sandbox.

Architecture:
- LANGUAGES dict defines all supported languages with compile + run commands
- detect_available_languages() probes which runtimes are installed at startup
- execute_code() compiles (if needed) then runs user code in a subprocess
- Resource limits: RLIMIT_CPU for runaway loops, asyncio timeout for wall-clock

Security note: This is a development sandbox.
Production should use Docker --network=none + seccomp + cgroup v2.
"""

import asyncio
import os
import resource
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ExecutionResult:
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool
    wall_time_ms: float
    language: str


MAX_OUTPUT_BYTES = 64 * 1024  # 64 KB
TIMEOUT_SECONDS  = 10


# ── Language definitions ──────────────────────────────────────────────────────
# Each entry:
#   binary      : executable to check for (shutil.which)
#   ext         : source file extension
#   run         : list of args to run; {src} = source path, {bin} = output binary
#   compile     : optional compile step before running
#   version_flag: flag to get version string
#   aliases     : alternative names the frontend might send

LANGUAGES: dict[str, dict] = {
    # Interpreted ─────────────────────────────────────────────────────────────
    "python": {
        "binary": "python3",
        "ext": ".py",
        "run": ["python3", "-u", "{src}"],
        "version_flag": "--version",
        "aliases": ["python3", "py"],
        "label": "Python",
    },
    "javascript": {
        "binary": "node",
        "ext": ".js",
        "run": ["node", "{src}"],
        "version_flag": "--version",
        "aliases": ["js", "node", "nodejs"],
        "label": "JavaScript (Node)",
    },
    "typescript": {
        "binary": "npx",           # uses ts-node via npx
        "ext": ".ts",
        "run": ["npx", "--yes", "ts-node", "--skip-project", "{src}"],
        "version_flag": "--version",
        "aliases": ["ts"],
        "label": "TypeScript",
    },
    "ruby": {
        "binary": "ruby",
        "ext": ".rb",
        "run": ["ruby", "{src}"],
        "version_flag": "--version",
        "aliases": ["rb"],
        "label": "Ruby",
    },
    "php": {
        "binary": "php",
        "ext": ".php",
        "run": ["php", "{src}"],
        "version_flag": "--version",
        "aliases": [],
        "label": "PHP",
    },
    "perl": {
        "binary": "perl",
        "ext": ".pl",
        "run": ["perl", "{src}"],
        "version_flag": "--version",
        "aliases": [],
        "label": "Perl",
    },
    "lua": {
        "binary": "lua",
        "ext": ".lua",
        "run": ["lua", "{src}"],
        "version_flag": "-v",
        "aliases": ["lua5.4", "lua5.3"],
        "label": "Lua",
    },
    "r": {
        "binary": "Rscript",
        "ext": ".r",
        "run": ["Rscript", "{src}"],
        "version_flag": "--version",
        "aliases": ["rscript"],
        "label": "R",
    },
    "julia": {
        "binary": "julia",
        "ext": ".jl",
        "run": ["julia", "{src}"],
        "version_flag": "--version",
        "aliases": [],
        "label": "Julia",
    },
    "elixir": {
        "binary": "elixir",
        "ext": ".exs",
        "run": ["elixir", "{src}"],
        "version_flag": "--version",
        "aliases": ["ex", "exs"],
        "label": "Elixir",
    },
    # Compiled ─────────────────────────────────────────────────────────────────
    "c": {
        "binary": "gcc",
        "ext": ".c",
        "compile": ["gcc", "-O2", "-o", "{bin}", "{src}", "-lm"],
        "run": ["{bin}"],
        "version_flag": "--version",
        "aliases": ["gcc"],
        "label": "C (GCC)",
    },
    "cpp": {
        "binary": "g++",
        "ext": ".cpp",
        "compile": ["g++", "-O2", "-std=c++20", "-o", "{bin}", "{src}"],
        "run": ["{bin}"],
        "version_flag": "--version",
        "aliases": ["c++", "cxx", "g++"],
        "label": "C++ 20",
    },
    "rust": {
        "binary": "rustc",
        "ext": ".rs",
        "compile": ["rustc", "-O", "-o", "{bin}", "{src}"],
        "run": ["{bin}"],
        "version_flag": "--version",
        "aliases": ["rs"],
        "label": "Rust",
    },
    "go": {
        "binary": "go",
        "ext": ".go",
        "run": ["go", "run", "{src}"],
        "version_flag": "version",
        "aliases": ["golang"],
        "label": "Go",
    },
    "java": {
        "binary": "java",
        "ext": ".java",
        "compile": ["javac", "{src}"],
        "run": ["java", "-cp", "{dir}", "{classname}"],
        "version_flag": "--version",
        "aliases": [],
        "label": "Java",
        "needs_classname": True,
    },
    "kotlin": {
        "binary": "kotlinc",
        "ext": ".kt",
        "compile": ["kotlinc", "{src}", "-include-runtime", "-d", "{bin}.jar"],
        "run": ["java", "-jar", "{bin}.jar"],
        "version_flag": "-version",
        "aliases": ["kt"],
        "label": "Kotlin",
    },
    "swift": {
        "binary": "swift",
        "ext": ".swift",
        "run": ["swift", "{src}"],
        "version_flag": "--version",
        "aliases": [],
        "label": "Swift",
    },
    "csharp": {
        "binary": "dotnet",
        "ext": ".csx",
        "run": ["dotnet", "script", "{src}"],
        "version_flag": "--version",
        "aliases": ["cs", "c#", "dotnet"],
        "label": "C# (dotnet-script)",
    },
    "scala": {
        "binary": "scala",
        "ext": ".sc",
        "run": ["scala", "{src}"],
        "version_flag": "--version",
        "aliases": [],
        "label": "Scala",
    },
    "groovy": {
        "binary": "groovy",
        "ext": ".groovy",
        "run": ["groovy", "{src}"],
        "version_flag": "--version",
        "aliases": [],
        "label": "Groovy",
    },
    "haskell": {
        "binary": "runghc",
        "ext": ".hs",
        "run": ["runghc", "{src}"],
        "version_flag": "--version",
        "aliases": ["ghc", "hs"],
        "label": "Haskell",
    },
    "bash": {
        "binary": "bash",
        "ext": ".sh",
        "run": ["bash", "{src}"],
        "version_flag": "--version",
        "aliases": ["sh", "shell"],
        "label": "Bash",
    },
    "dart": {
        "binary": "dart",
        "ext": ".dart",
        "run": ["dart", "run", "{src}"],
        "version_flag": "--version",
        "aliases": [],
        "label": "Dart",
    },
    "nim": {
        "binary": "nim",
        "ext": ".nim",
        "compile": ["nim", "c", "-o:{bin}", "--hints:off", "{src}"],
        "run": ["{bin}"],
        "version_flag": "--version",
        "aliases": [],
        "label": "Nim",
    },
    "zig": {
        "binary": "zig",
        "ext": ".zig",
        "run": ["zig", "run", "{src}"],
        "version_flag": "version",
        "aliases": [],
        "label": "Zig",
    },
    "python2": {
        "binary": "python2",
        "ext": ".py",
        "run": ["python2", "{src}"],
        "version_flag": "--version",
        "aliases": ["py2"],
        "label": "Python 2",
    },
}


# ── Runtime detection ─────────────────────────────────────────────────────────

_available: dict[str, dict] | None = None   # cached after first call


def detect_available_languages() -> dict[str, dict]:
    """
    Probe which language runtimes are installed.
    Returns a dict of {lang_id: {label, version, available: True}}.
    Called once at startup, result is cached.
    """
    global _available
    if _available is not None:
        return _available

    result = {}
    for lang_id, spec in LANGUAGES.items():
        binary = spec["binary"]
        # Check primary binary
        found = shutil.which(binary)
        # Check aliases if primary not found
        if not found:
            for alias in spec.get("aliases", []):
                found = shutil.which(alias)
                if found:
                    break

        if found:
            # Get version string
            try:
                v_flag = spec.get("version_flag", "--version")
                out = subprocess.run(
                    [found, v_flag],
                    capture_output=True, text=True, timeout=3
                )
                version = (out.stdout or out.stderr or "").split("\n")[0].strip()[:60]
            except Exception:
                version = "unknown version"

            result[lang_id] = {
                "id":        lang_id,
                "label":     spec["label"],
                "version":   version,
                "available": True,
                "ext":       spec["ext"],
            }
        else:
            result[lang_id] = {
                "id":        lang_id,
                "label":     spec["label"],
                "version":   None,
                "available": False,
                "ext":       spec["ext"],
            }

    _available = result
    available_count = sum(1 for v in result.values() if v["available"])
    print(f"[sandbox] Detected {available_count}/{len(result)} language runtimes")
    return result


def resolve_lang(lang: str) -> str | None:
    """
    Resolve a language string (possibly an alias) to a canonical lang_id.
    Returns None if not found.
    """
    lang = lang.lower().strip()
    if lang in LANGUAGES:
        return lang
    for lang_id, spec in LANGUAGES.items():
        if lang in [a.lower() for a in spec.get("aliases", [])]:
            return lang_id
    return None


# ── Resource limits ───────────────────────────────────────────────────────────

def _set_resource_limits():
    """CPU time limit. Wall-clock timeout handled by asyncio.wait_for()."""
    resource.setrlimit(resource.RLIMIT_CPU, (TIMEOUT_SECONDS, TIMEOUT_SECONDS))
    try:
        resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
    except ValueError:
        pass


# ── Code execution ────────────────────────────────────────────────────────────

async def execute_code(code: str, language: str = "python") -> ExecutionResult:
    """
    Write code to a temp file and execute it.
    Handles both interpreted and compiled languages.
    """
    lang_id = resolve_lang(language) or "python"
    spec = LANGUAGES.get(lang_id)
    if not spec:
        return ExecutionResult("", f"Unsupported language: {language}",
                               1, False, 0, language)

    available = detect_available_languages()
    if not available.get(lang_id, {}).get("available"):
        return ExecutionResult(
            "", f"Runtime for '{spec['label']}' is not installed on this server.\n"
                f"Install it and restart the backend.",
            1, False, 0, lang_id
        )

    with tempfile.TemporaryDirectory() as tmpdir:
        ext  = spec["ext"]
        src  = os.path.join(tmpdir, f"solution{ext}")
        bin_ = os.path.join(tmpdir, "solution_bin")

        # Java needs the class name to match the filename
        classname = "Solution"
        if spec.get("needs_classname"):
            # Extract public class name or default to Solution
            import re
            m = re.search(r"public\s+class\s+(\w+)", code)
            classname = m.group(1) if m else "Solution"
            src = os.path.join(tmpdir, f"{classname}{ext}")

        with open(src, "w", encoding="utf-8") as f:
            f.write(code)

        start = time.perf_counter()

        # ── Compile step (if needed) ──────────────────────────────────────
        if "compile" in spec:
            compile_cmd = [
                a.replace("{src}", src)
                 .replace("{bin}", bin_)
                 .replace("{dir}", tmpdir)
                 .replace("{classname}", classname)
                for a in spec["compile"]
            ]
            try:
                compile_proc = await asyncio.create_subprocess_exec(
                    *compile_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=tmpdir,
                )
                try:
                    cout, cerr = await asyncio.wait_for(
                        compile_proc.communicate(), timeout=30
                    )
                except asyncio.TimeoutError:
                    compile_proc.kill()
                    return ExecutionResult("", "Compilation timed out (30s)",
                                          1, True, 30000, lang_id)

                if compile_proc.returncode != 0:
                    return ExecutionResult(
                        "",
                        cerr.decode("utf-8", errors="replace")[:MAX_OUTPUT_BYTES],
                        compile_proc.returncode, False,
                        (time.perf_counter() - start) * 1000,
                        lang_id,
                    )
            except Exception as e:
                return ExecutionResult("", f"Compile error: {e}", 1, False, 0, lang_id)

        # ── Run step ──────────────────────────────────────────────────────
        run_cmd = [
            a.replace("{src}", src)
             .replace("{bin}", bin_)
             .replace("{dir}", tmpdir)
             .replace("{classname}", classname)
            for a in spec["run"]
        ]

        try:
            proc = await asyncio.create_subprocess_exec(
                *run_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                preexec_fn=_set_resource_limits,
                cwd=tmpdir,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            )
            try:
                stdout_b, stderr_b = await asyncio.wait_for(
                    proc.communicate(), timeout=TIMEOUT_SECONDS + 1
                )
                timed_out = False
            except asyncio.TimeoutError:
                proc.kill()
                await proc.communicate()
                stdout_b, stderr_b = b"", b"Execution timed out (10s limit)\n"
                timed_out = True

            return ExecutionResult(
                stdout=stdout_b[:MAX_OUTPUT_BYTES].decode("utf-8", errors="replace"),
                stderr=stderr_b[:MAX_OUTPUT_BYTES].decode("utf-8", errors="replace"),
                exit_code=proc.returncode or 0,
                timed_out=timed_out,
                wall_time_ms=round((time.perf_counter() - start) * 1000, 1),
                language=lang_id,
            )
        except Exception as e:
            return ExecutionResult("", f"Execution error: {e}", 1, False, 0, lang_id)


# ── Test harness ──────────────────────────────────────────────────────────────

async def run_test_suite(
    user_code: str, language: str, problem_id: str = "two-sum"
) -> list[dict]:
    """Run the problem's test harness against the user's code."""
    lang_id = resolve_lang(language) or "python"

    if lang_id != "python":
        # Run the code as-is and return a single execution result
        result = await execute_code(user_code, lang_id)
        if result.exit_code == 0:
            return [{"name": "Code runs without errors", "pass": True, "time": f"{result.wall_time_ms:.0f}ms"}]
        else:
            return [{"name": "Runtime error", "pass": False,
                     "time": f"{result.wall_time_ms:.0f}ms",
                     "error": (result.stderr or result.stdout)[:200]}]

    from problems import get_problem
    problem = await get_problem(problem_id)
    if not problem:
        return [{"name": f"Unknown problem: {problem_id}", "pass": False, "time": "0ms"}]

    harness = problem.get("test_harness", "")
    if not harness:
        result = await execute_code(user_code, "python")
        return [{"name": "Code runs without errors",
                 "pass": result.exit_code == 0,
                 "time": f"{result.wall_time_ms:.0f}ms"}]

    full_code = user_code + "\n\n" + harness + """
import sys, inspect
try:
    user_classes = [obj for name, obj in list(globals().items())
                    if inspect.isclass(obj) and obj.__module__ == '__main__']
    if not user_classes:
        for cls_name in ['LockFreeQueue','LRUCache','ConsistentHashRing',
                          'RateLimiter','Trie','Solution']:
            if cls_name in globals():
                user_classes = [globals()[cls_name]]
                break
    if not user_classes:
        print("FAIL|No class found in your code|0ms")
        sys.exit(0)
    results = run_tests(user_classes[0])
    for name, passed, t in results:
        print(f"{'PASS' if passed else 'FAIL'}|{name}|{t}")
except Exception as e:
    print(f"FAIL|Harness error: {e}|0ms")
"""

    result = await execute_code(full_code, "python")
    tests = []
    for line in result.stdout.strip().splitlines():
        parts = line.split("|", 2)
        if len(parts) == 3:
            status, name, t = parts
            tests.append({"name": name, "pass": status == "PASS", "time": t})

    if result.stderr and not tests:
        tests.append({"name": "Runtime error", "pass": False,
                       "time": "0ms", "error": result.stderr[:300]})
    if not tests:
        tests.append({"name": "No output from test runner", "pass": False, "time": "0ms"})

    return tests
