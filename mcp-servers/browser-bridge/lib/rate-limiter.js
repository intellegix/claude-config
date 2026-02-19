/**
 * RateLimiter — token bucket algorithm for request throttling.
 */

export class RateLimiter {
  constructor(maxTokens = 60, refillRate = 1) {
    this.buckets = new Map();
    this.maxTokens = maxTokens;
    this.refillRate = refillRate; // tokens per second
  }
  check(clientId) {
    const now = Date.now();
    let bucket = this.buckets.get(clientId);
    if (!bucket) {
      bucket = { tokens: this.maxTokens, lastRefill: now };
      this.buckets.set(clientId, bucket);
    }
    const elapsed = (now - bucket.lastRefill) / 1000;
    bucket.tokens = Math.min(this.maxTokens, bucket.tokens + elapsed * this.refillRate);
    bucket.lastRefill = now;
    if (bucket.tokens < 1) return false;
    bucket.tokens--;
    return true;
  }
}
