"""Blogwatcher scan service."""

from __future__ import annotations

import asyncio


async def run_scan() -> dict[str, int | str]:
    try:
        proc = await asyncio.create_subprocess_exec(
            "blogwatcher-cli",
            "scan",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=120.0)
            stdout = stdout_bytes.decode() if stdout_bytes else ""
            stderr = stderr_bytes.decode() if stderr_bytes else ""
            returncode = proc.returncode
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            return {"ok": 0, "error": "Scan timed out (>120s)"}

        return {"ok": 1, "stdout": stdout, "stderr": stderr, "returncode": returncode}
    except FileNotFoundError:
        return {"ok": 0, "error": "blogwatcher-cli not found in PATH"}
