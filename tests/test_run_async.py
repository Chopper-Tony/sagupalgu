"""_run_async 전용 이벤트루프 스레드 패턴 unit 테스트."""

from __future__ import annotations

import asyncio
import concurrent.futures
import time

import pytest

from app.graph.nodes.helpers import _get_dedicated_loop, _run_async


pytestmark = pytest.mark.unit


# ── 기본 동작 ──────────────────────────────────────────────


class TestRunAsyncBasic:
    """_run_async 기본 동작 검증."""

    def test_coroutine_execution(self):
        """코루틴을 정상 실행하고 결과를 반환한다."""

        async def add(a, b):
            return a + b

        assert _run_async(add(3, 4)) == 7

    def test_callable_factory(self):
        """callable(lambda)을 받아 코루틴을 생성 후 실행한다."""

        async def greet(name):
            return f"hello {name}"

        result = _run_async(lambda: greet("world"))
        assert result == "hello world"

    def test_exception_propagation(self):
        """코루틴 내부 예외가 호출자에게 전파된다."""

        async def fail():
            raise ValueError("test error")

        with pytest.raises(ValueError, match="test error"):
            _run_async(lambda: fail())

    def test_awaitable_chain(self):
        """여러 await를 포함하는 코루틴이 정상 동작한다."""

        async def inner():
            await asyncio.sleep(0.01)
            return 42

        async def outer():
            val = await inner()
            return val * 2

        assert _run_async(lambda: outer()) == 84


# ── 전용 루프 싱글턴 ──────────────────────────────────────


class TestDedicatedLoop:
    """_get_dedicated_loop 싱글턴 검증."""

    def test_singleton_reuse(self):
        """동일한 루프 인스턴스를 재사용한다."""
        loop1 = _get_dedicated_loop()
        loop2 = _get_dedicated_loop()
        assert loop1 is loop2

    def test_loop_is_running(self):
        """전용 루프가 실행 중이다."""
        loop = _get_dedicated_loop()
        assert loop.is_running()


# ── running loop 컨텍스트 ──────────────────────────────────


class TestRunningLoopContext:
    """이미 running loop이 있는 환경에서도 정상 동작."""

    def test_works_inside_running_loop(self):
        """uvicorn 등 이미 이벤트루프가 실행 중인 컨텍스트에서도 동작한다."""

        async def check():
            return "ok"

        # 별도 스레드에서 running loop 내에서 _run_async 호출
        def run_in_loop():
            loop = asyncio.new_event_loop()

            async def wrapper():
                # 여기서 이벤트루프가 이미 실행 중
                return _run_async(lambda: check())

            try:
                return loop.run_until_complete(wrapper())
            finally:
                loop.close()

        with concurrent.futures.ThreadPoolExecutor() as pool:
            result = pool.submit(run_in_loop).result()
        assert result == "ok"


# ── 동시 호출 thread-safety ────────────────────────────────


class TestConcurrency:
    """concurrent 호출 시 thread-safety 검증."""

    def test_concurrent_calls(self):
        """여러 스레드에서 동시에 _run_async를 호출해도 안전하다."""

        async def compute(n):
            await asyncio.sleep(0.01)
            return n * n

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(_run_async, lambda n=i: compute(n)) for i in range(8)]
            results = sorted(f.result() for f in futures)

        assert results == [0, 1, 4, 9, 16, 25, 36, 49]
