#!/usr/bin/env python3
"""IEEE 1722 (AVTP) acceptance tests for the CAN/CAN-FD gateway.

1. Codec self-test inside OMNeT++ (golden vectors, round trips, malformed PDUs).
2. Nine network configurations (four on INET TSN): delivery, byte integrity, sequence, drop counters.
3. Wire check of the recorded pcap with an independent Python parser written from
   the IEEE 1722-2016 field tables, plus the COVESA Open1722 reference decoder.
4. Negative scenarios: stream-ID filter, CAN bus-ID filter, late presentation.
5. INET TSN: 802.1Q PCP/VID tagging, credit-based shaping under overload, gPTP.
"""
import json
import os
import pathlib
import shlex
import shutil
import struct
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]
RESULTS = ROOT / 'results' / 'avtp'
OPEN1722 = ROOT / 'upstream' / 'Open1722'
DECODER = ROOT / '.local' / 'bin' / 'open1722_decode'

ETHERTYPE_AVTP = 0x22F0
MAC = {'gatewayA': bytes.fromhex('020000000001'), 'gatewayB': bytes.fromhex('020000000002')}
STREAM_DEST = {'gatewayA': bytes.fromhex('91e0f000fe01'), 'gatewayB': bytes.fromhex('91e0f000fe02')}
PEER = {'gatewayA': 'gatewayB', 'gatewayB': 'gatewayA'}
CAN_IDS = {'gatewayA': {256, 512}, 'gatewayB': {768, 1024}}
BUS_ID = {'gatewayA': 1, 'gatewayB': 2}
FD_LENGTHS = {0, 1, 2, 3, 4, 5, 6, 7, 8, 12, 16, 20, 24, 32, 48, 64}

CONFIGS = {
    'AvtpNtscf': {'subtype': 0x82, 'acf': 1, 'pdus': 20, 'per_pdu': 1},
    'AvtpTscf': {'subtype': 0x05, 'acf': 1, 'pdus': 20, 'per_pdu': 1, 'transit_ns': 500_000},
    'AvtpBriefAggregated': {'subtype': 0x82, 'acf': 2, 'pdus': 10, 'per_pdu': 2},
    'AvtpLoadedEthernet': {'subtype': 0x05, 'acf': 1, 'pdus': 20, 'per_pdu': 1, 'transit_ns': 500_000},
    'AvtpFdNoBrs': {'subtype': 0x82, 'acf': 1, 'pdus': 20, 'per_pdu': 1, 'brs': 0},
    # Best effort flooded to an unowned MAC congests the switch egress ports.
    'AvtpTscfOverload': {'subtype': 0x05, 'acf': 1, 'pdus': 20, 'per_pdu': 1, 'transit_ns': 500_000,
                         'flooded_background': True},
    'AvtpTsn': {'subtype': 0x05, 'acf': 1, 'pdus': 20, 'per_pdu': 1, 'transit_ns': 500_000,
                'flooded_background': True, 'vlan': (3, 2)},
    'AvtpTsnGptp': {'subtype': 0x05, 'acf': 1, 'pdus': 20, 'per_pdu': 1, 'transit_ns': 500_000,
                    'flooded_background': True, 'vlan': (3, 2), 'drifting_clocks': True},
    'AvtpTsnFreeRunning': {'subtype': 0x05, 'acf': 1, 'pdus': 20, 'per_pdu': 1, 'transit_ns': 500_000,
                           'flooded_background': True, 'vlan': (3, 2), 'drifting_clocks': True},
}
PROCESSING_DELAY = 5e-6
MAX_BEST_EFFORT_FRAME = (1400 + 14 + 4 + 8 + 12) * 8 / 100e6   # 1400B payload on 100 Mbps incl. preamble/IFG
DROP_COUNTERS = ('sequenceLost', 'sequenceOutOfOrder', 'droppedMalformedPdus', 'droppedStreamId',
                 'droppedBusId', 'droppedInvalidMessages', 'droppedRtr', 'unsupportedAcfMessages',
                 'latePresentations', 'droppedLate', 'originTagMissing')


def run(config, name=None, extra=()):
    """Run one configuration of examples/mixed; return (scalars, statistics, result dir)."""
    name = name or config
    result_dir = RESULTS / name
    if result_dir.exists():
        shutil.rmtree(result_dir)
    result = subprocess.run([str(ROOT / 'scripts/run-mixed.sh'), config, f'--result-dir={result_dir}', *extra],
                            cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    (ROOT / 'logs' / f'test-{name}.log').write_text(result.stdout)
    assert result.returncode == 0, result.stdout[-6000:]
    return (*read_sca(result_dir), result_dir)


def read_sca(result_dir):
    files = list(result_dir.glob('*.sca'))
    assert len(files) == 1, files
    scalars, stats, current = {}, {}, None
    for line in files[0].read_text().splitlines():
        if line.startswith('scalar '):
            _, module, name, value = shlex.split(line)
            scalars[module.removeprefix('MixedCanEthernet.'), name] = float(value)
            current = None
        elif line.startswith('statistic '):
            _, module, name = shlex.split(line)
            current = stats.setdefault((module.removeprefix('MixedCanEthernet.'), name), {})
        elif line.startswith('field ') and current is not None:
            _, field, value = shlex.split(line)
            current[field] = float(value)
    return scalars, stats


def app(gateway):
    return f'{gateway}.app[0]'


# ---- independent IEEE 1722 wire parser ----------------------------------------------

def read_pcap(path):
    data = path.read_bytes()
    magic = struct.unpack('<I', data[:4])[0]
    assert magic == 0xa1b23c4d, f'{path}: expected nanosecond pcap, magic {magic:#x}'
    linktype = struct.unpack('<I', data[20:24])[0]
    assert linktype == 1, f'{path}: expected Ethernet link type, got {linktype}'
    offset, frames = 24, []
    while offset < len(data):
        seconds, nanos, captured, _ = struct.unpack('<IIII', data[offset:offset + 16])
        offset += 16
        frames.append((seconds * 1_000_000_000 + nanos, data[offset:offset + captured]))
        offset += captured
    return frames


def parse_avtp(pdu):
    """Decode an AVTPDU strictly following the IEEE 1722-2016 field tables."""
    subtype = pdu[0]
    out = {'subtype': subtype, 'sv': pdu[1] >> 7, 'version': (pdu[1] >> 4) & 7, 'messages': []}
    if subtype == 0x82:
        header, length = 12, ((pdu[1] & 7) << 8) | pdu[2]
        out.update(sequence=pdu[3], stream_id=int.from_bytes(pdu[4:12], 'big'), r=(pdu[1] >> 3) & 1)
    elif subtype == 0x05:
        header = 24
        length = int.from_bytes(pdu[20:22], 'big')
        out.update(mr=(pdu[1] >> 3) & 1, rsv=(pdu[1] >> 1) & 3, tv=pdu[1] & 1, sequence=pdu[2],
                   reserved1=pdu[3] >> 1, tu=pdu[3] & 1, stream_id=int.from_bytes(pdu[4:12], 'big'),
                   avtp_timestamp=int.from_bytes(pdu[12:16], 'big'),
                   reserved2=int.from_bytes(pdu[16:20], 'big'), reserved3=int.from_bytes(pdu[22:24], 'big'))
    else:
        raise AssertionError(f'unexpected AVTP subtype {subtype:#x}')
    out['data_length'] = length
    out['trailer'] = pdu[header + length:]
    offset = header
    while offset < header + length:
        word = int.from_bytes(pdu[offset:offset + 2], 'big')
        msg_type, msg_length = word >> 9, (word & 0x1ff) * 4
        assert msg_length > 0 and offset + msg_length <= header + length
        msg = pdu[offset:offset + msg_length]
        flags = msg[2]
        can_header = 16 if msg_type == 1 else 8
        pad = flags >> 6
        entry = {'type': msg_type, 'length': msg_length, 'pad': pad, 'mtv': (flags >> 5) & 1,
                 'rtr': (flags >> 4) & 1, 'eff': (flags >> 3) & 1, 'brs': (flags >> 2) & 1,
                 'fdf': (flags >> 1) & 1, 'esi': flags & 1, 'rsv1': msg[3] >> 5, 'bus': msg[3] & 0x1f,
                 'id': int.from_bytes(msg[can_header - 4:can_header], 'big') & 0x1fffffff,
                 'rsv2': msg[can_header - 4] >> 5,
                 'payload': msg[can_header:msg_length - pad].hex(), 'pad_bytes': msg[msg_length - pad:]}
        if msg_type == 1:
            entry['timestamp'] = int.from_bytes(msg[4:12], 'big')
        out['messages'].append(entry)
        offset += msg_length
    return out


def avtp_frames(frames, source):
    """(capture time, dst, AVTPDU bytes, frame length, (PCP, VID) or None) of every AVTP frame from source."""
    result = []
    for time_ns, frame in frames:
        if frame[6:12] != MAC[source]:
            continue
        ethertype, offset, vlan = int.from_bytes(frame[12:14], 'big'), 14, None
        if ethertype == 0x8100:                              # IEEE 802.1Q C-tag
            tci = int.from_bytes(frame[14:16], 'big')
            assert (tci >> 12) & 1 == 0                      # DEI
            vlan = (tci >> 13, tci & 0xfff)
            ethertype, offset = int.from_bytes(frame[16:18], 'big'), 18
        if ethertype == ETHERTYPE_AVTP:
            result.append((time_ns, frame[:6], frame[offset:-4], len(frame), vlan))
    return result


def build_decoder():
    assert (OPEN1722 / 'include' / 'avtp' / 'acf' / 'Can.h').exists(), \
        'upstream/Open1722 missing: run python3 scripts/fetch-sources.py'
    DECODER.parent.mkdir(parents=True, exist_ok=True)
    compiler = os.environ.get('CC') or shutil.which('cc') or shutil.which('gcc') or shutil.which('clang')
    assert compiler, 'A C compiler (cc, gcc or clang) is required for the Open1722 cross-check'
    subprocess.run([compiler, '-std=c11', '-O1', '-Wall', f'-I{OPEN1722 / "include"}',
                    str(ROOT / 'tests/avtp/open1722_decode.c'), str(OPEN1722 / 'src/avtp/Utils.c'),
                    str(OPEN1722 / 'src/avtp/CommonHeader.c'), '-o', str(DECODER)], check=True)


def open1722_decode(pdus):
    completed = subprocess.run([str(DECODER)], input=''.join(p.hex() + '\n' for p in pdus),
                               stdout=subprocess.PIPE, text=True, check=True)
    return [json.loads(line) for line in completed.stdout.splitlines()]


def check_wire(config, spec, result_dir, scalars):
    captures = {gw: read_pcap(result_dir / f'{gw}.pcap') for gw in MAC}
    summary = {}
    for talker in MAC:
        sent = avtp_frames(captures[talker], talker)
        received = avtp_frames(captures[PEER[talker]], talker)
        assert len(sent) == spec['pdus'] == scalars[app(talker), 'avtpPdusSent'], (config, talker, len(sent))
        # The switch forwards the talker's bytes unchanged to the listener.
        assert [f[2:] for f in sent] == [f[2:] for f in received], (config, talker)
        stream_id = int.from_bytes(MAC[talker], 'big') << 16 | 1
        references = open1722_decode([f[2] for f in sent])
        can_messages = 0
        for index, ((time_ns, dst, pdu, frame_length, vlan), reference) in enumerate(zip(sent, references)):
            assert vlan == spec.get('vlan'), (config, talker, vlan)   # PCP 3 / VID 2 only with TSN
            parsed = parse_avtp(pdu)
            assert dst == STREAM_DEST[talker]
            assert frame_length >= 64                       # minimum Ethernet frame incl. FCS
            assert set(parsed['trailer']) <= {0}            # Ethernet padding only
            assert parsed['subtype'] == spec['subtype'] and parsed['sv'] == 1 and parsed['version'] == 0
            assert parsed['stream_id'] == stream_id
            assert parsed['sequence'] == index % 256, (config, talker, index, parsed['sequence'])
            assert len(parsed['messages']) == spec['per_pdu']
            assert parsed['data_length'] == sum(m['length'] for m in parsed['messages'])
            if spec['subtype'] == 0x05:
                assert parsed['tv'] == 1 and parsed['mr'] == 0 and parsed['tu'] == 0
                assert parsed['rsv'] == parsed['reserved1'] == parsed['reserved2'] == parsed['reserved3'] == 0
                # Presentation time lies within maxTransitTime of the capture (tx end) time.
                ahead = (parsed['avtp_timestamp'] - time_ns) % 2**32
                # Talker clocks may drift up to 50 ppm from simulation time (at most 5 us in 100 ms).
                tolerance = 10_000 if spec.get('drifting_clocks') else 0
                assert 0 < ahead <= spec['transit_ns'] + tolerance, (config, talker, ahead)
            else:
                assert parsed['r'] == 0
            for message in parsed['messages']:
                can_messages += 1
                length = len(message['payload']) // 2
                assert message['type'] == spec['acf']
                assert message['length'] % 4 == 0 and message['pad'] < 4 and set(message['pad_bytes']) <= {0}
                assert message['length'] == (16 if spec['acf'] == 1 else 8) + length + message['pad']
                assert message['id'] in CAN_IDS[talker] and message['bus'] == BUS_ID[talker]
                assert message['rsv1'] == message['rsv2'] == message['rtr'] == message['esi'] == message['eff'] == 0
                assert length in FD_LENGTHS
                expected_flags = (1, spec.get('brs', 1)) if length == 64 else (0, 0)
                assert (message['fdf'], message['brs']) == expected_flags, (config, message)
                payload = bytes.fromhex(message['payload'])
                assert payload == bytes((message['id'] + i) & 255 for i in range(length))
                if spec['acf'] == 1:
                    assert message['mtv'] == 1
                    assert 0 < time_ns - message['timestamp'] < 3_000_000   # CAN reception precedes tx
                else:
                    assert message['mtv'] == 0
            # Cross-check every field against the Open1722 reference decoder.
            assert reference['valid'] is True and reference['subtype'] == parsed['subtype']
            for key in ('version', 'sv', 'sequence', 'stream_id', 'data_length', 'tv', 'avtp_timestamp'):
                if key in reference:
                    assert reference[key] == parsed[key], (config, key, reference[key], parsed[key])
            assert len(reference['messages']) == len(parsed['messages'])
            for ref_msg, msg in zip(reference['messages'], parsed['messages']):
                assert ref_msg['valid'] is True, ref_msg
                for key in ('type', 'length', 'pad', 'mtv', 'rtr', 'eff', 'brs', 'fdf', 'esi', 'bus', 'id',
                            'payload', 'timestamp'):
                    if key in ref_msg:
                        assert ref_msg[key] == msg[key], (config, key, ref_msg[key], msg[key])
        assert can_messages == 20
        summary[talker] = {'pdus': len(sent), 'can_messages': can_messages, 'open1722_valid': len(references)}
    return summary


def check_delivery(config, spec, scalars, stats):
    for gateway in MAC:
        assert scalars[app(gateway), 'canToAvtp'] == 20
        assert scalars[app(gateway), 'avtpToCan'] == 20
        assert scalars[app(gateway), 'avtpPdusReceived'] == spec['pdus']
        for counter in DROP_COUNTERS:
            assert scalars[app(gateway), counter] == 0, (config, gateway, counter)
        assert stats[app(gateway), 'acfMessagesPerPdu:stats']['mean'] == spec['per_pdu']
    for side, ids in (('A', (768, 1024)), ('B', (256, 512))):
        for node in range(2):
            module = f'ecu{side}[{node}].sinkApp[0]'
            assert scalars[module, 'receivedFrames'] == 20
            assert scalars[module, 'receivedPayloadBytes'] == 720
            for can_id in ids:
                assert scalars[module, f'id_{can_id}_received'] == 10
    sent = scalars['background.app[0].source', 'packets sent']
    received = scalars['receiver.app[0].source', 'packets received']
    if spec.get('flooded_background'):
        assert sent > 800 and received == 0, (sent, received)   # addressed to nobody
    else:
        assert sent > 0 and sent == received, (sent, received)
    return received


def main():
    (ROOT / 'logs').mkdir(exist_ok=True)
    RESULTS.mkdir(parents=True, exist_ok=True)
    build_decoder()
    report = {}

    # 1. codec self-test
    selftest_dir = RESULTS / 'selftest'
    completed = subprocess.run(
        ['bash', '-c', 'set -e; source "$1/scripts/env.sh"; set -u; cd "$1/tests/avtp"; '
         'exec opp_run -u Cmdenv -n "$1/tests:$INET_ROOT/src:$1/upstream/FiCo4OMNeT/src:$1/upstream/SignalsAndGateways/src-inet4" '
         '-l "$INET_ROOT/src/INET" -l "$1/upstream/FiCo4OMNeT/src/FiCo4OMNeT" '
         '-l "$1/upstream/SignalsAndGateways/src-inet4/SignalsAndGateways_INET4" '
         '-f selftest.ini --result-dir="$2"', 'avtp-selftest', str(ROOT), str(selftest_dir)],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    (ROOT / 'logs' / 'test-AvtpSelfTest.log').write_text(completed.stdout)
    assert completed.returncode == 0, completed.stdout[-4000:]
    sca = next(selftest_dir.glob('*.sca')).read_text()
    passed = int(float(next(l.split()[-1] for l in sca.splitlines() if ' checksPassed ' in l)))
    failed = int(float(next(l.split()[-1] for l in sca.splitlines() if ' checksFailed ' in l)))
    assert failed == 0 and passed >= 33, completed.stdout[-4000:]
    report['codec_selftest'] = {'passed': passed, 'failed': failed}

    # 2 + 3. network configurations and wire checks
    delays = {}
    for config, spec in CONFIGS.items():
        scalars, stats, result_dir = run(config)
        background = check_delivery(config, spec, scalars, stats)
        wire = check_wire(config, spec, result_dir, scalars)
        delays[config] = {can_id: scalars[f'ecuB[0].sinkApp[0]', f'id_{can_id}_delayMean'] for can_id in (256, 512)}
        entry = {'pdus_each': spec['pdus'], 'acf_messages_per_pdu': spec['per_pdu'], 'wire': wire,
                 'ethernet_background_delivered': background,
                 'ecuB_delay_mean_seconds': {str(k): v for k, v in delays[config].items()}}
        if spec['subtype'] == 0x05:
            slack = stats[app('gatewayB'), 'presentationSlack:stats']
            assert slack['count'] == spec['pdus'] and slack['min'] > 0 and slack['max'] < 500e-6, slack
            entry['presentation_slack_seconds'] = {'min': slack['min'], 'max': slack['max']}
            # Worst Ethernet transit gatewayA -> gatewayB = presentation offset - processing - minimum slack.
            entry['max_network_transit_seconds'] = spec['transit_ns'] * 1e-9 - PROCESSING_DELAY - slack['min']
            errors = [stats[app(gw), 'presentationError:stats'] for gw in MAC]
            entry['presentation_error_seconds'] = {'min': min(e['min'] for e in errors),
                                                   'max': max(e['max'] for e in errors)}
        report[config] = entry
    # Presentation time adds deterministic latency and hides Ethernet queueing:
    for can_id in (256, 512):
        assert delays['AvtpTscf'][can_id] > delays['AvtpNtscf'][can_id]
        assert abs(delays['AvtpLoadedEthernet'][can_id] - delays['AvtpTscf'][can_id]) < 1e-9
    # Without BRS the 64-byte FD frames (ID 512) take longer on both CAN buses.
    assert delays['AvtpFdNoBrs'][512] > delays['AvtpNtscf'][512]

    # 5. INET TSN. Strict priority + CBS bound the AVTP transit to one blocking
    # best-effort frame (no preemption), well below the untagged overload case.
    transit = {c: report[c]['max_network_transit_seconds'] for c in ('AvtpTscfOverload', 'AvtpTsn', 'AvtpTsnGptp')}
    assert transit['AvtpTsn'] < transit['AvtpTscfOverload'], transit
    assert transit['AvtpTsn'] < MAX_BEST_EFFORT_FRAME + 30e-6, transit
    assert transit['AvtpTsnGptp'] < MAX_BEST_EFFORT_FRAME + 30e-6, transit
    # Ideal clocks: release exactly at the intended instant. gPTP keeps +/-50 ppm
    # oscillators within 1 us; free-running clocks diverge by ~100 ppm * elapsed time.
    error = {c: report[c]['presentation_error_seconds'] for c in ('AvtpTsn', 'AvtpTsnGptp', 'AvtpTsnFreeRunning')}
    assert error['AvtpTsn'] == {'min': 0, 'max': 0}, error
    assert max(abs(v) for v in error['AvtpTsnGptp'].values()) < 1e-6, error
    assert max(abs(v) for v in error['AvtpTsnFreeRunning'].values()) > 5e-6, error
    report['tsn'] = {'max_network_transit_seconds': transit, 'presentation_error_seconds': error}

    # 4. negative scenarios
    negative = {}
    scalars, _, _ = run('AvtpNtscf', 'AvtpWrongStream', ('--*.gatewayB.app[0].listenStreamId="0x0200000000019999"',))
    assert scalars[app('gatewayB'), 'droppedStreamId'] == 20 and scalars[app('gatewayB'), 'avtpToCan'] == 0
    assert scalars['ecuB[0].sinkApp[0]', 'receivedFrames'] == 0 and scalars['ecuA[0].sinkApp[0]', 'receivedFrames'] == 20
    negative['wrong_stream_id'] = {'dropped': 20}
    scalars, _, _ = run('AvtpNtscf', 'AvtpWrongBus', ('--*.gatewayA.app[0].acceptCanBusId=5',))
    assert scalars[app('gatewayA'), 'droppedBusId'] == 20 and scalars['ecuA[0].sinkApp[0]', 'receivedFrames'] == 0
    assert scalars['ecuB[0].sinkApp[0]', 'receivedFrames'] == 20
    negative['wrong_can_bus_id'] = {'dropped': 20}
    scalars, _, _ = run('AvtpTscf', 'AvtpLateDrop', ('--*.gateway*.app[0].maxTransitTime=1us',
                                                      '--*.gateway*.app[0].latePresentationPolicy="drop"'))
    for gateway in MAC:
        assert scalars[app(gateway), 'latePresentations'] == 20 and scalars[app(gateway), 'droppedLate'] == 20
        assert scalars[app(gateway), 'avtpToCan'] == 0
    negative['late_presentation_drop'] = {'late_each': 20, 'dropped_each': 20}
    scalars, _, _ = run('AvtpTscf', 'AvtpLateForward', ('--*.gateway*.app[0].maxTransitTime=1us',))
    for gateway in MAC:
        assert scalars[app(gateway), 'latePresentations'] == 20 and scalars[app(gateway), 'avtpToCan'] == 20
    negative['late_presentation_forward'] = {'late_each': 20, 'forwarded_each': 20}
    report['negative'] = negative

    path = RESULTS / 'report.json'
    path.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    print('AVTP validation passed')


if __name__ == '__main__':
    main()
