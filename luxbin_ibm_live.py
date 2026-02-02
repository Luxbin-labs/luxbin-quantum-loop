#!/usr/bin/env python3
"""
LUXBIN LIVE ON IBM QUANTUM HARDWARE

Triple encoding (Light + Sound + Microwave) through the Echo Loop.
Submits REAL jobs to IBM quantum computers.

Pipeline: Echo -> Relay -> Consensus -> Ping-Pong -> Echo
"""

from qiskit import QuantumCircuit
from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2
from qiskit.transpiler.preset_passmanagers import generate_preset_pass_manager
import concurrent.futures
import numpy as np
import time
import os

TOKEN = os.environ.get('IBM_QUANTUM_TOKEN', 'YOUR_IBM_QUANTUM_TOKEN')

# ==========================================================================
# LUXBIN TRIPLE ENCODING
# ==========================================================================

CHAR_WAVELENGTHS = {
    'A': 400.0, 'B': 403.9, 'C': 407.8, 'D': 411.7, 'E': 415.6,
    'F': 419.5, 'G': 423.4, 'H': 427.3, 'I': 431.2, 'J': 435.1,
    'K': 439.0, 'L': 442.9, 'M': 446.8, 'N': 450.6, 'O': 454.5,
    'P': 458.4, 'Q': 462.3, 'R': 466.2, 'S': 470.1, 'T': 474.0,
    'U': 477.9, 'V': 481.8, 'W': 485.7, 'X': 489.6, 'Y': 493.5,
    'Z': 497.4, ' ': 540.3,
}

CHAR_FREQUENCIES = {
    'A': 440.0, 'B': 493.9, 'C': 523.3, 'D': 587.3, 'E': 659.3,
    'F': 698.5, 'G': 784.0, 'H': 830.6, 'I': 880.0, 'J': 932.3,
    'K': 987.8, 'L': 1046.5, 'M': 1108.7, 'N': 1174.7, 'O': 1244.5,
    'P': 1318.5, 'Q': 1396.9, 'R': 1480.0, 'S': 1568.0, 'T': 1661.2,
    'U': 1760.0, 'V': 1864.7, 'W': 1975.5, 'X': 2093.0, 'Y': 2217.5,
    'Z': 2349.3, ' ': 262.6,
}

CHAR_MICROWAVES = {
    'A': 4.000, 'B': 4.154, 'C': 4.308, 'D': 4.462, 'E': 4.615,
    'F': 4.769, 'G': 4.923, 'H': 5.077, 'I': 5.231, 'J': 5.385,
    'K': 5.538, 'L': 5.692, 'M': 5.846, 'N': 6.000, 'O': 6.154,
    'P': 6.308, 'Q': 6.462, 'R': 6.615, 'S': 6.769, 'T': 6.923,
    'U': 7.077, 'V': 7.231, 'W': 7.385, 'X': 7.538, 'Y': 7.692,
    'Z': 7.846, ' ': 5.500,
}

MW_MIN, MW_MAX = 4.0, 8.0


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

def mw_band(ghz):
    if ghz < 5.0: return "C-band"
    if ghz < 6.0: return "C/X"
    if ghz < 7.0: return "X-lo"
    return "X-hi"


def decode_counts(counts, n_chars=5):
    """Decode quantum measurement using triple-channel consensus."""
    from collections import Counter
    sorted_counts = sorted(counts.items(), key=lambda x: -x[1])
    chars, light_wls, sound_freqs, mw_ghzs = [], [], [], []

    for bitstring, count in sorted_counts[:n_chars]:
        value = int(bitstring, 2)
        max_val = 2 ** len(bitstring) - 1
        ratio = value / max_val if max_val > 0 else 0.5

        wl = 400 + ratio * 300
        freq = 262.6 + ratio * (2349.3 - 262.6)
        mw = MW_MIN + ratio * (MW_MAX - MW_MIN)

        votes = [wavelength_to_char(wl), frequency_to_char(freq), microwave_to_char(mw)]
        winner = Counter(votes).most_common(1)[0]
        chars.append(winner[0] if winner[1] >= 2 else votes[0])

        light_wls.append(wl)
        sound_freqs.append(freq)
        mw_ghzs.append(mw)

    return ''.join(chars), light_wls, sound_freqs, mw_ghzs


# ==========================================================================
# TRIPLE ENCODING
# ==========================================================================

def encode_char(qc, i, char):
    wl = CHAR_WAVELENGTHS.get(char.upper(), 540.3)
    freq = CHAR_FREQUENCIES.get(char.upper(), 262.6)
    mw = CHAR_MICROWAVES.get(char.upper(), 5.5)
    qc.ry(((wl - 400) / 300) * 2 * np.pi, i)
    qc.rz(((freq - 262.6) / (2349.3 - 262.6)) * np.pi, i)
    qc.rx(((mw - MW_MIN) / (MW_MAX - MW_MIN)) * np.pi, i)


def build_echo_circuit(message):
    n = min(len(message), 5)
    qc = QuantumCircuit(n, n)
    for i, char in enumerate(message[:n]):
        qc.h(i)
        encode_char(qc, i, char)
    for i in range(n - 1):
        qc.cx(i, i + 1)
    for i in range(n):
        qc.h(i); qc.t(i); qc.h(i)
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
        for i in range(n):
            qc.rz(np.pi / 4, i); qc.rx(np.pi / 6, i)
        for i in range(0, n - 1, 2):
            qc.cx(i, i + 1)
    elif leg == 2:
        for i in range(n - 1):
            qc.swap(i, i + 1)
        for i in range(n):
            qc.ry(np.pi / 3, i); qc.rx(np.pi / 4, i)
    elif leg == 3:
        for i in range(n - 1):
            qc.cx(i, i + 1)
        qc.cx(n - 1, 0)
        for i in range(n):
            qc.h(i); qc.rx(np.pi / 3, i)
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
    for i in range(n - 1):
        qc.cx(i, i + 1)
    for i in range(n):
        qc.rz(np.pi / n, i); qc.rx(np.pi / (n + 1), i)
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
            qc.ry(-theta, i); qc.rz(phi, i); qc.rx(-gamma, i)
        else:
            qc.ry(theta, i); qc.rz(-phi, i); qc.rx(gamma, i)
    if is_pong:
        for i in range(n - 1, 0, -1):
            qc.cx(i, i - 1)
    else:
        for i in range(n - 1):
            qc.cx(i, i + 1)
    for i in range(n):
        qc.t(i); qc.h(i)
    qc.measure(range(n), range(n))
    return qc


# ==========================================================================
# IBM HARDWARE RUNNER
# ==========================================================================

def run_on_hardware(backend, qc, shots=500):
    """Transpile and run on real IBM hardware. Returns counts and job_id."""
    pm = generate_preset_pass_manager(backend=backend, optimization_level=1)
    transpiled = pm.run(qc)
    sampler = SamplerV2(backend)
    job = sampler.run([transpiled], shots=shots)
    job_id = job.job_id()
    print(f"    Job submitted: {job_id}")
    print(f"    View at: https://quantum.ibm.com/jobs/{job_id}")
    result = job.result()
    counts = result[0].data.c.get_counts()
    return counts, job_id


# ==========================================================================
# MAIN - LIVE ON IBM HARDWARE
# ==========================================================================

print("=" * 70)
print("LUXBIN LIVE ON IBM QUANTUM HARDWARE")
print("Triple Encoding: Light + Sound + Microwave")
print("Full Bloch Sphere: RY + RZ + RX")
print("=" * 70)

print("\nConnecting to IBM Quantum...")
service = QiskitRuntimeService(channel="ibm_quantum_platform", token=TOKEN)

# Use known backends directly (avoids slow backends() query)
backend_a = service.backend('ibm_fez')
print(f"  Connected to: {backend_a.name} ({backend_a.num_qubits} qubits)")
backend_b = service.backend('ibm_torino')
print(f"  Connected to: {backend_b.name} ({backend_b.num_qubits} qubits)")
backend_c = service.backend('ibm_marrakesh')
print(f"  Connected to: {backend_c.name} ({backend_c.num_qubits} qubits)")

all_jobs = []
pipeline_log = []
pipeline_start = time.time()

current = "NICHO"  # First 5 chars (5 qubits)
# We'll send the full name in two passes: NICHO + LE

# =========================================================================
# PHASE 1: ECHO LOOP
# =========================================================================
print(f"\n{'='*70}")
print(f"PHASE 1: ECHO LOOP (2 rounds) on {backend_a.name}")
print(f"{'='*70}")
print(f"Starting message: '{current}'")

for r in range(2):
    print(f"\n  Round {r+1}:")
    print(f"    Sending: '{current}'")
    start = time.time()

    qc = build_echo_circuit(current)
    counts, job_id = run_on_hardware(backend_a, qc, shots=200)
    elapsed = time.time() - start

    response, wls, freqs, mws = decode_counts(counts)
    all_jobs.append(job_id)

    print(f"    Response: '{response}' ({elapsed:.1f}s)")
    print(f"    Light:     {[f'{w:.0f}nm ({color_name(w)})' for w in wls[:5]]}")
    print(f"    Microwave: {[f'{m:.2f}GHz ({mw_band(m)})' for m in mws[:5]]}")

    pipeline_log.append({'phase': 'ECHO', 'in': current, 'out': response,
                         'node': backend_a.name, 'job': job_id, 'time': elapsed})
    current = response

echo_out = current
print(f"\n  Echo output: '{echo_out}'")

# =========================================================================
# PHASE 2: RELAY RACE
# =========================================================================
print(f"\n{'='*70}")
print(f"PHASE 2: RELAY RACE")
print(f"{'='*70}")
print(f"Input: '{current}'")

relay_backends = [backend_a, backend_b, backend_c]
transforms = {1: "Phase + MW kick", 2: "Swap + MW mod", 3: "Loop + MW resonance"}

for leg in range(1, 4):
    backend = relay_backends[leg - 1]
    print(f"\n  Leg {leg} [{backend.name}] - {transforms[leg]}:")
    print(f"    Passing: '{current}'")
    start = time.time()

    qc = build_relay_circuit(current, leg)
    counts, job_id = run_on_hardware(backend, qc, shots=500)
    elapsed = time.time() - start

    response, wls, freqs, mws = decode_counts(counts)
    all_jobs.append(job_id)

    print(f"    Received: '{response}' ({elapsed:.1f}s)")
    print(f"    MW: {[f'{m:.2f}GHz' for m in mws[:5]]}")

    pipeline_log.append({'phase': 'RELAY', 'in': current, 'out': response,
                         'node': backend.name, 'job': job_id, 'time': elapsed})
    current = response

relay_out = current
print(f"\n  Relay output: '{relay_out}'")

# =========================================================================
# PHASE 3: CONSENSUS
# =========================================================================
print(f"\n{'='*70}")
print(f"PHASE 3: CONSENSUS VOTE")
print(f"{'='*70}")
print(f"Proposal: '{current}'")

while len(current) < 5:
    current += 'A'

votes = []
start = time.time()

def vote_hw(backend, msg):
    qc = build_consensus_circuit(msg)
    counts, job_id = run_on_hardware(backend, qc, shots=1000)
    top = max(counts.items(), key=lambda x: x[1])[0]
    val = int(top, 2)
    ratio = val / 31
    wl = 400 + ratio * 300
    freq = 262.6 + ratio * (2349.3 - 262.6)
    mw = MW_MIN + ratio * (MW_MAX - MW_MIN)
    return {
        'backend': backend.name,
        'vote_light': wavelength_to_char(wl),
        'vote_mw': microwave_to_char(mw),
        'wl': wl, 'mw': mw, 'job_id': job_id
    }

with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
    futures = [executor.submit(vote_hw, b, current)
               for b in [backend_a, backend_b, backend_c]]
    for f in concurrent.futures.as_completed(futures):
        v = f.result()
        votes.append(v)
        all_jobs.append(v['job_id'])
        print(f"  {v['backend']} votes: Light='{v['vote_light']}' ({v['wl']:.0f}nm) "
              f"MW='{v['vote_mw']}' ({v['mw']:.2f}GHz)")

elapsed = time.time() - start
print(f"  Voting done in {elapsed:.1f}s")

vote_chars = [v['vote_light'] for v in votes]
majority = max(set(vote_chars), key=vote_chars.count)
consensus_msg = ''.join(vote_chars)
while len(consensus_msg) < 5:
    consensus_msg += majority
current = consensus_msg[:5]

pipeline_log.append({'phase': 'CONSENSUS', 'in': relay_out, 'out': current,
                     'node': 'ALL', 'job': 'multiple', 'time': elapsed})

consensus_out = current
print(f"\n  Consensus: '{consensus_out}'")

# =========================================================================
# PHASE 4: PING-PONG
# =========================================================================
print(f"\n{'='*70}")
print(f"PHASE 4: PING-PONG")
print(f"{'='*70}")
print(f"Ball: '{current}'")

players = [backend_a, backend_b]

for rally in range(4):
    is_pong = (rally % 2 == 1)
    backend = players[rally % 2]
    action = "PONG" if is_pong else "PING"

    print(f"\n  Rally {rally+1} [{backend.name}] {action}:")
    print(f"    Ball in: '{current}'")
    start = time.time()

    qc = build_ping_circuit(current, is_pong)
    counts, job_id = run_on_hardware(backend, qc, shots=500)
    elapsed = time.time() - start

    response, wls, freqs, mws = decode_counts(counts)
    all_jobs.append(job_id)

    print(f"    Ball out: '{response}' ({elapsed:.1f}s)")
    print(f"    MW: {[f'{m:.2f}GHz' for m in mws[:5]]}")

    pipeline_log.append({'phase': 'PINGPONG', 'in': current, 'out': response,
                         'node': backend.name, 'job': job_id, 'time': elapsed})
    current = response

pingpong_out = current
print(f"\n  Ping-Pong output: '{pingpong_out}'")

# =========================================================================
# PHASE 5: FINAL ECHO
# =========================================================================
print(f"\n{'='*70}")
print(f"PHASE 5: FINAL ECHO")
print(f"{'='*70}")

print(f"  Looping back: '{current}'")
start = time.time()
qc = build_echo_circuit(current)
counts, job_id = run_on_hardware(backend_a, qc, shots=200)
elapsed = time.time() - start

final, final_wls, final_freqs, final_mws = decode_counts(counts)
all_jobs.append(job_id)

pipeline_log.append({'phase': 'ECHO_FINAL', 'in': current, 'out': final,
                     'node': backend_a.name, 'job': job_id, 'time': elapsed})

print(f"  Result: '{final}' ({elapsed:.1f}s)")

total_time = time.time() - pipeline_start

# =========================================================================
# RESULTS
# =========================================================================

print(f"\n{'='*70}")
print("LUXBIN IBM QUANTUM RESULTS")
print(f"{'='*70}")

print(f"\nTotal time: {total_time:.1f}s")
print(f"Total IBM jobs: {len(all_jobs)}")

stages = [
    ('START', '-', 'NICHO'),
    ('ECHO', backend_a.name, echo_out),
    ('RELAY', 'All 3', relay_out),
    ('CONSENSUS', 'All 3', consensus_out),
    ('PINGPONG', f'{backend_a.name}/{backend_b.name}', pingpong_out),
    ('FINAL', backend_a.name, final),
]

print(f"\nMessage evolution:")
print("-" * 80)
print(f"  {'Phase':<12} {'Backend':<20} {'Message':<8} {'Light':<10} {'MW'}")
print("-" * 80)

for label, node, msg in stages:
    avg_wl = np.mean([CHAR_WAVELENGTHS.get(c.upper(), 540) for c in msg[:5]])
    avg_mw = np.mean([CHAR_MICROWAVES.get(c.upper(), 5.5) for c in msg[:5]])
    print(f"  {label:<12} {node:<20} '{msg:<5}' {avg_wl:>6.0f}nm  {avg_mw:>5.2f}GHz")

print(f"""
{'='*70}
PIPELINE: 'NICHO' -> '{final}'
{'='*70}

  NICHO -> [{backend_a.name}] ECHO
       -> [{backend_a.name}] RELAY Leg 1 (Phase + MW kick)
       -> [{backend_b.name}] RELAY Leg 2 (Swap + MW mod)
       -> [{backend_c.name}] RELAY Leg 3 (Loop + MW res)
       -> [ALL 3] CONSENSUS VOTE
       -> [{backend_a.name}/{backend_b.name}] PING-PONG x4
       -> [{backend_a.name}] FINAL ECHO
       -> '{final}'

  Encoding: Light (RY) + Sound (RZ) + Microwave (RX)
  Full Bloch sphere coverage on REAL quantum hardware!
""")

print(f"{'='*70}")
print("ALL IBM QUANTUM JOB IDs")
print(f"{'='*70}")
print(f"\nView your jobs at: https://quantum.ibm.com/jobs\n")
for entry in pipeline_log:
    job = entry.get('job', 'N/A')
    print(f"  [{entry['phase']:<12}] {entry['node']:<20} {job}")
    if job != 'multiple' and job != 'N/A':
        print(f"                     https://quantum.ibm.com/jobs/{job}")

print(f"\nTotal: {len(all_jobs)} jobs on real IBM quantum hardware")
