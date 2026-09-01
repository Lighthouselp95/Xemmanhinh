
class PCMProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.ring = null; this.wptr = 0; this.rptr = 0; this.filled = 0;
    this.port.onmessage = (e) => {
      if (e.data.type === 'init') {
        this.ring = e.data.ring; this.wptr = e.data.wptr; this.rptr = e.data.rptr; this.filled = e.data.filled;
      } else if (e.data.type === 'write') {
        const src = e.data.samples; const n = src.length;
        const ring = this.ring, cap = ring.length, w = Atomics.load(this.wptr, 0), r = Atomics.load(this.rptr, 0);
        let filled = (w - r + cap) % cap;
        for (let i = 0; i < n && filled < cap; i++) {
          ring[w] = src[i];
          w = (w + 1) % cap;
          filled++;
        }
        Atomics.store(this.wptr, 0, w);
        Atomics.store(this.filled, 0, filled);
      }
    };
  }
  process(outputs) {
    const out = outputs[0];
    const L = out[0], R = out[1];
    if (!this.ring) return true;
    const ring = this.ring, cap = ring.length, r = Atomics.load(this.rptr, 0);
    let filled = Atomics.load(this.filled, 0);
    const need = L.length;
    for (let i = 0; i < need; i += 2) {
      if (filled >= 2) {
        L[i/2] = ring[(r + i) % cap];
        R[i/2] = ring[(r + i + 1) % cap];
      } else { L[i/2] = 0; R[i/2] = 0; }
    }
    Atomics.store(this.rptr, 0, (r + need * 2) % cap);
    Atomics.store(this.filled, 0, Math.max(0, filled - need * 2));
    return true;
  }
}
registerProcessor('pcm-processor', PCMProcessor);
