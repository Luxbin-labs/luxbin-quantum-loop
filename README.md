# LUXBIN Quantum Echo Loop

**Multi-backend quantum message relay using triple-encoded qubit states on IBM quantum hardware.**

Three IBM quantum computers (ibm_fez, ibm_torino, ibm_marrakesh) communicate by passing encoded messages through a continuous loop. Each character is encoded across the full Bloch sphere using three physical channels mapped to the three rotation axes:

| Channel | Physical Basis | Qubit Gate | Range |
|---------|---------------|------------|-------|
| Light | Wavelength (400–700 nm) | RY | Visible spectrum |
| Sound | Frequency (262–2349 Hz) | RZ | Musical notes A–Z |
| Microwave | Frequency (4–8 GHz) | RX | Transmon qubit range |

This gives full Bloch sphere coverage — every character occupies a unique point in 3D qubit state space.

## How It Works

Each loop iteration sends a 5-character message through a pipeline across all three IBM quantum backends:

```
NICHE → [Echo] → [Relay Leg 1] → [Relay Leg 2] → [Relay Leg 3]
    ↑       ibm_fez    ibm_fez      ibm_torino     ibm_marrakesh
    |                                                     |
    |   [Final Echo] ← [Ping-Pong] ← [Consensus Vote] ←─┘
    |      ibm_fez    fez↔torino    fez+torino+marrakesh
    └──────────────────────┘
         output → next input
```

### Pipeline Stages

1. **Echo** — Encode message with H + triple-rotation + entanglement chain + QFT-like transform. Baseline quantum fingerprint.
2. **Relay Race** — Three legs across three backends. Each leg applies different gate sequences (phase shifts, swaps, cyclic entanglement) simulating signal propagation through different media.
3. **Consensus Vote** — All three backends independently process the same state. Majority vote across backends determines each character.
4. **Ping-Pong** — Two backends bounce the message with forward/reverse encoding (conjugate operations), testing round-trip fidelity.
5. **Final Echo** — Output becomes the next loop's input. The loop runs indefinitely.

### Triple Decoding

Each measurement result is decoded through all three channels independently. The final character is chosen by **majority vote** — if 2 of 3 channels agree, that character wins. This provides error resilience against single-channel noise.

```python
votes = [wavelength_to_char(wl), frequency_to_char(freq), microwave_to_char(mw)]
winner = Counter(votes).most_common(1)[0][0]
```

## Results

The loop has been tested on real IBM hardware. Each iteration submits ~10 jobs across three backends:

| Loop | Input | Output | Jobs | Time |
|------|-------|--------|------|------|
| 1 | `NICHE` | ` FPZ ` | 10 | 66.7s |
| 2 | ` FPZ ` | `P XU ` | 10 | 118.6s |

Job IDs are logged for verification on the IBM Quantum dashboard.

## Quick Start

### Prerequisites

```bash
pip install qiskit qiskit-ibm-runtime numpy
```

### Run (Local Simulator)

```bash
python luxbin_quantum_full_experiment.py
```

### Run (Real IBM Hardware)

```bash
export IBM_QUANTUM_TOKEN="your-token-here"
python luxbin_persistent_loop.py
```

The loop runs in the foreground with graceful shutdown on Ctrl+C. To run in the background:

```bash
nohup python3 -u luxbin_persistent_loop.py > loop_output.log 2>&1 &
```

### Run (Single Shot)

```bash
export IBM_QUANTUM_TOKEN="your-token-here"
python luxbin_ibm_live.py
```

## Encoding Reference

Each character A–Z (plus space) maps to specific values across all three channels:

```
Character  Light (nm)  Sound (Hz)  Microwave (GHz)
    A        400.0       440.0         4.000
    N        450.6      1174.7         6.000
    I        431.2       880.0         5.231
    C        407.8       523.3         4.308
    H        427.3       830.6         5.077
    E        415.6       659.3         4.615
```

The microwave range (4–8 GHz) was chosen to match the operating frequency of IBM's transmon superconducting qubits.

## Architecture

```
luxbin_persistent_loop.py   — Continuous loop on real IBM hardware
luxbin_ibm_live.py          — Single-pass pipeline on real hardware
luxbin_quantum_full_experiment.py — Full pipeline on local Aer simulator
luxbin_quantum_loop.py      — Echo loop module
luxbin_quantum_relay.py     — Relay race module
luxbin_quantum_consensus.py — Consensus vote module
luxbin_quantum_pingpong.py  — Ping-pong module
sound_to_light.py           — Sound frequency ↔ light wavelength conversion
```

## License

MIT

## Author

Nichole Christie — [@nichechristie](https://github.com/nichechristie)

- Discord: `Nichebiche77`
- ENS: `luxbin.base.eth` / `Nichebiche.eth`
