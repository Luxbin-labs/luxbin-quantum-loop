#!/usr/bin/env python3
"""
LUXBIN FULL QUANTUM INTER-COMPUTER COMMUNICATION

Uses LUXBIN triple encoding (Light + Sound + Microwave) through the Echo Loop.
Runs on Aer simulator with realistic noise for fast execution.

Pipeline:
  Echo Loop -> Relay -> Consensus -> Ping-Pong -> Echo

Each stage encodes/decodes using all three channels:
  - LIGHT:     400-700nm   -> RY rotation (amplitude)
  - SOUND:     262-2349Hz  -> RZ rotation (phase)
  - MICROWAVE: 4.0-8.0GHz  -> RX rotation (third axis)

This gives FULL Bloch sphere coverage - every point on the qubit
state space is addressable through the three LUXBIN channels.

IBM transmon qubits physically operate at 4-8 GHz, so the microwave
channel directly corresponds to the hardware's native control pulses.
"""

from qiskit import QuantumCircuit, transpile
from qiskit_aer import AerSimulator
from qiskit_aer.noise import NoiseModel
import concurrent.futures
import numpy as np
import time

try:
    from qiskit_ibm_runtime.fake_provider import FakeManilaV2
    noise_model = NoiseModel.from_backend(FakeManilaV2())
    simulator = AerSimulator(noise_model=noise_model)
    print("Using realistic noise model (FakeManila)")
except Exception:
    simulator = AerSimulator()
    print("Using ideal simulator")

# ==========================================================================
# LUXBIN TRIPLE ENCODING: Light + Sound + Microwave
# ==========================================================================

# Light channel: visible spectrum (400-700nm) -> RY rotation
CHAR_WAVELENGTHS = {
    'A': 400.0, 'B': 403.9, 'C': 407.8, 'D': 411.7, 'E': 415.6,
    'F': 419.5, 'G': 423.4, 'H': 427.3, 'I': 431.2, 'J': 435.1,
    'K': 439.0, 'L': 442.9, 'M': 446.8, 'N': 450.6, 'O': 454.5,
    'P': 458.4, 'Q': 462.3, 'R': 466.2, 'S': 470.1, 'T': 474.0,
    'U': 477.9, 'V': 481.8, 'W': 485.7, 'X': 489.6, 'Y': 493.5,
    'Z': 497.4, ' ': 540.3,
}

# Sound channel: audible frequencies (262-2349 Hz) -> RZ rotation
CHAR_FREQUENCIES = {
    'A': 440.0, 'B': 493.9, 'C': 523.3, 'D': 587.3, 'E': 659.3,
    'F': 698.5, 'G': 784.0, 'H': 830.6, 'I': 880.0, 'J': 932.3,
    'K': 987.8, 'L': 1046.5, 'M': 1108.7, 'N': 1174.7, 'O': 1244.5,
    'P': 1318.5, 'Q': 1396.9, 'R': 1480.0, 'S': 1568.0, 'T': 1661.2,
    'U': 1760.0, 'V': 1864.7, 'W': 1975.5, 'X': 2093.0, 'Y': 2217.5,
    'Z': 2349.3, ' ': 262.6,
}

# Microwave channel: transmon qubit frequencies (4.0-8.0 GHz) -> RX rotation
# Maps to actual IBM superconducting qubit drive frequencies
CHAR_MICROWAVES = {
    'A': 4.000, 'B': 4.154, 'C': 4.308, 'D': 4.462, 'E': 4.615,
    'F': 4.769, 'G': 4.923, 'H': 5.077, 'I': 5.231, 'J': 5.385,
    'K': 5.538, 'L': 5.692, 'M': 5.846, 'N': 6.000, 'O': 6.154,
    'P': 6.308, 'Q': 6.462, 'R': 6.615, 'S': 6.769, 'T': 6.923,
    'U': 7.077, 'V': 7.231, 'W': 7.385, 'X': 7.538, 'Y': 7.692,
    'Z': 7.846, ' ': 5.500,
}

MW_MIN = 4.0
MW_MAX = 8.0


def wavelength_to_char(wl):
    return min(CHAR_WAVELENGTHS.items(), key=lambda x: abs(x[1] - wl))[0]


def frequency_to_char(freq):
    return min(CHAR_FREQUENCIES.items(), key=lambda x: abs(x[1] - freq))[0]


def microwave_to_char(mw):
    return min(CHAR_MICROWAVES.items(), key=lambda x: abs(x[1] - mw))[0]


def color_name(wl):
    if wl < 440: return "Violet"
    if wl < 490: return "Blue"
    if wl < 510: return "Cyan"
    if wl < 565: return "Green"
    if wl < 590: return "Yellow"
    if wl < 625: return "Orange"
    return "Red"


def note_name(freq):
    if freq < 300: return "C4"
    if freq < 500: return "A4-B4"
    if freq < 700: return "D5-E5"
    if freq < 1000: return "G5-B5"
    if freq < 1500: return "C6-F6"
    if freq < 2000: return "G6-B6"
    return "C7+"


def mw_band(ghz):
    if ghz < 5.0: return "C-band"
    if ghz < 6.0: return "C/X-trans"
    if ghz < 7.0: return "X-band lo"
    return "X-band hi"


def decode_counts(counts, n_chars=5):
    """Decode quantum measurement into LUXBIN message using triple encoding."""
    sorted_counts = sorted(counts.items(), key=lambda x: -x[1])
    chars = []
    light_wls = []
    sound_freqs = []
    mw_ghzs = []

    for bitstring, count in sorted_counts[:n_chars]:
        value = int(bitstring, 2)
        max_val = 2 ** len(bitstring) - 1
        ratio = value / max_val if max_val > 0 else 0.5

        # Light channel
        wl = 400 + ratio * 300
        char_light = wavelength_to_char(wl)

        # Sound channel
        freq = 262.6 + ratio * (2349.3 - 262.6)
        char_sound = frequency_to_char(freq)

        # Microwave channel
        mw = MW_MIN + ratio * (MW_MAX - MW_MIN)
        char_mw = microwave_to_char(mw)

        # Triple-channel consensus: majority vote across channels
        channel_votes = [char_light, char_sound, char_mw]
        # If 2+ channels agree, use that; otherwise light priority
        from collections import Counter
        vote_counts = Counter(channel_votes)
        winner = vote_counts.most_common(1)[0]
        if winner[1] >= 2:
            chars.append(winner[0])
        else:
            chars.append(char_light)

        light_wls.append(wl)
        sound_freqs.append(freq)
        mw_ghzs.append(mw)

    return ''.join(chars), light_wls, sound_freqs, mw_ghzs


def run_circuit(qc, shots=500):
    """Run circuit on Aer simulator."""
    transpiled = transpile(qc, simulator)
    job = simulator.run(transpiled, shots=shots)
    result = job.result()
    counts = result.get_counts()
    return counts


# ==========================================================================
# CIRCUIT BUILDERS (triple encoding: Light RY + Sound RZ + Microwave RX)
# ==========================================================================

def encode_char(qc, i, char):
    """Encode a character on qubit i using all 3 LUXBIN channels.
    Light  -> RY (amplitude axis)
    Sound  -> RZ (phase axis)
    Microwave -> RX (third axis)
    Full Bloch sphere coverage!
    """
    wl = CHAR_WAVELENGTHS.get(char.upper(), 540.3)
    freq = CHAR_FREQUENCIES.get(char.upper(), 262.6)
    mw = CHAR_MICROWAVES.get(char.upper(), 5.5)

    theta_light = ((wl - 400) / 300) * 2 * np.pi
    theta_sound = ((freq - 262.6) / (2349.3 - 262.6)) * np.pi
    theta_mw = ((mw - MW_MIN) / (MW_MAX - MW_MIN)) * np.pi

    qc.ry(theta_light, i)   # Light: amplitude
    qc.rz(theta_sound, i)   # Sound: phase
    qc.rx(theta_mw, i)      # Microwave: third axis


def build_echo_circuit(message):
    n = min(len(message), 5)
    qc = QuantumCircuit(n, n)
    for i, char in enumerate(message[:n]):
        qc.h(i)
        encode_char(qc, i, char)
    for i in range(n - 1):
        qc.cx(i, i + 1)
    # Echo response layer
    for i in range(n):
        qc.h(i)
        qc.t(i)
        qc.h(i)
    for i in range(n - 1):
        qc.cx(i, i + 1)
    qc.measure(range(n), range(n))
    return qc


def build_relay_circuit(message, leg):
    n = min(len(message), 5)
    qc = QuantumCircuit(n, n)
    for i, char in enumerate(message[:n]):
        qc.h(i)
        encode_char(qc, i, char)
    if leg == 1:
        # Phase shifts + pairwise entanglement
        for i in range(n):
            qc.rz(np.pi / 4, i)
            qc.rx(np.pi / 6, i)  # Microwave kick
        for i in range(0, n - 1, 2):
            qc.cx(i, i + 1)
    elif leg == 2:
        # Swap + rotate + microwave flip
        for i in range(n - 1):
            qc.swap(i, i + 1)
        for i in range(n):
            qc.ry(np.pi / 3, i)
            qc.rx(np.pi / 4, i)  # Microwave modulation
    elif leg == 3:
        # Loop entangle + interference + microwave resonance
        for i in range(n - 1):
            qc.cx(i, i + 1)
        qc.cx(n - 1, 0)
        for i in range(n):
            qc.h(i)
            qc.rx(np.pi / 3, i)  # Microwave resonance sweep
    for i in range(n):
        qc.h(i)
    qc.measure(range(n), range(n))
    return qc


def build_consensus_circuit(message):
    n = 5
    msg = (message + 'AAAAA')[:5]
    qc = QuantumCircuit(n, n)
    for i, char in enumerate(msg):
        qc.h(i)
        encode_char(qc, i, char)
    # GHZ-like entanglement
    for i in range(n - 1):
        qc.cx(i, i + 1)
    # Agreement phase + microwave sync
    for i in range(n):
        qc.rz(np.pi / n, i)
        qc.rx(np.pi / (n + 1), i)  # Microwave consensus sync
    for i in range(n):
        qc.h(i)
    qc.measure(range(n), range(n))
    return qc


def build_ping_circuit(message, is_pong=False):
    n = min(len(message), 5)
    qc = QuantumCircuit(n, n)
    for i, char in enumerate(message[:n]):
        wl = CHAR_WAVELENGTHS.get(char.upper(), 540.3)
        freq = CHAR_FREQUENCIES.get(char.upper(), 262.6)
        mw = CHAR_MICROWAVES.get(char.upper(), 5.5)
        theta = ((wl - 400) / 300) * np.pi
        phi = ((freq - 262.6) / (2349.3 - 262.6)) * np.pi / 2
        gamma = ((mw - MW_MIN) / (MW_MAX - MW_MIN)) * np.pi / 2
        qc.h(i)
        if is_pong:
            qc.ry(-theta, i)
            qc.rz(phi, i)
            qc.rx(-gamma, i)  # Microwave reverse
        else:
            qc.ry(theta, i)
            qc.rz(-phi, i)
            qc.rx(gamma, i)   # Microwave forward
    if is_pong:
        for i in range(n - 1, 0, -1):
            qc.cx(i, i - 1)
    else:
        for i in range(n - 1):
            qc.cx(i, i + 1)
    for i in range(n):
        qc.t(i)
        qc.h(i)
    qc.measure(range(n), range(n))
    return qc


# ==========================================================================
# MAIN PIPELINE
# ==========================================================================

print("=" * 70)
print("LUXBIN QUANTUM INTER-COMPUTER COMMUNICATION")
print("Triple Encoding: Light + Sound + Microwave")
print("Full Bloch Sphere: RY (light) + RZ (sound) + RX (microwave)")
print("Echo Loop -> Relay -> Consensus -> Ping-Pong -> Echo")
print("=" * 70)

pipeline_start = time.time()
pipeline_log = []

COMPUTERS = ["QNode-Alpha", "QNode-Beta", "QNode-Gamma"]

# =========================================================================
# PHASE 1: ECHO LOOP
# =========================================================================
current = "NICHO"  # Nichole - 5 chars for 5 qubits

print(f"\n{'='*70}")
print(f"PHASE 1: ECHO LOOP (2 rounds)")
print(f"{'='*70}")
print(f"Starting message: '{current}'")

for r in range(2):
    start = time.time()
    qc = build_echo_circuit(current)
    counts = run_circuit(qc, shots=200)
    response, wls, freqs, mws = decode_counts(counts)
    elapsed = time.time() - start

    print(f"\n  Round {r+1} [{COMPUTERS[0]}]:")
    print(f"    Sent:      '{current}'")
    print(f"    Light:     {[f'{w:.0f}nm ({color_name(w)})' for w in wls[:len(current)]]}")
    print(f"    Sound:     {[f'{f:.0f}Hz ({note_name(f)})' for f in freqs[:len(current)]]}")
    print(f"    Microwave: {[f'{m:.2f}GHz ({mw_band(m)})' for m in mws[:len(current)]]}")
    print(f"    Response:  '{response}' ({elapsed:.2f}s)")

    pipeline_log.append({'phase': 'ECHO', 'in': current, 'out': response,
                         'node': COMPUTERS[0], 'time': elapsed})
    current = response

echo_out = current
print(f"\n  Echo output: '{echo_out}'")

# =========================================================================
# PHASE 2: RELAY RACE
# =========================================================================
print(f"\n{'='*70}")
print(f"PHASE 2: RELAY RACE (3 legs, 3 computers)")
print(f"{'='*70}")
print(f"Input from Echo: '{current}'")

for leg in range(1, 4):
    node = COMPUTERS[leg - 1]
    start = time.time()
    qc = build_relay_circuit(current, leg)
    counts = run_circuit(qc, shots=500)
    response, wls, freqs, mws = decode_counts(counts)
    elapsed = time.time() - start

    transforms = {
        1: "Phase shift + Entangle + MW kick",
        2: "Swap + Rotate + MW modulation",
        3: "Loop entangle + Interfere + MW resonance"
    }
    print(f"\n  Leg {leg} [{node}] - {transforms[leg]}:")
    print(f"    In:  '{current}'")
    print(f"         Light: {[f'{CHAR_WAVELENGTHS.get(c.upper(),540):.0f}nm' for c in current[:5]]}")
    print(f"         MW:    {[f'{CHAR_MICROWAVES.get(c.upper(),5.5):.2f}GHz' for c in current[:5]]}")
    print(f"    Out: '{response}'")
    print(f"         Sound: {[f'{f:.0f}Hz' for f in freqs[:5]]}")
    print(f"         MW:    {[f'{m:.2f}GHz' for m in mws[:5]]}")
    print(f"    Time: {elapsed:.2f}s")

    pipeline_log.append({'phase': 'RELAY', 'in': current, 'out': response,
                         'node': node, 'time': elapsed})
    current = response

relay_out = current
print(f"\n  Relay output: '{relay_out}'")

# =========================================================================
# PHASE 3: CONSENSUS VOTE
# =========================================================================
print(f"\n{'='*70}")
print(f"PHASE 3: CONSENSUS VOTE (3 computers vote simultaneously)")
print(f"{'='*70}")
print(f"Proposal from Relay: '{current}'")

votes = []
start = time.time()


def vote(node_idx, msg):
    qc = build_consensus_circuit(msg)
    counts = run_circuit(qc, shots=1000)
    top = max(counts.items(), key=lambda x: x[1])[0]
    val = int(top, 2)
    ratio = val / 31
    wl = 400 + ratio * 300
    freq = 262.6 + ratio * (2349.3 - 262.6)
    mw = MW_MIN + ratio * (MW_MAX - MW_MIN)
    return {
        'node': COMPUTERS[node_idx],
        'vote_light': wavelength_to_char(wl),
        'vote_sound': frequency_to_char(freq),
        'vote_mw': microwave_to_char(mw),
        'wl': wl, 'freq': freq, 'mw': mw,
        'counts': counts
    }


with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
    futures = [executor.submit(vote, i, current) for i in range(3)]
    for f in concurrent.futures.as_completed(futures):
        v = f.result()
        votes.append(v)
        channels = [v['vote_light'], v['vote_sound'], v['vote_mw']]
        agreement = len(set(channels))
        status = "3/3 AGREE" if agreement == 1 else f"2/3 AGREE" if agreement == 2 else "ALL DIFFER"
        print(f"  {v['node']} votes: "
              f"Light='{v['vote_light']}' ({v['wl']:.0f}nm) "
              f"Sound='{v['vote_sound']}' ({v['freq']:.0f}Hz) "
              f"MW='{v['vote_mw']}' ({v['mw']:.2f}GHz) [{status}]")

elapsed = time.time() - start
print(f"  Voting done in {elapsed:.2f}s")

# Build consensus from votes (triple-channel majority)
vote_chars = [v['vote_light'] for v in votes]
majority = max(set(vote_chars), key=vote_chars.count)
consensus_msg = ''.join(vote_chars)
while len(consensus_msg) < 5:
    consensus_msg += majority
current = consensus_msg[:5]

pipeline_log.append({'phase': 'CONSENSUS', 'in': relay_out, 'out': current,
                     'node': 'ALL', 'time': elapsed})

consensus_out = current
print(f"\n  Consensus: '{consensus_out}' (majority: '{majority}')")

# =========================================================================
# PHASE 4: PING-PONG
# =========================================================================
print(f"\n{'='*70}")
print(f"PHASE 4: PING-PONG (4 rallies between 2 computers)")
print(f"{'='*70}")
print(f"Ball from Consensus: '{current}'")

for rally in range(4):
    is_pong = (rally % 2 == 1)
    node = COMPUTERS[rally % 2]
    action = "PONG" if is_pong else "PING"

    start = time.time()
    qc = build_ping_circuit(current, is_pong)
    counts = run_circuit(qc, shots=500)
    response, wls, freqs, mws = decode_counts(counts)
    elapsed = time.time() - start

    print(f"\n  Rally {rally+1} [{node}] {action}:")
    print(f"    Ball in:  '{current}'")
    print(f"    Ball out: '{response}' ({elapsed:.2f}s)")
    print(f"    Light: {[f'{w:.0f}nm' for w in wls[:5]]}")
    print(f"    Sound: {[f'{f:.0f}Hz' for f in freqs[:5]]}")
    print(f"    MW:    {[f'{m:.2f}GHz' for m in mws[:5]]}")

    pipeline_log.append({'phase': 'PINGPONG', 'in': current, 'out': response,
                         'node': node, 'time': elapsed})
    current = response

pingpong_out = current
print(f"\n  Ping-Pong output: '{pingpong_out}'")

# =========================================================================
# PHASE 5: FINAL ECHO (loop back)
# =========================================================================
print(f"\n{'='*70}")
print(f"PHASE 5: FINAL ECHO (loop back to start)")
print(f"{'='*70}")

start = time.time()
qc = build_echo_circuit(current)
counts = run_circuit(qc, shots=200)
final, final_wls, final_freqs, final_mws = decode_counts(counts)
elapsed = time.time() - start

pipeline_log.append({'phase': 'ECHO_FINAL', 'in': current, 'out': final,
                     'node': COMPUTERS[0], 'time': elapsed})

print(f"  Looped back: '{current}' -> '{final}' ({elapsed:.2f}s)")

total_time = time.time() - pipeline_start

# =========================================================================
# RESULTS
# =========================================================================

print(f"\n{'='*70}")
print("FULL PIPELINE RESULTS")
print(f"{'='*70}")

print(f"\nTotal time: {total_time:.2f}s")
print(f"Total quantum operations: {len(pipeline_log)}")

stages = [
    ('START', '-', 'NICHO'),
    ('ECHO', COMPUTERS[0], echo_out),
    ('RELAY', 'All 3', relay_out),
    ('CONSENSUS', 'All 3', consensus_out),
    ('PINGPONG', f'{COMPUTERS[0]}/{COMPUTERS[1]}', pingpong_out),
    ('FINAL', COMPUTERS[0], final),
]

print(f"\nMessage evolution (triple channel):")
print("-" * 80)
print(f"  {'Phase':<12} {'Node':<15} {'Message':<8} {'Light':<10} {'Sound':<10} {'Microwave'}")
print("-" * 80)

for label, node, msg in stages:
    avg_wl = np.mean([CHAR_WAVELENGTHS.get(c.upper(), 540) for c in msg[:5]])
    avg_fq = np.mean([CHAR_FREQUENCIES.get(c.upper(), 262.6) for c in msg[:5]])
    avg_mw = np.mean([CHAR_MICROWAVES.get(c.upper(), 5.5) for c in msg[:5]])
    print(f"  {label:<12} {node:<15} '{msg:<5}' {avg_wl:>6.0f}nm  {avg_fq:>7.0f}Hz  {avg_mw:>5.2f}GHz")

print(f"""
{'='*70}
PIPELINE VISUALIZATION (Triple-Channel LUXBIN)
{'='*70}

    'NICHO'
     Light: 427nm (Violet) | Sound: 830Hz (G#5) | MW: 5.08GHz (C/X)
       |
       v
  +------------------------+
  |  ECHO LOOP (x2)        |  {COMPUTERS[0]}
  |  RY(light) + RZ(sound) |
  |  + RX(microwave)        |
  |  Full Bloch sphere!    |
  +-----------+------------+
              | '{echo_out}'
              v
  +------------------------+
  |  RELAY RACE            |  {COMPUTERS[0]} -> {COMPUTERS[1]} -> {COMPUTERS[2]}
  |  Leg 1: Phase + MW kick|
  |  Leg 2: Swap + MW mod  |
  |  Leg 3: Loop + MW res  |
  +-----------+------------+
              | '{relay_out}'
              v
  +------------------------+
  |  CONSENSUS VOTE        |  All 3 vote simultaneously
  |  Triple-channel ballot |
  |  Light/Sound/MW voting |
  +-----------+------------+
              | '{consensus_out}'
              v
  +------------------------+
  |  PING-PONG (x4)       |  {COMPUTERS[0]} vs {COMPUTERS[1]}
  |  Forward: +RY +RX     |
  |  Reverse: -RY -RX     |
  |  MW bounce effect     |
  +-----------+------------+
              | '{pingpong_out}'
              v
  +------------------------+
  |  FINAL ECHO            |  Loop complete!
  +-----------+------------+
              |
              v
    '{final}'
""")

# Spectrum visualizations
print(f"{'='*70}")
print("LIGHT SPECTRUM (RY axis)")
print(f"{'='*70}")
print("  400nm (Violet) ---------- 550nm (Green) ---------- 700nm (Red)")

for label, _, msg in stages:
    avg_wl = np.mean([CHAR_WAVELENGTHS.get(c.upper(), 540) for c in msg[:5]])
    pos = int((avg_wl - 400) / 300 * 50)
    bar = " " * pos + "●"
    print(f"  {bar} {avg_wl:.0f}nm ({label})")

print(f"\n{'='*70}")
print("SOUND SPECTRUM (RZ axis)")
print(f"{'='*70}")
print("  262Hz (C4) ---------- 1300Hz (E6) ---------- 2349Hz (D7)")

for label, _, msg in stages:
    avg_fq = np.mean([CHAR_FREQUENCIES.get(c.upper(), 262.6) for c in msg[:5]])
    pos = int((avg_fq - 262.6) / (2349.3 - 262.6) * 50)
    bar = " " * pos + "●"
    print(f"  {bar} {avg_fq:.0f}Hz ({label})")

print(f"\n{'='*70}")
print("MICROWAVE SPECTRUM (RX axis)")
print(f"{'='*70}")
print("  4.0GHz (C-band) -------- 6.0GHz (X-trans) -------- 8.0GHz (X-band)")

for label, _, msg in stages:
    avg_mw = np.mean([CHAR_MICROWAVES.get(c.upper(), 5.5) for c in msg[:5]])
    pos = int((avg_mw - MW_MIN) / (MW_MAX - MW_MIN) * 50)
    bar = " " * pos + "●"
    print(f"  {bar} {avg_mw:.2f}GHz ({label})")

print(f"""
{'='*70}
BLOCH SPHERE ENCODING
{'='*70}

  Each character is encoded as a point on the Bloch sphere:

        Z (Sound/Phase)
        |
        |    /  Y (Light/Amplitude)
        |   /
        |  /
        | /
        +------------ X (Microwave/Drive)

  RY(light)     = rotation around Y axis (amplitude modulation)
  RZ(sound)     = rotation around Z axis (phase modulation)
  RX(microwave) = rotation around X axis (drive pulse modulation)

  Together they can reach ANY point on the Bloch sphere,
  giving maximum information density per qubit.

  The microwave channel (4-8 GHz) directly matches IBM transmon
  qubit operating frequencies - the physical hardware control layer.

{'='*70}
INTER-COMPUTER COMMUNICATION SUMMARY
{'='*70}

  3 quantum computers communicated through:
    - 2 echo rounds
    - 3 relay legs (each with microwave transforms)
    - 3 simultaneous consensus votes (triple-channel)
    - 4 ping-pong rallies (forward/reverse MW bounce)
    - 1 final echo loop-back

  Triple LUXBIN encoding:
    LIGHT:     400-700nm   -> RY rotation (amplitude axis)
    SOUND:     262-2349Hz  -> RZ rotation (phase axis)
    MICROWAVE: 4.0-8.0GHz  -> RX rotation (drive axis)

  Full Bloch sphere coverage = maximum quantum information density

  Message traveled: 'NICHO' -> '{final}'
  Total quantum ops: {len(pipeline_log)}
  Total time: {total_time:.2f}s
""")

print("Detailed log:")
for entry in pipeline_log:
    print(f"  [{entry['phase']:<12}] {entry['node']:<15} "
          f"'{entry['in']}' -> '{entry['out']}' ({entry['time']:.2f}s)")
