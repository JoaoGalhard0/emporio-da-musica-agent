"""The client's pacing, tested with a fake clock so no real time passes."""
from emporio_agent.llm import RateLimiter


class FakeTime:
    def __init__(self):
        self.now, self.slept = 0.0, []

    def clock(self):
        return self.now

    def sleep(self, seconds):
        self.slept.append(round(seconds, 2))
        self.now += seconds


def limiter(per_minute):
    t = FakeTime()
    return RateLimiter(per_minute, t.clock, t.sleep), t


def test_calls_under_the_limit_do_not_wait():
    rl, t = limiter(3)
    for _ in range(3):
        rl.wait()
    assert t.slept == []


def test_the_call_over_the_limit_waits_for_the_oldest_to_age_out():
    rl, t = limiter(3)
    for _ in range(3):
        rl.wait()
        t.now += 10  # calls at t=0, 10, 20; now t=30
    rl.wait()
    assert t.slept == [30.0]  # the 4th must wait until the first call is 60 s old


def test_window_slides_instead_of_resetting():
    rl, t = limiter(2)
    rl.wait()          # t=0
    t.now = 50
    rl.wait()          # t=50, two calls in the window
    t.now = 61
    rl.wait()          # t=0 aged out, so no wait
    assert t.slept == []
    rl.wait()          # window holds t=50 and t=61: the next waits until t=110
    assert t.slept == [49.0]


def test_zero_disables_pacing():
    rl, t = limiter(0)
    for _ in range(100):
        rl.wait()
    assert t.slept == []


def test_concurrent_callers_never_exceed_the_limit():
    import threading

    rl, t = limiter(5)
    threads = [threading.Thread(target=rl.wait) for _ in range(20)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()

    assert len(rl._calls) <= 5
    assert t.now >= 180  # 20 calls at 5 per minute need at least three full waits
