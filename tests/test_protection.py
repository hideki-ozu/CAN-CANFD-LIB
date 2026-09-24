#!/usr/bin/env python3
"""AUTOSAR E2E and SecOC acceptance tests (autosar/, docs/PROTECTION.md).

1. Self-test inside OMNeT++: CRC catalogue check values, E2E examples (P01/P02/P04/
   P05/P07), E2E checker and state machine, RFC 4493 AES-CMAC, SecOC layouts.
2. Reference cross-check: random PDUs protected by the C++ code are verified with
   autosar-e2e (E2E) and pycryptodome (AES-CMAC), which are independent of the C++
   code and of OpenSSL. Both are test-only and pinned by hash in a private venv.
3. CAN/CAN-FD end to end through the gateways (proprietary tunnel and IEEE 1722):
   delivery and E2E/SecOC status counts, plus a wire check of every AVTP-carried
   CAN payload against the references.
4. CAN fault injection: bit errors, replay, counter jump, wrong key, with and
   without SecOC; the expected status counts are derived by hand in FAULTS.
5. SOME/IP events (TCP, UDP, UDP multicast): delivery, wire check of every
   notification (E2E over the header from Request ID, SecOC MAC), SD untouched,
   and fault injection.
"""
import json
import os
import pathlib
import shlex
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
RESULTS = ROOT / 'results' / 'protection'
VENV = ROOT / '.local' / 'venv-protection-test'
REQUIREMENTS = ROOT / 'tests' / 'protectiontest' / 'requirements.txt'
KEY = bytes.fromhex('2b7e151628aed2a6abf7158809cf4f3c')


def ensure_venv():
    """Re-run this script inside the private venv holding the reference packages."""
    python = VENV / 'bin' / 'python'
    if pathlib.Path(sys.prefix).resolve() == VENV.resolve():
        return
    probe = [str(python), '-c', 'import e2e, Crypto; print(Crypto.__version__)']
    if not (python.exists() and subprocess.run(probe, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                               text=True).stdout.strip() == '3.23.0'):
        if VENV.exists():
            shutil.rmtree(VENV)
        subprocess.run([sys.executable, '-m', 'venv', str(VENV)], check=True)
        subprocess.run([str(python), '-m', 'pip', 'install', '-q', '--require-hashes', '-r', str(REQUIREMENTS)],
                       check=True)
    os.execv(str(python), [str(python), __file__, *sys.argv[1:]])


ensure_venv()

import e2e                                   # noqa: E402  (test-only reference, MIT)
from Crypto.Cipher import AES                # noqa: E402  (test-only reference)
from Crypto.Hash import CMAC                 # noqa: E402

sys.path.insert(0, str(ROOT / 'tests'))
import test_avtp                             # noqa: E402  (IEEE 1722 pcap parser)
import test_someip                           # noqa: E402  (IPv4/SOME/IP pcap parser)

P01_MODES = [e2e.p01.E2E_P01_DATAID_BOTH, e2e.p01.E2E_P01_DATAID_ALT, e2e.p01.E2E_P01_DATAID_LOW,
             e2e.p01.E2E_P01_DATAID_NIBBLE]
HEADER = {'P01': 2, 'P02': 2, 'P04': 12, 'P05': 3, 'P07': 20}
MODULUS = {'P01': 15, 'P02': 16, 'P04': 1 << 16, 'P05': 1 << 8, 'P07': 1 << 32}
DATA_ID_LIST = bytes.fromhex('102132435465768798a9bacbdcedfe0f')


# ---- independent reference checks --------------------------------------------------

def e2e_check(profile, area, data_id, offset=0, data_id_list=DATA_ID_LIST, mode=0):
    """autosar-e2e verification; returns the counter or None."""
    if profile == 'P01':
        ok = e2e.p01.e2e_p01_check(area, data_id, data_id_mode=P01_MODES[mode], offset=offset)
        return area[offset + 1] & 0x0F if ok else None
    if profile == 'P02':
        return area[1] & 0x0F if e2e.p02.e2e_p02_check(area, data_id_list) else None
    if profile == 'P04':
        return int.from_bytes(area[offset + 2:offset + 4], 'big') if e2e.p04.e2e_p04_check(area, data_id, offset=offset) else None
    if profile == 'P05':
        return area[offset + 2] if e2e.p05.e2e_p05_check(area, data_id, offset=offset) else None
    if profile == 'P07':
        return int.from_bytes(area[offset + 12:offset + 16], 'big') if e2e.p07.e2e_p07_check(area, data_id, offset=offset) else None
    raise AssertionError(profile)


def secoc_trailer(authentic, data_id, freshness, fv_bits, tx_bits, mac_bits, key=KEY):
    """FV LSBs followed by the MAC MSBs, bit packed MSB first (pycryptodome CMAC)."""
    data = data_id.to_bytes(2, 'big') + authentic + freshness.to_bytes(fv_bits // 8, 'big')
    mac = int.from_bytes(CMAC.new(key, data, ciphermod=AES).digest(), 'big') >> (128 - mac_bits)
    bits = tx_bits + mac_bits
    value = ((freshness & ((1 << tx_bits) - 1)) << mac_bits) | mac
    size = (bits + 7) // 8
    return (value << (size * 8 - bits)).to_bytes(size, 'big')


def truncated_fv(trailer, tx_bits, mac_bits):
    bits = tx_bits + mac_bits
    return int.from_bytes(trailer, 'big') >> (len(trailer) * 8 - bits) >> mac_bits


# ---- OMNeT++ runs ----------------------------------------------------------------------

def run(script, config, network):
    result_dir = RESULTS / config
    if result_dir.exists():
        shutil.rmtree(result_dir)
    result = subprocess.run([str(ROOT / 'scripts' / script), config, f'--result-dir={result_dir}'], cwd=ROOT,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, stdin=subprocess.DEVNULL)
    (ROOT / 'logs' / f'test-{config}.log').write_text(result.stdout)
    assert result.returncode == 0, result.stdout[-6000:]
    files = list(result_dir.glob('*.sca'))
    assert len(files) == 1, files
    scalars = {}
    for line in files[0].read_text().splitlines():
        if line.startswith('scalar '):
            _, module, name, value = shlex.split(line)
            try:
                scalars[module.removeprefix(network + '.'), name] = float(value)
            except ValueError:
                pass
    return scalars, result_dir


def self_test():
    selftest_dir = RESULTS / 'selftest'
    vectors = RESULTS / 'vectors.json'
    completed = subprocess.run(
        ['bash', '-c', 'set -e; source "$1/scripts/env.sh"; set -u; cd "$1/tests/protection"; '
         'exec opp_run -u Cmdenv -n "$1/tests:$1/autosar/src" -l "$1/autosar/src/AutosarProtection" '
         '-f selftest.ini --result-dir="$2" "--*.test.vectorFile=\\"$3\\""',
         'protection-selftest', str(ROOT), str(selftest_dir), str(vectors)],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    (ROOT / 'logs' / 'test-ProtectionSelfTest.log').write_text(completed.stdout)
    assert completed.returncode == 0, completed.stdout[-4000:]
    sca = next(selftest_dir.glob('*.sca')).read_text()
    passed = int(float(next(l.split()[-1] for l in sca.splitlines() if ' checksPassed ' in l)))
    failed = int(float(next(l.split()[-1] for l in sca.splitlines() if ' checksFailed ' in l)))
    assert failed == 0 and passed >= 111, completed.stdout[-4000:]

    data = json.loads(vectors.read_text())
    profiles = {}
    for case in data['e2e']:
        pdu = bytearray.fromhex(case['pdu'])
        counter = e2e_check(case['profile'], pdu, case['dataId'], case['offset'],
                            bytes.fromhex(case['dataIdList']), case['mode'])
        assert counter == case['counter'], case
        # The reference protect() of the same buffer yields identical bytes.
        ref = bytearray(pdu)
        p, off = case['profile'], case['offset']
        if p == 'P01':
            e2e.p01.e2e_p01_protect(ref, case['dataId'], data_id_mode=P01_MODES[case['mode']], offset=off,
                                    increment_counter=False)
        elif p == 'P02':
            e2e.p02.e2e_p02_protect(ref, bytes.fromhex(case['dataIdList']), increment_counter=False)
        else:
            getattr(getattr(e2e, p.lower()), f'e2e_{p.lower()}_protect')(ref, case['dataId'], offset=off,
                                                                        increment_counter=False)
        assert ref == pdu, case
        # A single flipped bit is rejected by the reference as well.
        pdu[len(pdu) - 1] ^= 0x01
        assert e2e_check(p, pdu, case['dataId'], off, bytes.fromhex(case['dataIdList']), case['mode']) is None, case
        profiles[p] = profiles.get(p, 0) + 1
    for case in data['secoc']:
        authentic = bytes.fromhex(case['authentic'])
        trailer = secoc_trailer(authentic, case['dataId'], case['freshness'], case['freshnessBits'],
                                case['freshnessTxBits'], case['macTxBits'], bytes.fromhex(case['key']))
        assert authentic + trailer == bytes.fromhex(case['secured']), case
    return {'passed': passed, 'failed': failed, 'reference_e2e_vectors': profiles,
            'reference_secoc_vectors': len(data['secoc'])}


# ---- CAN/CAN-FD --------------------------------------------------------------------------

CLASSIC_IDS, FD_IDS = (256, 768), (512, 1024)
# stream: (E2E profile, SecOC (transmitted FV bits, MAC bits) or None)
CAN_CONFIGS = {
    'E2eSecOc': {'classic': ('P01', (8, 24)), 'fd': ('P05', (16, 64)), 'avtp': False},
    'E2eSecOcAvtp': {'classic': ('P01', (8, 24)), 'fd': ('P05', (16, 64)), 'avtp': True},
    'E2eP02P07Avtp': {'classic': ('P02', None), 'fd': ('P07', (32, 128)), 'avtp': True},
}
SINKS = [f'ecu{side}[{i}].sinkApp[{s}]' for side in 'AB' for i in (0, 1) for s in (0, 1)]
FRAMES = 10


def sink_stats(scalars, sink):
    keys = ('receivedFrames', 'deliveredFrames', 'patternErrors', 'e2eOK', 'e2eNONEWDATA', 'e2eERROR',
            'e2eREPEATED', 'e2eOKSOMELOST', 'e2eWRONGSEQUENCE', 'secocOK', 'secocAUTHENTICATION_FAILED',
            'secocFRESHNESS_FAILED', 'secocMALFORMED', 'e2eSmValidReceptions', 'e2eSmInvalidReceptions')
    return {k: int(scalars[sink, k]) for k in keys}


def clean(frames, secoc):
    """Expected sink statistics of a fault-free stream (first reception: SM INIT)."""
    return {'receivedFrames': frames, 'deliveredFrames': frames, 'patternErrors': 0, 'e2eOK': frames,
            'e2eNONEWDATA': 0, 'e2eERROR': 0, 'e2eREPEATED': 0, 'e2eOKSOMELOST': 0, 'e2eWRONGSEQUENCE': 0,
            'secocOK': frames if secoc else 0, 'secocAUTHENTICATION_FAILED': 0, 'secocFRESHNESS_FAILED': 0,
            'secocMALFORMED': 0, 'e2eSmValidReceptions': frames - 1, 'e2eSmInvalidReceptions': 1}


def check_can_payload(can_id, index, payload, profile, secoc):
    """Verifies the index-th (0-based) fault-free payload of a stream with the references."""
    assert len(payload) == (8 if can_id in CLASSIC_IDS else 64), (can_id, len(payload))
    authentic = payload
    if secoc:
        tx, mac = secoc
        size = (tx + mac + 7) // 8
        authentic, trailer = payload[:-size], payload[-size:]
        freshness = index + 1                    # FV starts at 1
        assert truncated_fv(trailer, tx, mac) == freshness % (1 << tx)
        assert trailer == secoc_trailer(authentic, can_id, freshness, 64, tx, mac), (can_id, index)
    counter = e2e_check(profile, bytearray(authentic), can_id)
    assert counter == index % MODULUS[profile], (can_id, index, counter)
    data = [(i, b) for i, b in enumerate(authentic) if i >= HEADER[profile]]
    assert all(b == (can_id + i) & 0xFF for i, b in data), (can_id, index)
    return len(authentic)


def check_can_wire(config, spec, result_dir):
    payloads = {}
    for gateway in ('gatewayA', 'gatewayB'):
        for _, _, pdu, _, _ in test_avtp.avtp_frames(test_avtp.read_pcap(result_dir / f'{gateway}.pcap'), gateway):
            for message in test_avtp.parse_avtp(pdu)['messages']:
                payloads.setdefault(message['id'], []).append(bytes.fromhex(message['payload']))
    assert sorted(payloads) == [256, 512, 768, 1024], sorted(payloads)
    summary = {}
    for can_id, frames in payloads.items():
        profile, secoc = spec['classic' if can_id in CLASSIC_IDS else 'fd']
        assert len(frames) == FRAMES, (config, can_id, len(frames))
        lengths = {check_can_payload(can_id, i, p, profile, secoc) for i, p in enumerate(frames)}
        # Sanity: the reference rejects a manipulated copy.
        tampered = bytearray(frames[0])
        tampered[1] ^= 0x04
        if secoc:
            size = (secoc[0] + secoc[1] + 7) // 8
            assert bytes(tampered[-size:]) != secoc_trailer(bytes(tampered[:-size]), can_id, 1, 64, *secoc)
        else:
            assert e2e_check(profile, tampered, can_id) is None
        summary[can_id] = {'frames': len(frames), 'profile': profile, 'secoc': secoc,
                           'authentic_bytes': lengths.pop()}
    return summary


# Hand-derived results for ID 256 (sinkApp[0] of ecuB[0] and ecuB[1]); 30 frames,
# corrupt 5/20/21, replay 10 (= frame 9), skip 3 counters at 15, maxDeltaCounter 2.
FAULTS = {
    # SecOC drops 5, 10, 20, 21 (MAC mismatch; the replayed truncated FV rebuilds to a
    # new FV). Timeout 12 ms -> NONEWDATA at 43, 93, 193, 205 ms. E2E: 6 OKSOMELOST,
    # 15 and 22 WRONGSEQUENCE; the SM drops to INVALID at 22 (window NND, NND, WS).
    'E2eSecOcFaults': {'receivedFrames': 30, 'deliveredFrames': 24, 'patternErrors': 0, 'e2eOK': 23,
                       'e2eNONEWDATA': 4, 'e2eERROR': 0, 'e2eREPEATED': 0, 'e2eOKSOMELOST': 1,
                       'e2eWRONGSEQUENCE': 2, 'secocOK': 26, 'secocAUTHENTICATION_FAILED': 4,
                       'secocFRESHNESS_FAILED': 0, 'secocMALFORMED': 0, 'e2eSmValidReceptions': 27,
                       'e2eSmInvalidReceptions': 3},
    # E2E alone: 5/20/21 ERROR, 10 REPEATED, 6 OKSOMELOST, 15/22 WRONGSEQUENCE; the SM is
    # INVALID for 21, 22, 23 (two errors in the window, then 2 OK without error needed).
    'E2eOnlyFaults': {'receivedFrames': 30, 'deliveredFrames': 24, 'patternErrors': 0, 'e2eOK': 23,
                      'e2eNONEWDATA': 0, 'e2eERROR': 3, 'e2eREPEATED': 1, 'e2eOKSOMELOST': 1,
                      'e2eWRONGSEQUENCE': 2, 'secocOK': 0, 'secocAUTHENTICATION_FAILED': 0,
                      'secocFRESHNESS_FAILED': 0, 'secocMALFORMED': 0, 'e2eSmValidReceptions': 26,
                      'e2eSmInvalidReceptions': 4},
    'SecOcWrongKey': {'receivedFrames': 10, 'deliveredFrames': 0, 'patternErrors': 0, 'e2eOK': 0,
                      'e2eNONEWDATA': 0, 'e2eERROR': 0, 'e2eREPEATED': 0, 'e2eOKSOMELOST': 0,
                      'e2eWRONGSEQUENCE': 0, 'secocOK': 0, 'secocAUTHENTICATION_FAILED': 10,
                      'secocFRESHNESS_FAILED': 0, 'secocMALFORMED': 0, 'e2eSmValidReceptions': 0,
                      'e2eSmInvalidReceptions': 0},
}


def check_can():
    report = {}
    for config, spec in CAN_CONFIGS.items():
        scalars, result_dir = run('run-mixed.sh', config, 'MixedCanEthernet')
        for sink in SINKS:
            secoc = spec['classic' if sink.endswith('[0]') else 'fd'][1] is not None
            assert sink_stats(scalars, sink) == clean(FRAMES, secoc), (config, sink, sink_stats(scalars, sink))
        for side in 'AB':
            for i in (0, 1):
                assert scalars[f'ecu{side}[{i}].sourceApp[0]', 'protectedFrames'] == FRAMES
        report[config] = {'sinks': len(SINKS), 'frames_per_sink': FRAMES}
        if spec['avtp']:
            report[config]['wire'] = check_can_wire(config, spec, result_dir)
    for config, expected in FAULTS.items():
        scalars, _ = run('run-mixed.sh', config, 'MixedCanEthernet')
        frames = 30 if config != 'SecOcWrongKey' else FRAMES
        secoc = config != 'E2eOnlyFaults'
        for sink in SINKS:
            stats = sink_stats(scalars, sink)
            if sink.startswith('ecuB') and sink.endswith('sinkApp[0]'):
                assert stats == expected, (config, sink, stats)
                final = scalars[sink, 'id_256_e2eSmFinalState']
                assert final == (0 if config == 'SecOcWrongKey' else 2), (config, sink, final)   # NODATA / VALID
            else:
                assert stats == clean(frames, secoc), (config, sink, stats)
        report[config] = expected
    return report


# ---- SOME/IP -------------------------------------------------------------------------------

SOMEIP_CONFIGS = {
    'SomeIpE2eSecOc': {'transports': {'Node2': 'tcp', 'Node3': 'udp'}, 'profile': 'P04', 'secoc': (32, 64)},
    'SomeIpE2eP07Mcast': {'transports': {'Node2': 'mcast', 'Node3': 'mcast'}, 'profile': 'P07', 'secoc': (64, 128)},
}
SERVICE, EVENT, DELIVERED, PAYLOAD = 1, 0x8001, 48, 64


def notifications(result_dir, node, transport):
    ip = test_someip.IP
    if transport == 'tcp':
        packets = test_someip.ip_packets(result_dir / 'Node1.pcap')
        segments = sorted({seq: data for _, proto, src, _, dst, _, data, seq in packets
                           if proto == 'tcp' and src == ip['Node1'] and dst == ip[node] and data}.items())
        stream, messages, offset = b''.join(data for _, data in segments), [], 0
        while offset < len(stream):
            size = 8 + int.from_bytes(stream[offset + 4:offset + 8], 'big')
            messages.append(stream[offset:offset + size])
            offset += size
        return messages
    dst_ip, dst_port = ((test_someip.MCAST_GROUP, test_someip.MCAST_PORT) if transport == 'mcast'
                        else (ip[node], test_someip.SUBSCRIBER_PORT[node]))
    return [p for _, proto, src, sport, dst, dport, p, _ in test_someip.ip_packets(result_dir / f'{node}.pcap')
            if proto == 'udp' and src == ip['Node1'] and sport == test_someip.PUBLISHER_PORT
            and dst == dst_ip and dport == dst_port]


def check_someip_message(raw, profile, secoc):
    """Returns (E2E counter or None, truncated FV, MAC valid) of one notification."""
    msg = test_someip.parse_someip(raw)
    assert msg['size'] == len(raw) and (msg['service'], msg['method'], msg['message_type']) == (SERVICE, EVENT, 2)
    tx, mac = secoc
    size = (tx + mac + 7) // 8
    payload, trailer = msg['payload'][:-size], msg['payload'][-size:]
    assert len(payload) == HEADER[profile] + PAYLOAD
    area = bytearray(raw[8:16] + payload)
    counter = e2e_check(profile, area, (SERVICE << 16) | EVENT, offset=8)
    fv = truncated_fv(trailer, tx, mac)
    return counter, fv, msg, trailer, bytes(raw[:4] + area)


def check_someip_wire(config, spec, result_dir):
    summary = {}
    for node, transport in spec['transports'].items():
        messages = notifications(result_dir, node, transport)
        assert len(messages) == DELIVERED, (config, node, len(messages))
        for index, raw in enumerate(messages):
            counter, fv, msg, trailer, authentic = check_someip_message(raw, spec['profile'], spec['secoc'])
            assert counter == index, (config, node, index, counter)
            assert fv == (index + 1) % (1 << spec['secoc'][0])
            assert trailer == secoc_trailer(authentic, EVENT, index + 1, 64, *spec['secoc']), (config, node, index)
            data = msg['payload'][HEADER[spec['profile']]:HEADER[spec['profile']] + PAYLOAD]
            assert data == bytes((msg['session'] + i) & 0xFF for i in range(PAYLOAD))
        summary[node] = {'transport': transport, 'notifications': len(messages)}
    # SOME/IP-SD is outside the E2E/SecOC scope: its datagrams parse without a trailer.
    sd = [p for node in test_someip.IP for _, proto, src, sport, _, _, p, _ in
          test_someip.ip_packets(result_dir / f'{node}.pcap') if proto == 'udp' and sport == test_someip.SD_PORT]
    for payload in sd:
        msg = test_someip.parse_sd(payload)
        assert msg['size'] == len(payload)
    summary['sd_messages_unprotected'] = len(sd)
    return summary


def someip_endpoint(scalars, node):
    keys = ('someipReceived', 'protectionDelivered', 'patternErrors', 'e2eOK', 'e2eERROR', 'e2eREPEATED',
            'e2eOKSOMELOST', 'e2eWRONGSEQUENCE', 'secocOK', 'secocAUTHENTICATION_FAILED', 'secocFRESHNESS_FAILED')
    stats = {k: int(scalars[f'{node}.middleware.subscriberEndpoints[0]', k]) for k in keys}
    stats['rxPk'] = int(scalars[f'{node}.services[0]', 'rxPk:count'])
    return stats


def someip_clean(n):
    return {'someipReceived': n, 'protectionDelivered': n, 'patternErrors': 0, 'e2eOK': n, 'e2eERROR': 0,
            'e2eREPEATED': 0, 'e2eOKSOMELOST': 0, 'e2eWRONGSEQUENCE': 0, 'secocOK': n,
            'secocAUTHENTICATION_FAILED': 0, 'secocFRESHNESS_FAILED': 0, 'rxPk': n}


def check_someip():
    report = {}
    for config, spec in SOMEIP_CONFIGS.items():
        scalars, result_dir = run('run-someip.sh', config, 'SomeIpSmallNetwork')
        for node in ('Node2', 'Node3'):
            assert someip_endpoint(scalars, node) == someip_clean(DELIVERED), (config, node, someip_endpoint(scalars, node))
        report[config] = check_someip_wire(config, spec, result_dir)

    # Per publisher endpoint: 10 corrupted, 20 replays 19, 30 skips 3 counters.
    scalars, result_dir = run('run-someip.sh', 'SomeIpE2eSecOcFaults', 'SomeIpSmallNetwork')
    expected = dict(someip_clean(DELIVERED), protectionDelivered=45, rxPk=45, e2eOK=44, e2eOKSOMELOST=1,
                    e2eWRONGSEQUENCE=1, secocOK=46, secocAUTHENTICATION_FAILED=2)
    for node in ('Node2', 'Node3'):
        assert someip_endpoint(scalars, node) == expected, (node, someip_endpoint(scalars, node))
    messages = notifications(result_dir, 'Node3', 'udp')
    checked = [check_someip_message(raw, 'P04', (32, 64)) for raw in messages]
    assert checked[9][0] is None                          # the bit error breaks the E2E CRC ...
    assert checked[9][3] != secoc_trailer(checked[9][4], EVENT, 10, 64, 32, 64)    # ... and the MAC
    assert messages[19] == messages[18]                   # replay: identical bytes, stale FV
    assert checked[19][1] == checked[18][1] == 19
    assert checked[29][0] - checked[28][0] == 1 + 3       # counter jump
    report['SomeIpE2eSecOcFaults'] = expected

    scalars, _ = run('run-someip.sh', 'SomeIpSecOcWrongKey', 'SomeIpSmallNetwork')
    assert someip_endpoint(scalars, 'Node2') == someip_clean(DELIVERED)
    wrong = dict(someip_clean(DELIVERED), protectionDelivered=0, rxPk=0, e2eOK=0, secocOK=0,
                 secocAUTHENTICATION_FAILED=DELIVERED)
    assert someip_endpoint(scalars, 'Node3') == wrong, someip_endpoint(scalars, 'Node3')
    report['SomeIpSecOcWrongKey'] = {'Node2': 'delivered', 'Node3': wrong}
    return report


def main():
    (ROOT / 'logs').mkdir(exist_ok=True)
    RESULTS.mkdir(parents=True, exist_ok=True)
    report = {'selftest': self_test()}
    report['can'] = check_can()
    report['someip'] = check_someip()
    (RESULTS / 'report.json').write_text(json.dumps(report, indent=2, default=str) + '\n')
    print(json.dumps(report, indent=2, default=str))
    print('E2E/SecOC tests passed')


if __name__ == '__main__':
    main()
