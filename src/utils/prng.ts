/**
 * Mulberry32 — fast, seedable 32-bit PRNG.
 * Same seed always produces the same sequence, making sessions reproducible.
 */
export class SeededRNG {
  private s: number

  constructor(seed: number) {
    this.s = seed >>> 0
  }

  /** Returns a float in [0, 1) */
  next(): number {
    this.s = (this.s + 0x6d2b79f5) >>> 0
    let z = this.s
    z = Math.imul(z ^ (z >>> 15), z | 1) >>> 0
    z ^= z + (Math.imul(z ^ (z >>> 7), z | 61) >>> 0)
    return ((z ^ (z >>> 14)) >>> 0) / 0x100000000
  }

  /** Integer in [min, max) */
  randInt(min: number, max: number): number {
    return Math.floor(this.next() * (max - min)) + min
  }

  /** Float in [min, max) */
  randFloat(min: number, max: number): number {
    return this.next() * (max - min) + min
  }

  /** Random element from array */
  choice<T>(arr: T[]): T {
    return arr[this.randInt(0, arr.length)]
  }

  /** Weighted random choice: weights need not sum to 1 */
  weightedChoice<T>(items: T[], weights: number[]): T {
    const total = weights.reduce((a, b) => a + b, 0)
    let r = this.next() * total
    for (let i = 0; i < items.length; i++) {
      r -= weights[i]
      if (r <= 0) return items[i]
    }
    return items[items.length - 1]
  }

  /** Exponential distribution — used for Poisson inter-arrival times */
  exponential(mean: number): number {
    return -mean * Math.log(1 - this.next())
  }

  /** Uniform noise in [-1, 1] */
  noise(): number {
    return this.next() * 2 - 1
  }

  /** Fork: create a child RNG seeded from this one's current state */
  fork(): SeededRNG {
    return new SeededRNG(this.randInt(0, 0xffffffff))
  }
}
