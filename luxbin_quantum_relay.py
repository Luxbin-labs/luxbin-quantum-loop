#!/usr/bin/env python3
"""
LUXBIN QUANTUM RELAY RACE

A message passes through all 3 IBM quantum computers in sequence:
  Computer 1 → Computer 2 → Computer 3 → Back to you

Each computer transforms the message quantum-mechanically.
The final message shows the cumulative quantum evolution!
"""

from qiskit import QuantumCircuit
from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2
from qiskit.transpiler.preset_passmanagers import generate_preset_pass_manager
import numpy as np
import time
import os

TOKEN = os.environ.get('IBM_QUANTUM_TOKEN', 'YOUR_IBM_QUANTUM_TOKEN')

# LUXBIN mappings
CHAR_WAVELENGTHS = {
    'A': 400.0, 'B': 403.9, 'C': 407.8, 'D': 411.7, 'E': 415.6,
    'F': 419.5, 'G': 423.4, 'H': 427.3, 'I': 431.2, 'J': 435.1,
    'K': 439.0, 'L': 442.9, 'M': 446.8, 'N': 450.6, 'O': 454.5,
    'P': 458.4, 'Q': 462.3, 'R': 466.2, 'S': 470.1, 'T': 474.0,
    'U': 477.9, 'V': 481.8, 'W': 485.7, 'X': 489.6, 'Y': 493.5,
    'Z': 497.4, ' ': 540.3,
}

def wavelength_to_char(wavelength):
    """Find closest character for a wavelength."""
    closest = min(CHAR_WAVELENGTHS.items(), key=lambda x: abs(x[1] - wavelength))
    return closest[0]

def create_relay_circuit(message, leg_number):
    """
    Create circuit for one leg of the relay.

    Each leg adds its own quantum transformation based on leg number.
    """
    n_qubits = min(len(message), 5)
    qc = QuantumCircuit(n_qubits, n_qubits)

    # Encode message
    for i, char in enumerate(message[:n_qubits]):
        wavelength = CHAR_WAVELENGTHS.get(char.upper(), 540.3)
        theta = ((wavelength - 400) / 300) * 2 * np.pi

        qc.h(i)
        qc.ry(theta, i)

    # Leg-specific transformation (each computer adds its signature)
    if leg_number == 1:
        # First leg: Add phase shifts
        for i in range(n_qubits):
            qc.rz(np.pi / 4, i)
        # Entangle pairs
        for i in range(0, n_qubits - 1, 2):
            qc.cx(i, i + 1)

    elif leg_number == 2:
        # Second leg: Swap and rotate
        for i in range(n_qubits - 1):
            qc.swap(i, i + 1)
        for i in range(n_qubits):
            qc.ry(np.pi / 3, i)

    elif leg_number == 3:
        # Third leg: Full entanglement + interference
        for i in range(n_qubits - 1):
            qc.cx(i, i + 1)
        qc.cx(n_qubits - 1, 0)  # Close the loop
        for i in range(n_qubits):
            qc.h(i)

    # Final interference layer
    for i in range(n_qubits):
        qc.h(i)

    qc.measure(range(n_qubits), range(n_qubits))
    return qc

def decode_relay_result(counts):
    """Decode quantum measurement to LUXBIN message."""
    sorted_counts = sorted(counts.items(), key=lambda x: -x[1])

    # Take top outcomes and convert to wavelengths
    decoded_chars = []
    for bitstring, count in sorted_counts[:5]:
        value = int(bitstring, 2)
        max_val = 2 ** len(bitstring) - 1
        wavelength = 400 + (value / max_val) * 300 if max_val > 0 else 550
        char = wavelength_to_char(wavelength)
        decoded_chars.append((char, wavelength, count))

    # Build message from most common outcomes
    message = ''.join([c[0] for c in decoded_chars])
    avg_wavelength = np.mean([c[1] for c in decoded_chars])

    return message, avg_wavelength, decoded_chars

def run_relay_leg(backend, message, leg_number):
    """Run one leg of the relay race."""
    qc = create_relay_circuit(message, leg_number)

    pm = generate_preset_pass_manager(backend=backend, optimization_level=1)
    transpiled = pm.run(qc)

    sampler = SamplerV2(backend)
    job = sampler.run([transpiled], shots=500)

    result = job.result()
    counts = result[0].data.c.get_counts()

    new_message, avg_wavelength, decoded = decode_relay_result(counts)

    return {
        'backend': backend.name,
        'job_id': job.job_id(),
        'leg': leg_number,
        'input': message,
        'output': new_message,
        'wavelength': avg_wavelength,
        'decoded': decoded,
        'counts': counts
    }

# =============================================================================
# MAIN RELAY RACE
# =============================================================================

print("=" * 70)
print("LUXBIN QUANTUM RELAY RACE")
print("Message passes through 3 quantum computers in sequence")
print("=" * 70)

# Connect
print("\nConnecting to IBM Quantum Network...")
service = QiskitRuntimeService(channel="ibm_quantum_platform", token=TOKEN)
backends = service.backends(operational=True, simulator=False)[:3]
print(f"Relay stations: {[b.name for b in backends]}")

# Starting message
current_message = "RELAY"
print(f"\n🏁 STARTING MESSAGE: '{current_message}'")

relay_log = []
total_start = time.time()

print(f"\n{'='*70}")
print("RELAY RACE IN PROGRESS")
print(f"{'='*70}")

for leg, backend in enumerate(backends, 1):
    print(f"\n{'─'*70}")
    print(f"LEG {leg}: {backend.name}")
    print(f"{'─'*70}")

    print(f"📤 Passing: '{current_message}'")
    wavelengths = [CHAR_WAVELENGTHS.get(c.upper(), 540) for c in current_message[:5]]
    print(f"   Wavelengths: {[f'{w:.0f}nm' for w in wavelengths]}")

    start = time.time()
    result = run_relay_leg(backend, current_message, leg)
    elapsed = time.time() - start

    print(f"\n📥 Received: '{result['output']}' (in {elapsed:.1f}s)")
    print(f"   Avg wavelength: {result['wavelength']:.1f}nm")
    print(f"   Job: {result['job_id']}")

    print(f"\n   Top outcomes:")
    for char, wl, count in result['decoded'][:3]:
        print(f"     '{char}' ({wl:.0f}nm): {count} shots")

    relay_log.append(result)
    current_message = result['output']

total_elapsed = time.time() - total_start

# =============================================================================
# RESULTS
# =============================================================================

print(f"\n{'='*70}")
print("RELAY RACE COMPLETE!")
print(f"{'='*70}")

print(f"\nTotal time: {total_elapsed:.1f}s")
print(f"\nMessage evolution:")
print("-" * 50)

original = "RELAY"
print(f"  START:  '{original}'")
for r in relay_log:
    arrow = "───▶"
    print(f"  {r['backend']:15} {arrow} '{r['output']}'")

print(f"\n  FINAL:  '{current_message}'")

# Visualize the relay
print(f"\n{'='*70}")
print("RELAY VISUALIZATION")
print(f"{'='*70}")

print("""
    ┌─────────────┐
    │   START     │
    │   "RELAY"   │
    └──────┬──────┘
           │
           ▼
    ┌─────────────┐     LEG 1
    │  """ + f"{backends[0].name:^9}" + """  │ ──────────▶ Phase shifts + Entanglement
    └──────┬──────┘
           │
           ▼
    ┌─────────────┐     LEG 2
    │  """ + f"{backends[1].name:^9}" + """  │ ──────────▶ Swap + Rotation
    └──────┬──────┘
           │
           ▼
    ┌─────────────┐     LEG 3
    │  """ + f"{backends[2].name:^9}" + """  │ ──────────▶ Full entanglement + Interference
    └──────┬──────┘
           │
           ▼
    ┌─────────────┐
    │   FINISH    │
    │   \"""" + current_message[:5] + """\"   │
    └─────────────┘
""")

# Wavelength evolution
print(f"\n{'='*70}")
print("WAVELENGTH EVOLUTION")
print(f"{'='*70}")

print("\n  400nm ────────────── 550nm ────────────── 700nm")
print("  Violet    Blue    Cyan   Green   Yellow  Orange  Red")
print("  │                   │                      │")

for r in relay_log:
    wl = r['wavelength']
    pos = int((wl - 400) / 300 * 50)
    bar = " " * pos + "●"
    print(f"  {bar} {wl:.0f}nm ({r['backend']})")

print(f"""
{'='*70}
WHAT HAPPENED:
{'='*70}

Each quantum computer applied a DIFFERENT transformation:

  LEG 1 ({backends[0].name}):
    - Added phase shifts (RZ gates)
    - Created pairwise entanglement
    - Changed the interference pattern

  LEG 2 ({backends[1].name}):
    - Swapped qubit positions
    - Applied Y-rotations
    - Scrambled the order

  LEG 3 ({backends[2].name}):
    - Created circular entanglement
    - Applied final interference (Hadamards)
    - Collapsed to new measurement

The message evolved: '{original}' → '{current_message}'

This shows REAL quantum processing across multiple computers!
""")

print(f"\nAll job IDs:")
for r in relay_log:
    print(f"  {r['job_id']} ({r['backend']}, leg {r['leg']})")
