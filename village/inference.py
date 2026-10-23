"""Hard wall deadlines shared by live play, evaluation and reliability probes.

File: village/inference.py
Maintainer: sunshine-engineer
Modified: 2026-10-23
"""

import math
import multiprocessing
import time

from .config import configure


def send_result(connection, result):
    """Send a worker response unless the deadline-owning parent has already closed its pipe.

    Args:
        connection: Multiprocessing pipe endpoint used for one response.
        result: Returned decision or result envelope being consumed.

    Returns:
        None; broken-pipe/EOF/OS errors during sending are intentionally ignored.
    """
    try:
        connection.send(result)
    except (BrokenPipeError, EOFError, OSError):
        pass  # Parent may already have reached its deadline or been interrupted.


def model_worker(connection, config_path, profile, observation, timeout):
    """Spawned request process: initialization cannot mutate the parent's world.

    Args:
        connection: Multiprocessing pipe endpoint used for one response.
        config_path: Startup JSON path, or trusted resolved snapshot when accepted by the worker.
        profile: Resolved model profile containing backend and generation options.
        observation: Request-time context containing legal choices and relevant world state.
        timeout: Maximum request wall time in seconds.

    Returns:
        None; errors are serialized and the pipe is always closed.
    """
    try:
        if isinstance(config_path, dict):
            from .config import configure_snapshot

            configure_snapshot(config_path)
        else:
            configure(config_path)
        from .extensions import load_extensions
        from .models import request_decision

        load_extensions()
        decision = request_decision(
            profile["url"],
            profile["model"],
            observation,
            timeout=timeout,
            profile=profile,
        )
        send_result(
            connection,
            {
                "status": "ok",
                "decision": dict(decision),
                "inference": getattr(decision, "metrics", {}),
            },
        )
    except Exception as exc:
        send_result(
            connection,
            {"status": "error", "error": f"{type(exc).__name__}: {str(exc)[:180]}"},
        )
    finally:
        connection.close()


def bounded_decision(profile, observation, config_path, timeout, *, worker=None):
    """Enforce a wall deadline even when a custom transport ignores its timeout.

    Args:
        profile: Resolved model profile containing backend and generation options.
        observation: Request-time context containing legal choices and relevant world state.
        config_path: Startup JSON path, or trusted resolved snapshot when accepted by the worker.
        timeout: Maximum request wall time in seconds.
        worker: Optional spawned worker override used by contract/deadline tests.

    Returns:
        Status envelope with decision/error, optional provider metrics and latency_ms.
    """
    if not math.isfinite(timeout) or timeout <= 0:
        return {
            "status": "timeout",
            "error": "No model time budget remains",
            "latency_ms": 0.0,
        }
    context = multiprocessing.get_context("spawn")
    parent, child = context.Pipe(duplex=False)
    process = context.Process(
        target=worker or model_worker,
        args=(
            child,
            config_path if isinstance(config_path, dict) else str(config_path),
            profile,
            observation,
            timeout,
        ),
        daemon=True,
    )
    started = time.monotonic()
    try:
        process.start()
        child.close()
        remaining = max(0, timeout - (time.monotonic() - started))
        if parent.poll(remaining):
            try:
                result = parent.recv()
            except EOFError:
                result = {
                    "status": "error",
                    "error": "Model process exited without a response",
                }
        else:
            result = {
                "status": "timeout",
                "error": "Model checkpoint wall-time limit exceeded",
            }
    except (OSError, ValueError) as exc:
        result = {"status": "error", "error": f"{type(exc).__name__}: {exc}"}
    finally:
        child.close()
        parent.close()
        if process.pid is not None:
            # Never leave model workers running into subsequent seed/mode runs.
            process.join(timeout=0)
            if process.is_alive():
                process.terminate()
                process.join(timeout=0.2)
            if process.is_alive():
                process.kill()
                process.join(timeout=0.2)
            if not process.is_alive():
                process.close()
    result["latency_ms"] = (time.monotonic() - started) * 1000
    return result
