import time
import unittest
from utils.rate_limiter import TokenBucketRateLimiter

class TestTokenBucketRateLimiter(unittest.TestCase):
    def test_immediate_acquire(self):
        """Test that we can acquire tokens immediately if available."""
        limiter = TokenBucketRateLimiter(capacity=5, refill_rate=1)
        start = time.monotonic()
        limiter.acquire(1)
        duration = time.monotonic() - start
        self.assertLess(duration, 0.1, "Should acquire immediately")

    def test_rate_limiting(self):
        """Test that we wait when tokens are exhausted."""
        # Capacity 1, refill 10 per second (0.1s per token)
        limiter = TokenBucketRateLimiter(capacity=1, refill_rate=10)
        
        # Consume the initial token
        limiter.acquire(1)
        
        start = time.monotonic()
        # Try to acquire another one immediately. Should wait ~0.1s
        limiter.acquire(1)
        duration = time.monotonic() - start
        
        self.assertGreaterEqual(duration, 0.09, "Should wait for refill")
        self.assertLess(duration, 0.2, "Should not wait too long")

    def test_burst_refill(self):
        """Test that bucket refills up to capacity."""
        limiter = TokenBucketRateLimiter(capacity=2, refill_rate=10)
        limiter.acquire(2) # Empty it
        
        # Wait enough for full refill (0.2s)
        time.sleep(0.25)
        
        start = time.monotonic()
        limiter.acquire(2) # Should be immediate
        duration = time.monotonic() - start
        self.assertLess(duration, 0.1, "Should have refilled to capacity")

if __name__ == "__main__":
    unittest.main()
