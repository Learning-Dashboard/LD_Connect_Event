"""
Token Bucket Rate Limiter implementation.
"""
import time
import threading
import logging

LOGGER = logging.getLogger(__name__)

class TokenBucketRateLimiter:
    """
    A thread-safe token bucket rate limiter.
    
    The bucket has a capacity (max tokens) and refills at a specific rate (tokens per second).
    Consuming a token removes it from the bucket. If the bucket is empty, the caller blocks
    until a token becomes available.
    """
    def __init__(self, capacity: float, refill_rate: float):
        """
        :param capacity: Maximum number of tokens the bucket can hold (burst size).
        :param refill_rate: Number of tokens added per second.
        """
        self.capacity = float(capacity)
        self.tokens = float(capacity)
        self.refill_rate = float(refill_rate)
        self.last_refill = time.monotonic()
        self.lock = threading.Lock()

    def acquire(self, tokens: float = 1.0) -> None:
        """
        Acquire tokens from the bucket. Blocks if insufficient tokens are available.
        """
        with self.lock:
            while True:
                self._refill()
                if self.tokens >= tokens:
                    self.tokens -= tokens
                    return
                
                # Calculate time to wait for enough tokens
                needed = tokens - self.tokens
                wait_time = needed / self.refill_rate
                if wait_time > 0:
                    # LOGGER.debug(f"Rate limiter: waiting {wait_time:.3f}s for tokens.")
                    time.sleep(wait_time)

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self.last_refill
        if elapsed > 0:
            added = elapsed * self.refill_rate
            self.tokens = min(self.capacity, self.tokens + added)
            self.last_refill = now
