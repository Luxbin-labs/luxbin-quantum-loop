#!/usr/bin/env python3
"""
LUXBIN QUANTUM PING-PONG

Two quantum computers play ping-pong with a LUXBIN message!

Computer A sends → Computer B responds → Computer A responds → ...

Watch the message evolve through quantum back-and-forth!
"""

from qiskit import QuantumCircuit
from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2
from qiskit.transpiler.preset_passmanagers import generate_preset_pass_manager
import numpy as np
import time
import os

TOKEN = os.environ.get('IBM_QUANTUM_TOKEN', 'YOUR_IBM_QUANTUM_TOKEN')

CHAR_WAVELENGTHS = {
    'A': 400.0, 'B': 403.9, 'C': 407.8, 'D': 411.7, 'E': 415.6,
    'F': 419.5, 'G': 423.4, 'H': 427.3, 'I': 431.2, 'J': 435.1,
    'K': 439.0, 'L': 442.9, 'M': 446.8, 'N': 450.6, 'O': 454.5,
    'P': 458.4, 'Q': 462.3, 'R': 466.2, 'S': 470.1, 'T': 474.0,
    'U': 477.9, 'V': 481.8, 'W': 485.7, 'X': 489.6, 'Y': 493.5,
    'Z': 497.4, ' ': 540.3,
}

def wavelength_to_char(wavelength):
    closest = min(CHAR_WAVELENGTHS.items(), key=lambda x: abs(x[1] - wavelength))
    return closest[0]

def create_ping_circuit(message, is_pong=False):
    """
    Create ping or pong circuit.

    Ping: Forward encoding
    Pong: Reversed encoding (like reflecting)
    """
    n_qubits = min(len(message), 5)
    qc = QuantumCircuit(n_qubits, n_qubits)

    # Encode message
    for i, char in enumerate(message[:n_qubits]):
        wavelength = CHAR_WAVELENGTHS.get(char.upper(), 540.3)
        theta = ((wavelength - 400) / 300) * np.pi

        qc.h(i)

        if is_pong:
            # Pong: Reverse direction
            qc.ry(-theta, i)  # Negative rotation
            qc.rz(theta, i)
        else:
            # Ping: Forward direction
            qc.ry(theta, i)
            qc.rz(-theta, i)

    # Entanglement pattern
    if is_pong:
        # Pong: Reverse entanglement
        for i in range(n_qubits - 1, 0, -1):
            qc.cx(i, i - 1)
    else:
        # Ping: Forward entanglement
        for i in range(n_qubits - 1):
            qc.cx(i, i + 1)

    # "Bounce" transformation
    for i in range(n_qubits):
        qc.t(i)  # Phase gate
        qc.h(i)

    qc.measure(range(n_qubits), range(n_qubits))
    return qc

def decode_response(counts):
    """Decode measurement to message."""
    sorted_counts = sorted(counts.items(), key=lambda x: -x[1])

    chars = []
    wavelengths = []

    for bitstring, count in sorted_counts[:5]:
        value = int(bitstring, 2)
        max_val = 2 ** len(bitstring) - 1
        wl = 400 + (value / max_val) * 300 if max_val > 0 else 550
        char = wavelength_to_char(wl)
        chars.append(char)
        wavelengths.append(wl)

    return ''.join(chars), np.mean(wavelengths)

def play_turn(backend, message, is_pong):
    """Play one turn of ping-pong."""
    qc = create_ping_circuit(message, is_pong)

    pm = generate_preset_pass_manager(backend=backend, optimization_level=1)
    transpiled = pm.run(qc)

    sampler = SamplerV2(backend)
    job = sampler.run([transpiled], shots=500)

    result = job.result()
    counts = result[0].data.c.get_counts()

    response, avg_wl = decode_response(counts)

    return {
        'backend': backend.name,
        'job_id': job.job_id(),
        'type': 'PONG' if is_pong else 'PING',
        'sent': message,
        'received': response,
        'wavelength': avg_wl,
        'counts': counts
    }

# =============================================================================
# MAIN GAME
# =============================================================================

print("=" * 70)
print("LUXBIN QUANTUM PING-PONG")
print("Two quantum computers rally a LUXBIN message!")
print("=" * 70)

# Connect
print("\nConnecting to IBM Quantum...")
service = QiskitRuntimeService(channel="ibm_quantum_platform", token=TOKEN)
backends = service.backends(operational=True, simulator=False)[:2]
print(f"Players: {backends[0].name} vs {backends[1].name}")

# Assign players
player_a = backends[0]
player_b = backends[1]

# Starting message
ball = "HELLO"
num_rallies = 4

print(f"\n🏓 STARTING BALL: '{ball}'")

print(f"\n{'='*70}")
print("GAME ON!")
print(f"{'='*70}")

rally_log = []
current_player = 0  # 0 = A, 1 = B

for rally in range(num_rallies):
    is_pong = (rally % 2 == 1)  # Alternate ping/pong
    backend = player_a if current_player == 0 else player_b
    player_name = "A" if current_player == 0 else "B"

    print(f"\n{'─'*70}")
    action = "PONG" if is_pong else "PING"
    print(f"RALLY {rally + 1}: Player {player_name} ({backend.name}) - {action}")
    print(f"{'─'*70}")

    print(f"🏓 Ball incoming: '{ball}'")

    start = time.time()
    result = play_turn(backend, ball, is_pong)
    elapsed = time.time() - start

    print(f"🏓 Ball returned: '{result['received']}' ({elapsed:.1f}s)")
    print(f"   Wavelength: {result['wavelength']:.1f}nm")
    print(f"   Job: {result['job_id']}")

    rally_log.append(result)

    # Ball becomes the response
    ball = result['received']

    # Switch player
    current_player = 1 - current_player

# =============================================================================
# RESULTS
# =============================================================================

print(f"\n{'='*70}")
print("GAME OVER!")
print(f"{'='*70}")

print(f"\nFinal ball: '{ball}'")
print(f"\nRally history:")
print("-" * 60)

for i, r in enumerate(rally_log):
    player = "A" if r['backend'] == player_a.name else "B"
    arrow = "──▶" if r['type'] == 'PING' else "◀──"
    print(f"  {i+1}. Player {player} ({r['type']}): '{r['sent']}' {arrow} '{r['received']}'")

# Visual game
print(f"\n{'='*70}")
print("VISUAL RALLY")
print(f"{'='*70}")

print(f"""
         Player A                                    Player B
    ┌─────────────────┐                        ┌─────────────────┐
    │  {player_a.name:^13}  │                        │  {player_b.name:^13}  │
    │                 │                        │                 │
    │    🏓 ──────────┼────────────────────────┼───────── 🏓     │
    │                 │                        │                 │
    └─────────────────┘                        └─────────────────┘
""")

print("Ball trajectory:")
print()

original = "HELLO"
trajectory = [original] + [r['received'] for r in rally_log]

for i, msg in enumerate(trajectory):
    if i == 0:
        side = "START"
    elif i % 2 == 1:
        side = f"A→B"
    else:
        side = f"B→A"

    spaces = "  " * (i * 3)
    if i < len(trajectory) - 1:
        print(f"    {spaces}'{msg}' ──╮")
        print(f"    {spaces}        │ {side}")
        print(f"    {spaces}        ╰──▶")
    else:
        print(f"    {spaces}'{msg}' (FINAL)")

# Wavelength bounce
print(f"\n{'='*70}")
print("WAVELENGTH BOUNCE PATTERN")
print(f"{'='*70}")

print("\n  400nm ────────────────────── 550nm ────────────────────── 700nm")

wls = [CHAR_WAVELENGTHS.get(trajectory[0][0].upper(), 540)]
wls.extend([r['wavelength'] for r in rally_log])

for i, wl in enumerate(wls):
    pos = int((wl - 400) / 300 * 55)
    if i == 0:
        label = "START"
    elif i % 2 == 1:
        label = f"A→B"
    else:
        label = f"B→A"

    bar = " " * pos + "●"
    print(f"  {bar} {wl:.0f}nm ({label})")

print(f"""
{'='*70}
ANALYSIS
{'='*70}

The quantum ping-pong shows:

1. MESSAGE EVOLUTION: '{original}' → '{ball}'
   Each quantum "hit" transforms the message

2. PING vs PONG:
   - PING: Forward rotation (ry +θ)
   - PONG: Reverse rotation (ry -θ)
   - Like a real ball bouncing!

3. WAVELENGTH DRIFT:
   Start: ~{wls[0]:.0f}nm
   End:   ~{wls[-1]:.0f}nm
   The "ball" shifted through the spectrum!

4. QUANTUM SIGNATURE:
   Each computer's hardware characteristics
   affect how the ball transforms.

This is quantum computers playing a game!
""")

print(f"\nAll job IDs:")
for r in rally_log:
    print(f"  {r['job_id']} ({r['backend']}, {r['type']})")
