#!/usr/bin/env python3
"""
LUXBIN QUANTUM CONSENSUS

All 3 IBM quantum computers "vote" on the same quantum state.
If they're truly quantum, their votes should show:
1. Individual randomness (each computer's result is random)
2. Statistical agreement (probability distributions should match)
3. Quantum signatures (characteristic patterns from real hardware)

This tests whether the computers can reach "quantum consensus"!
"""

from qiskit import QuantumCircuit
from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2
from qiskit.transpiler.preset_passmanagers import generate_preset_pass_manager
import concurrent.futures
import numpy as np
import time
import os

TOKEN = os.environ.get('IBM_QUANTUM_TOKEN', 'YOUR_IBM_QUANTUM_TOKEN')

# LUXBIN
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

def create_consensus_circuit(seed_message: str):
    """
    Create identical circuit for all computers.

    The circuit encodes a "proposal" that all computers vote on.
    """
    n_qubits = 5
    qc = QuantumCircuit(n_qubits, n_qubits)

    # Encode seed message as the "proposal"
    for i, char in enumerate(seed_message[:n_qubits]):
        wavelength = CHAR_WAVELENGTHS.get(char.upper(), 540.3)
        theta = ((wavelength - 400) / 300) * np.pi

        qc.h(i)
        qc.ry(theta, i)

    # Create GHZ-like state (all qubits correlated)
    for i in range(n_qubits - 1):
        qc.cx(i, i + 1)

    # Add phase that encodes "agreement"
    for i in range(n_qubits):
        qc.rz(np.pi / n_qubits, i)

    # Interference layer
    for i in range(n_qubits):
        qc.h(i)

    qc.measure(range(n_qubits), range(n_qubits))
    return qc

def run_vote(backend, seed_message):
    """Run voting circuit on one backend."""
    qc = create_consensus_circuit(seed_message)

    pm = generate_preset_pass_manager(backend=backend, optimization_level=1)
    transpiled = pm.run(qc)

    sampler = SamplerV2(backend)
    job = sampler.run([transpiled], shots=1000)

    result = job.result()
    counts = result[0].data.c.get_counts()

    # Determine the "vote" (most common outcome)
    vote = max(counts.items(), key=lambda x: x[1])[0]
    vote_int = int(vote, 2)
    vote_wavelength = 400 + (vote_int / 31) * 300
    vote_char = wavelength_to_char(vote_wavelength)

    # Calculate entropy (measure of agreement)
    total = sum(counts.values())
    probs = [c/total for c in counts.values()]
    entropy = -sum(p * np.log2(p) if p > 0 else 0 for p in probs)

    return {
        'backend': backend.name,
        'job_id': job.job_id(),
        'vote': vote,
        'vote_char': vote_char,
        'vote_wavelength': vote_wavelength,
        'entropy': entropy,
        'counts': counts,
        'top_3': sorted(counts.items(), key=lambda x: -x[1])[:3]
    }

def calculate_consensus(results):
    """Calculate consensus metrics across all votes."""
    votes = [r['vote'] for r in results]
    vote_chars = [r['vote_char'] for r in results]

    # Check for unanimous vote
    unanimous = len(set(votes)) == 1

    # Check for character consensus
    char_consensus = len(set(vote_chars)) == 1

    # Calculate cross-correlation of probability distributions
    all_keys = set()
    for r in results:
        all_keys.update(r['counts'].keys())

    # Build probability vectors
    prob_vectors = []
    for r in results:
        total = sum(r['counts'].values())
        vec = [r['counts'].get(k, 0) / total for k in sorted(all_keys)]
        prob_vectors.append(vec)

    # Pairwise correlations
    correlations = []
    for i in range(len(results)):
        for j in range(i + 1, len(results)):
            corr = np.corrcoef(prob_vectors[i], prob_vectors[j])[0, 1]
            correlations.append({
                'pair': (results[i]['backend'], results[j]['backend']),
                'correlation': corr
            })

    avg_correlation = np.mean([c['correlation'] for c in correlations])

    # Find common outcomes across all computers
    common_outcomes = set(results[0]['counts'].keys())
    for r in results[1:]:
        common_outcomes &= set(r['counts'].keys())

    return {
        'unanimous': unanimous,
        'char_consensus': char_consensus,
        'majority_vote': max(set(vote_chars), key=vote_chars.count),
        'correlations': correlations,
        'avg_correlation': avg_correlation,
        'common_outcomes': len(common_outcomes),
        'total_outcomes': len(all_keys)
    }

# =============================================================================
# MAIN
# =============================================================================

print("=" * 70)
print("LUXBIN QUANTUM CONSENSUS")
print("3 quantum computers vote on the same quantum state")
print("=" * 70)

# Connect
print("\nConnecting to IBM Quantum Network...")
service = QiskitRuntimeService(channel="ibm_quantum_platform", token=TOKEN)
backends = service.backends(operational=True, simulator=False)[:3]
print(f"Voters: {[b.name for b in backends]}")

# The proposal to vote on
proposal = "VOTE"
print(f"\n📜 PROPOSAL: '{proposal}'")

print(f"\n{'='*70}")
print("VOTING IN PROGRESS")
print(f"{'='*70}")

# All computers vote simultaneously
results = []
start = time.time()

with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
    futures = [executor.submit(run_vote, backend, proposal) for backend in backends]

    for future in concurrent.futures.as_completed(futures):
        try:
            result = future.result()
            results.append(result)
            print(f"✓ {result['backend']} voted: {result['vote']} → '{result['vote_char']}'")
        except Exception as e:
            print(f"✗ Error: {e}")

elapsed = time.time() - start
print(f"\nVoting completed in {elapsed:.1f}s")

# Calculate consensus
consensus = calculate_consensus(results)

# =============================================================================
# RESULTS
# =============================================================================

print(f"\n{'='*70}")
print("VOTING RESULTS")
print(f"{'='*70}")

print("\n┌────────────────┬──────────┬──────┬───────────┬─────────┐")
print("│    Computer    │   Vote   │ Char │ Wavelength│ Entropy │")
print("├────────────────┼──────────┼──────┼───────────┼─────────┤")

for r in sorted(results, key=lambda x: x['backend']):
    print(f"│ {r['backend']:14} │ {r['vote']:8} │  {r['vote_char']}   │  {r['vote_wavelength']:5.0f}nm  │  {r['entropy']:.2f}   │")

print("└────────────────┴──────────┴──────┴───────────┴─────────┘")

print(f"\n{'='*70}")
print("CONSENSUS ANALYSIS")
print(f"{'='*70}")

print(f"""
  Unanimous vote (same bitstring): {'✓ YES' if consensus['unanimous'] else '✗ NO'}
  Character consensus:             {'✓ YES' if consensus['char_consensus'] else '✗ NO'}
  Majority vote:                   '{consensus['majority_vote']}'

  Common outcomes:                 {consensus['common_outcomes']}/{consensus['total_outcomes']}
                                   ({100*consensus['common_outcomes']/consensus['total_outcomes']:.0f}% overlap)

  Average correlation:             {consensus['avg_correlation']:.3f}
""")

print("Pairwise correlations:")
for c in consensus['correlations']:
    bar_len = int(abs(c['correlation']) * 20)
    bar = "█" * bar_len
    print(f"  {c['pair'][0]} ↔ {c['pair'][1]}: {c['correlation']:+.3f} {bar}")

# Top outcomes comparison
print(f"\n{'='*70}")
print("TOP OUTCOMES BY COMPUTER")
print(f"{'='*70}")

for r in sorted(results, key=lambda x: x['backend']):
    print(f"\n{r['backend']}:")
    for outcome, count in r['top_3']:
        value = int(outcome, 2)
        wl = 400 + (value / 31) * 300
        char = wavelength_to_char(wl)
        pct = 100 * count / sum(r['counts'].values())
        bar = "█" * int(pct / 5)
        print(f"  {outcome} → '{char}' ({wl:.0f}nm): {bar} {pct:.1f}%")

# Visual voting
print(f"\n{'='*70}")
print("VISUAL VOTE")
print(f"{'='*70}")

print("""
    ┌─────────────────────────────────────────────────────────┐
    │                    QUANTUM BALLOT                        │
    ├─────────────────────────────────────────────────────────┤""")

for r in sorted(results, key=lambda x: x['backend']):
    char = r['vote_char']
    wl = r['vote_wavelength']
    color = "Violet" if wl < 450 else "Blue" if wl < 500 else "Cyan" if wl < 520 else "Green" if wl < 565 else "Yellow" if wl < 590 else "Orange" if wl < 625 else "Red"
    print(f"    │  {r['backend']:14}  votes:  [ {char} ]  ({color:6}, {wl:.0f}nm)  │")

print("""    ├─────────────────────────────────────────────────────────┤
    │                                                         │""")

if consensus['char_consensus']:
    print(f"    │        ✓ CONSENSUS REACHED: '{consensus['majority_vote']}'                      │")
else:
    print(f"    │        ⚡ QUANTUM SUPERPOSITION OF VOTES              │")
    print(f"    │        Majority: '{consensus['majority_vote']}'                                 │")

print("""    │                                                         │
    └─────────────────────────────────────────────────────────┘
""")

print(f"""
{'='*70}
INTERPRETATION
{'='*70}

What does this mean?

1. HIGH CORRELATION ({consensus['avg_correlation']:.1%}):
   - The quantum computers show similar probability distributions
   - This suggests they're running the same quantum algorithm
   - NOT that they're communicating directly

2. DIFFERENT VOTES (if applicable):
   - Each computer's random outcome is truly random
   - But the underlying probabilities are similar
   - This is quantum mechanics in action!

3. COMMON OUTCOMES ({consensus['common_outcomes']} shared):
   - Despite randomness, certain outcomes appear on all machines
   - These are the "preferred" quantum states
   - Could be used for distributed consensus protocols

LUXBIN Insight:
  The proposal '{proposal}' was encoded as wavelengths.
  Each computer's vote is a quantum-derived response.
  Correlation shows quantum agreement without classical communication!
""")

print(f"\nAll job IDs:")
for r in sorted(results, key=lambda x: x['backend']):
    print(f"  {r['job_id']} ({r['backend']})")
