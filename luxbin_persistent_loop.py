#!/usr/bin/env python3
"""
LUXBIN PERSISTENT QUANTUM LOOP

Runs forever in the background, continuously sending 'NICHE' through
all 3 IBM quantum computers in the Echo -> Relay -> Consensus -> Ping-Pong loop.

Triple encoding: Light (RY) + Sound (RZ) + Microwave (RX)

Logs all results to luxbin_loop_log.json
Run with: nohup python3 luxbin_persistent_loop.py &
"""

from qiskit import QuantumCircuit
from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2
from qiskit.transpiler.preset_passmanagers import generate_preset_pass_manager
import concurrent.futures
import numpy as np
import time
import json
import os
import signal
import sys
from datetime import datetime
from collections import Counter

TOKEN = os.environ.get('IBM_QUANTUM_TOKEN', 'YOUR_IBM_QUANTUM_TOKEN')
LOG_FILE = '/tmp/luxbin-quantum-internet/luxbin_loop_log.json'
STATUS_FILE = '/tmp/luxbin-quantum-internet/luxbin_loop_status.txt'

# LUXBIN TRIPLE ENCODING
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

def decode_counts(counts, n_chars=5):
    sorted_counts = sorted(counts.items(), key=lambda x: -x[1])
    chars, wls, freqs, mws = [], [], [], []
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
        wls.append(wl); freqs.append(freq); mws.append(mw)
    return ''.join(chars), wls, freqs, mws

def encode_char(qc, i, char):
    wl = CHAR_WAVELENGTHS.get(char.upper(), 540.3)
    freq = CHAR_FREQUENCIES.get(char.upper(), 262.6)
    mw = CHAR_MICROWAVES.get(char.upper(), 5.5)
    qc.ry(((wl - 400) / 300) * 2 * np.pi, i)
    qc.rz(((freq - 262.6) / (2349.3 - 262.6)) * np.pi, i)
    qc.rx(((mw - MW_MIN) / (MW_MAX - MW_MIN)) * np.pi, i)

def build_echo(msg):
    n = min(len(msg), 5)
    qc = QuantumCircuit(n, n)
    for i, c in enumerate(msg[:n]):
        qc.h(i); encode_char(qc, i, c)
    for i in range(n-1): qc.cx(i, i+1)
    for i in range(n): qc.h(i); qc.t(i); qc.h(i)
    for i in range(n-1): qc.cx(i, i+1)
    qc.measure(range(n), range(n))
    return qc

def build_relay(msg, leg):
    n = min(len(msg), 5)
    qc = QuantumCircuit(n, n)
    for i, c in enumerate(msg[:n]):
        qc.h(i); encode_char(qc, i, c)
    if leg == 1:
        for i in range(n): qc.rz(np.pi/4, i); qc.rx(np.pi/6, i)
        for i in range(0, n-1, 2): qc.cx(i, i+1)
    elif leg == 2:
        for i in range(n-1): qc.swap(i, i+1)
        for i in range(n): qc.ry(np.pi/3, i); qc.rx(np.pi/4, i)
    elif leg == 3:
        for i in range(n-1): qc.cx(i, i+1)
        qc.cx(n-1, 0)
        for i in range(n): qc.h(i); qc.rx(np.pi/3, i)
    for i in range(n): qc.h(i)
    qc.measure(range(n), range(n))
    return qc

def build_consensus(msg):
    n = 5; msg = (msg + 'AAAAA')[:5]
    qc = QuantumCircuit(n, n)
    for i, c in enumerate(msg):
        qc.h(i); encode_char(qc, i, c)
    for i in range(n-1): qc.cx(i, i+1)
    for i in range(n): qc.rz(np.pi/n, i); qc.rx(np.pi/(n+1), i)
    for i in range(n): qc.h(i)
    qc.measure(range(n), range(n))
    return qc

def build_ping(msg, is_pong=False):
    n = min(len(msg), 5)
    qc = QuantumCircuit(n, n)
    for i, c in enumerate(msg[:n]):
        wl = CHAR_WAVELENGTHS.get(c.upper(), 540.3)
        freq = CHAR_FREQUENCIES.get(c.upper(), 262.6)
        mw = CHAR_MICROWAVES.get(c.upper(), 5.5)
        t = ((wl-400)/300)*np.pi; p = ((freq-262.6)/(2349.3-262.6))*np.pi/2
        g = ((mw-MW_MIN)/(MW_MAX-MW_MIN))*np.pi/2
        qc.h(i)
        if is_pong: qc.ry(-t,i); qc.rz(p,i); qc.rx(-g,i)
        else: qc.ry(t,i); qc.rz(-p,i); qc.rx(g,i)
    if is_pong:
        for i in range(n-1, 0, -1): qc.cx(i, i-1)
    else:
        for i in range(n-1): qc.cx(i, i+1)
    for i in range(n): qc.t(i); qc.h(i)
    qc.measure(range(n), range(n))
    return qc

def run_hw(backend, qc, shots=500):
    pm = generate_preset_pass_manager(backend=backend, optimization_level=1)
    transpiled = pm.run(qc)
    sampler = SamplerV2(backend)
    job = sampler.run([transpiled], shots=shots)
    job_id = job.job_id()
    result = job.result()
    counts = result[0].data.c.get_counts()
    return counts, job_id

def log(msg):
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(STATUS_FILE, 'a') as f:
        f.write(line + '\n')

def save_loop_result(loop_num, data):
    """Append result to JSON log file."""
    results = []
    if os.path.exists(LOG_FILE):
        try:
            with open(LOG_FILE, 'r') as f:
                results = json.load(f)
        except:
            results = []
    results.append(data)
    with open(LOG_FILE, 'w') as f:
        json.dump(results, f, indent=2)

# ==========================================================================
# GRACEFUL SHUTDOWN
# ==========================================================================
running = True
def shutdown(sig, frame):
    global running
    log("Received shutdown signal. Finishing current loop...")
    running = False

signal.signal(signal.SIGTERM, shutdown)
signal.signal(signal.SIGINT, shutdown)

# ==========================================================================
# MAIN PERSISTENT LOOP
# ==========================================================================

log("=" * 60)
log("LUXBIN PERSISTENT QUANTUM LOOP STARTING")
log("Message: NICHE | Encoding: Light+Sound+Microwave")
log("=" * 60)

log("Connecting to IBM Quantum...")
service = QiskitRuntimeService(channel="ibm_quantum_platform", token=TOKEN)
backend_a = service.backend('ibm_fez')
backend_b = service.backend('ibm_torino')
backend_c = service.backend('ibm_marrakesh')
log(f"Backends: {backend_a.name}, {backend_b.name}, {backend_c.name}")

loop_num = 0
total_jobs = 0

# If previous output message exists from last loop, use it as input
current = "NICHE"

while running:
    loop_num += 1
    loop_start = time.time()
    jobs_this_loop = []

    log(f"\n{'='*60}")
    log(f"LOOP {loop_num} | Input: '{current}' | {datetime.now().isoformat()}")
    log(f"{'='*60}")

    try:
        # ECHO
        log(f"  ECHO [{backend_a.name}]: '{current}'")
        qc = build_echo(current)
        counts, jid = run_hw(backend_a, qc, 200)
        response, wls, freqs, mws = decode_counts(counts)
        jobs_this_loop.append(jid)
        log(f"    -> '{response}' [job:{jid}]")
        current = response

        # RELAY
        for leg, backend in enumerate([backend_a, backend_b, backend_c], 1):
            log(f"  RELAY Leg {leg} [{backend.name}]: '{current}'")
            qc = build_relay(current, leg)
            counts, jid = run_hw(backend, qc, 500)
            response, wls, freqs, mws = decode_counts(counts)
            jobs_this_loop.append(jid)
            log(f"    -> '{response}' [job:{jid}]")
            current = response

        # CONSENSUS
        log(f"  CONSENSUS: '{current}'")
        votes = []
        def do_vote(backend, msg):
            qc = build_consensus(msg)
            counts, jid = run_hw(backend, qc, 1000)
            top = max(counts.items(), key=lambda x: x[1])[0]
            val = int(top, 2)
            ratio = val / 31
            return wavelength_to_char(400 + ratio * 300), jid

        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
            futs = [ex.submit(do_vote, b, current) for b in [backend_a, backend_b, backend_c]]
            for f in concurrent.futures.as_completed(futs):
                char, jid = f.result()
                votes.append(char)
                jobs_this_loop.append(jid)

        majority = max(set(votes), key=votes.count)
        consensus = ''.join(votes)
        while len(consensus) < 5:
            consensus += majority
        current = consensus[:5]
        log(f"    -> '{current}' (votes: {votes})")

        # PING-PONG
        for rally in range(2):
            is_pong = rally % 2 == 1
            backend = [backend_a, backend_b][rally % 2]
            action = "PONG" if is_pong else "PING"
            log(f"  PING-PONG {action} [{backend.name}]: '{current}'")
            qc = build_ping(current, is_pong)
            counts, jid = run_hw(backend, qc, 500)
            response, wls, freqs, mws = decode_counts(counts)
            jobs_this_loop.append(jid)
            log(f"    -> '{response}' [job:{jid}]")
            current = response

        # FINAL ECHO (loops back - output becomes next loop's input)
        log(f"  ECHO FINAL [{backend_a.name}]: '{current}'")
        qc = build_echo(current)
        counts, jid = run_hw(backend_a, qc, 200)
        response, wls, freqs, mws = decode_counts(counts)
        jobs_this_loop.append(jid)
        log(f"    -> '{response}' [job:{jid}]")

        loop_time = time.time() - loop_start
        total_jobs += len(jobs_this_loop)

        # Save result
        loop_data = {
            'loop': loop_num,
            'timestamp': datetime.now().isoformat(),
            'input': current,
            'output': response,
            'jobs': jobs_this_loop,
            'job_count': len(jobs_this_loop),
            'loop_time_seconds': round(loop_time, 1),
            'total_jobs_all_time': total_jobs
        }
        save_loop_result(loop_num, loop_data)

        # Output becomes next input (THE LOOP)
        current = response

        log(f"\n  LOOP {loop_num} COMPLETE: '{loop_data['input']}' -> '{response}'")
        log(f"  Jobs: {len(jobs_this_loop)} | Time: {loop_time:.1f}s | Total jobs: {total_jobs}")
        log(f"  Next loop input: '{current}'")

        # Brief pause between loops to be nice to IBM's queue
        if running:
            log("  Waiting 10s before next loop...")
            time.sleep(10)

    except Exception as e:
        log(f"  ERROR in loop {loop_num}: {e}")
        log("  Waiting 30s before retry...")
        time.sleep(30)
        # Reset to NICHE on error
        current = "NICHE"

log(f"\n{'='*60}")
log(f"LOOP STOPPED after {loop_num} loops, {total_jobs} total IBM jobs")
log(f"{'='*60}")
