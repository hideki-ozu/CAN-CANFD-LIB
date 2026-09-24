#!/usr/bin/env python3
"""IEEE 1722 AV streams (AAF PCM, IEC 61883-4 MPEG-2 TS, CRF) acceptance tests.

1. Codec self-test inside OMNeT++ (hand-written golden vectors, round trips,
   rejection of malformed PDUs, MPEG-2 TS / PCR / CRC helpers, PCM pattern).
2. Five network configurations (ideal, overloaded without TSN, TSN, TSN + gPTP,
   free-running clocks): delivery, content, continuity, presentation timing and
   media clock recovery at every listener.
3. Wire check of every captured AVTPDU: AAF and CRF against the COVESA Open1722
   reference decoder plus an independent Python parser; IEC 61883-4 (CIP header,
   source packets) and the MPEG-2 transport stream (PAT/PMT CRC, continuity counters,
   PCR, payload) with an independent Python parser written from the IEEE 1722 and
   ISO/IEC 13818-1 field tables. Sent and received frames must be identical.
4. Negative scenarios: wrong stream ID, late presentation with the drop policy.
"""
import json
import math
import os
import pathlib
import shlex
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
RESULTS = ROOT / 'results' / 'av'
OPEN1722 = ROOT / 'upstream' / 'Open1722'
DECODER = ROOT / '.local' / 'bin' / 'open1722_media_decode'
sys.path.insert(0, str(ROOT / 'tests'))
import test_avtp  # noqa: E402  (pcap reader)

TUNER = bytes.fromhex('020000000101')
STREAMS = {  # destination MAC -> (subtype, stream ID, SR class PCP)
    bytes.fromhex('91e0f000fe10'): ('aaf', 0x0200000001010001, 3),
    bytes.fromhex('91e0f000fe11'): ('ts', 0x0200000001010002, 2),
    bytes.fromhex('91e0f000fe12'): ('crf', 0x0200000001010003, 3),
}
LISTENERS = {'aaf': 'headUnit.app[0].listener[0]', 'ts': 'headUnit.app[0].listener[1]',
             'crf': 'headUnit.app[0].listener[2]', 'tsRear': 'rearDisplay.app[0].listener[0]'}
TALKERS = {'aaf': 'tuner.app[0].talker[0]', 'ts': 'tuner.app[0].talker[1]', 'crf': 'tuner.app[0].talker[2]'}
MEDIA_PPM = 25                      # tuner media clock against its gPTP clock
RATE, CHANNELS, SPP, STEP = 48000, 2, 6, 331
TS_BITRATE, TS_PACKET_NS = 16e6, 188 * 8 / 16e6 * 1e9
PCR_TICKS_PER_PACKET = 188 * 8 * 27000000 // 16000000
CONFIGS = {
    # name: (TSN, oscillator drift of tuner/headUnit/rearDisplay in ppm, synchronized)
    'AvBasic': (False, (0, 0, 0), True),
    'AvTsn': (True, (0, 0, 0), True),
    'AvTsnGptp': (True, (50, -50, 30), True),
    'AvTsnFreeRunning': (True, (50, -50, 30), False),
}
ERROR_COUNTERS = ('sequenceLost', 'sequenceOutOfOrder', 'droppedMalformedPdus', 'droppedStreamId', 'droppedSubtype',
                  'latePresentations', 'droppedLate')
CONTENT_COUNTERS = {
    'aaf': ('sampleErrors', 'sampleGaps', 'formatChanges', 'timestampInvalid'),
    'ts': ('syncErrors', 'continuityErrors', 'psiCrcErrors', 'payloadErrors', 'payloadMissing', 'unknownPid', 'dbcErrors'),
    'crf': ('crfNonMonotonic', 'crfParameterChanges', 'crfLateTimestamps'),
}


def run(config, name=None, extra=()):
    name = name or config
    result_dir = RESULTS / name
    if result_dir.exists():
        shutil.rmtree(result_dir)
    result = subprocess.run([str(ROOT / 'scripts/run-av.sh'), config, f'--result-dir={result_dir}', *extra],
                            cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, stdin=subprocess.DEVNULL)
    (ROOT / 'logs' / f'test-{name}.log').write_text(result.stdout)
    assert result.returncode == 0, result.stdout[-6000:]
    files = list(result_dir.glob('*.sca'))
    assert len(files) == 1, files
    scalars, stats, current = {}, {}, None
    for line in files[0].read_text().splitlines():
        if line.startswith('scalar '):
            _, module, key, value = shlex.split(line)
            try:
                scalars[module.removeprefix('AvNetwork.'), key] = float(value)
            except ValueError:
                pass
            current = None
        elif line.startswith('statistic '):
            _, module, key = shlex.split(line)
            current = stats.setdefault((module.removeprefix('AvNetwork.'), key), {})
        elif line.startswith('field ') and current is not None:
            _, field, value = shlex.split(line)
            current[field] = float(value)
    return scalars, stats, result_dir


# ---- independent wire parsers ------------------------------------------------------

def crc32_mpeg2(data):
    crc = 0xFFFFFFFF
    for byte in data:
        crc ^= byte << 24
        for _ in range(8):
            crc = ((crc << 1) ^ 0x04C11DB7) & 0xFFFFFFFF if crc & 0x80000000 else (crc << 1) & 0xFFFFFFFF
    return crc


def avtp_frames(path):
    """(dst, (pcp, vid) or None, AVTPDU) of every EtherType 0x22F0 frame sent by the tuner."""
    result = []
    for _, frame in test_avtp.read_pcap(path):
        if frame[6:12] != TUNER:
            continue
        ethertype, offset, vlan = int.from_bytes(frame[12:14], 'big'), 14, None
        if ethertype == 0x8100:
            tci = int.from_bytes(frame[14:16], 'big')
            vlan, ethertype, offset = (tci >> 13, tci & 0xfff), int.from_bytes(frame[16:18], 'big'), 18
        if ethertype == 0x22F0:
            result.append((frame[:6], vlan, frame[offset:-4]))
    return result


def parse_common(p):
    return {'subtype': p[0], 'sv': p[1] >> 7, 'version': (p[1] >> 4) & 7, 'mr': (p[1] >> 3) & 1,
            'sequence': p[2], 'stream_id': int.from_bytes(p[4:12], 'big')}


def parse_aaf(p):
    out = parse_common(p)
    out.update(rsv=(p[1] >> 1) & 3, tv=p[1] & 1, reserved1=p[3] >> 1, tu=p[3] & 1,
               avtp_timestamp=int.from_bytes(p[12:16], 'big'), format=p[16], nsr=p[17] >> 4, rsv2=(p[17] >> 2) & 3,
               channels=int.from_bytes(p[17:19], 'big') & 0x3ff, bit_depth=p[19],
               data_length=int.from_bytes(p[20:22], 'big'), rsv3=p[22] >> 5, sp=(p[22] >> 4) & 1, evt=p[22] & 15,
               reserved2=p[23])
    out['samples'] = p[24:24 + out['data_length']]
    return out


def parse_crf(p):
    out = parse_common(p)
    word = int.from_bytes(p[12:16], 'big')
    out.update(r=(p[1] >> 2) & 1, fs=(p[1] >> 1) & 1, tu=p[1] & 1, type=p[3], pull=word >> 29,
               base_frequency=word & 0x1fffffff, data_length=int.from_bytes(p[16:18], 'big'),
               timestamp_interval=int.from_bytes(p[18:20], 'big'))
    out['timestamps'] = [int.from_bytes(p[20 + 8 * i:28 + 8 * i], 'big') for i in range(out['data_length'] // 8)]
    return out


def parse_61883(p):
    out = parse_common(p)
    out.update(r=(p[1] >> 2) & 1, gv=(p[1] >> 1) & 1, tv=p[1] & 1, reserved=p[3] >> 1, tu=p[3] & 1,
               avtp_timestamp=int.from_bytes(p[12:16], 'big'), gateway_info=int.from_bytes(p[16:20], 'big'),
               data_length=int.from_bytes(p[20:22], 'big'), tag=p[22] >> 6, channel=p[22] & 0x3f,
               tcode=p[23] >> 4, sy=p[23] & 15)
    cip = p[24:32]  # IEC 61883-1 CIP header
    out.update(qi1=cip[0] >> 6, sid=cip[0] & 0x3f, dbs=cip[1], fn=cip[2] >> 6, qpc=(cip[2] >> 3) & 7,
               sph=(cip[2] >> 2) & 1, cip_rsv=cip[2] & 3, dbc=cip[3], qi2=cip[4] >> 6, fmt=cip[4] & 0x3f,
               tsf=cip[5] >> 7, fdf_rsv=int.from_bytes(cip[5:8], 'big') & 0x7fffff)
    body = p[32:24 + out['data_length']]
    out['source_packets'] = [(int.from_bytes(body[i:i + 4], 'big'), body[i + 4:i + 192]) for i in range(0, len(body), 192)]
    out['body_length'] = len(body)
    return out


def parse_ts(ts):
    """ISO/IEC 13818-1 transport packet header, adaptation field (PCR) and payload offset."""
    out = {'sync': ts[0], 'tei': ts[1] >> 7, 'pusi': (ts[1] >> 6) & 1, 'pid': ((ts[1] & 0x1f) << 8) | ts[2],
           'scrambling': ts[3] >> 6, 'afc': (ts[3] >> 4) & 3, 'cc': ts[3] & 15, 'pcr': None}
    offset = 4
    if out['afc'] & 2:
        length = ts[4]
        if length and ts[5] & 0x10:
            b = ts[6:12]
            base = (b[0] << 25) | (b[1] << 17) | (b[2] << 9) | (b[3] << 1) | (b[4] >> 7)
            assert (b[4] >> 1) & 0x3f == 0x3f          # reserved bits
            out['pcr'] = base * 300 + (((b[4] & 1) << 8) | b[5])
        offset += 1 + length
    out['payload'] = offset
    return out


def build_decoder():
    assert (OPEN1722 / 'include' / 'avtp' / 'aaf' / 'Pcm.h').exists(), 'upstream/Open1722 missing: run scripts/fetch-sources.py'
    DECODER.parent.mkdir(parents=True, exist_ok=True)
    compiler = os.environ.get('CC') or shutil.which('cc') or shutil.which('gcc') or shutil.which('clang')
    assert compiler, 'A C compiler is required for the Open1722 cross-check'
    subprocess.run([compiler, '-std=c11', '-O1', '-Wall', f'-I{OPEN1722 / "include"}', str(ROOT / 'tests/av/open1722_media_decode.c'),
                    str(OPEN1722 / 'src/avtp/Utils.c'), str(OPEN1722 / 'src/avtp/CommonHeader.c'), '-o', str(DECODER)], check=True)


def open1722(pdus):
    completed = subprocess.run([str(DECODER)], input=''.join(p.hex() + '\n' for p in pdus), stdout=subprocess.PIPE,
                               text=True, check=True)
    return [json.loads(line) for line in completed.stdout.splitlines()]


def pcm_sample(n, c, depth=16):
    raw = ((n + 1000 * c) * STEP) % (1 << depth)
    return raw - (1 << depth) if raw >= 1 << (depth - 1) else raw


def check_aaf(pdus, stream_id):
    parsed = [parse_aaf(p) for p in pdus]
    reference = open1722(pdus)
    for i, (ours, theirs) in enumerate(zip(parsed, reference)):
        assert theirs['valid'] is True, theirs
        for key in ('sv', 'mr', 'tv', 'tu', 'sequence', 'stream_id', 'avtp_timestamp', 'format', 'nsr', 'channels',
                    'bit_depth', 'data_length', 'sp', 'evt'):
            assert ours[key] == theirs[key], (key, ours[key], theirs[key])
        assert (ours['subtype'], ours['version'], ours['sv'], ours['tv'], ours['stream_id']) == (2, 0, 1, 1, stream_id)
        assert (ours['rsv'], ours['reserved1'], ours['rsv2'], ours['rsv3'], ours['reserved2']) == (0, 0, 0, 0, 0)
        assert (ours['format'], ours['nsr'], ours['channels'], ours['bit_depth']) == (4, 5, CHANNELS, 16)
        assert ours['data_length'] == SPP * CHANNELS * 2 and ours['sequence'] == i % 256
        samples = [int.from_bytes(ours['samples'][k:k + 2], 'big', signed=True) for k in range(0, len(ours['samples']), 2)]
        assert samples == [pcm_sample(i * SPP + f, c) for f in range(SPP) for c in range(CHANNELS)], i
    # Presentation time of the first sample: consecutive PDUs are 6 samples of the
    # (+25 ppm) media clock apart on the talker's gPTP clock.
    spacing = SPP / RATE / (1 + MEDIA_PPM * 1e-6) * 1e9
    for a, b in zip(parsed, parsed[1:]):
        assert abs(((b['avtp_timestamp'] - a['avtp_timestamp']) % 2**32) - spacing) <= 1, (a['avtp_timestamp'], b['avtp_timestamp'])
    return len(parsed)


def check_crf(pdus, stream_id):
    parsed = [parse_crf(p) for p in pdus]
    reference = open1722(pdus)
    interval = 160 / RATE / (1 + MEDIA_PPM * 1e-6) * 1e9
    previous = None
    for i, (ours, theirs) in enumerate(zip(parsed, reference)):
        assert theirs['valid'] is True, theirs
        for key in ('sv', 'mr', 'fs', 'tu', 'sequence', 'type', 'stream_id', 'pull', 'base_frequency', 'data_length',
                    'timestamp_interval'):
            assert ours[key] == theirs[key], (key, ours[key], theirs[key])
        assert (ours['subtype'], ours['version'], ours['sv'], ours['r'], ours['stream_id']) == (4, 0, 1, 0, stream_id)
        assert (ours['type'], ours['pull'], ours['base_frequency'], ours['timestamp_interval'], ours['data_length']) == (1, 0, RATE, 160, 48)
        for t in ours['timestamps']:
            if previous is not None:
                assert abs(t - previous - interval) <= 1, (t, previous)
            previous = t
    return len(parsed)


def check_ts(pdus, stream_id, talker_sent):
    parsed = [parse_61883(p) for p in pdus]
    reference = open1722(pdus)        # common header only
    dbc, cc, previous_sph, index, pcrs, psi = 0, {}, None, 0, 0, {0: 0, 0x1000: 0}
    for i, (ours, theirs) in enumerate(zip(parsed, reference)):
        assert (theirs['subtype'], theirs['version']) == (0, 0)
        assert (ours['sv'], ours['tv'], ours['gv'], ours['r'], ours['reserved'], ours['tu'], ours['stream_id']) == (1, 1, 0, 0, 0, 0, stream_id)
        assert (ours['tag'], ours['channel'], ours['tcode'], ours['sy']) == (1, 31, 0x0A, 0)
        assert (ours['qi1'], ours['sid'], ours['dbs'], ours['fn'], ours['qpc'], ours['sph'], ours['cip_rsv']) == (0, 63, 6, 3, 0, 1, 0)
        assert (ours['qi2'], ours['fmt'], ours['tsf'], ours['fdf_rsv']) == (2, 0x20, 0, 0)
        assert ours['body_length'] == 192 * len(ours['source_packets']) and 1 <= len(ours['source_packets']) <= 7
        assert ours['dbc'] == dbc and ours['sequence'] == i % 256
        dbc = (dbc + 8 * len(ours['source_packets'])) % 256
        assert ours['avtp_timestamp'] == ours['source_packets'][0][0]
        for sph, ts in ours['source_packets']:
            if previous_sph is not None:
                assert abs(((sph - previous_sph) % 2**32) - TS_PACKET_NS / (1 + MEDIA_PPM * 1e-6)) <= 1
            previous_sph = sph
            h = parse_ts(ts)
            assert len(ts) == 188 and h['sync'] == 0x47 and h['tei'] == 0 and h['scrambling'] == 0
            if h['afc'] & 1:
                if h['pid'] in cc:
                    assert h['cc'] == (cc[h['pid']] + 1) % 16, (index, h)
                cc[h['pid']] = h['cc']
            if h['pid'] in psi:
                assert index % 1000 == (0 if h['pid'] == 0 else 1) and h['pusi'] == 1 and ts[4] == 0
                length = ((ts[6] & 0x0f) << 8) | ts[7]
                section = ts[5:8 + length]
                assert crc32_mpeg2(section) == 0, 'PSI CRC'
                if h['pid'] == 0:     # PAT: program 1 -> PMT PID 0x1000
                    assert section[0] == 0 and section[8:12] == bytes.fromhex('0001f000')
                else:                 # PMT: PCR PID 0x100, H.264 on 0x100, AAC on 0x110
                    assert section[0] == 2 and section[8:10] == bytes.fromhex('e100')
                    assert section[12:22] == bytes.fromhex('1be100f0000fe110f000')
                assert all(b == 0xFF for b in ts[8 + length:])
                psi[h['pid']] += 1
            else:
                assert h['pid'] == (0x110 if index % 10 == 9 else 0x100), (index, h['pid'])
                if h['pcr'] is not None:
                    # k-th PCR due at packet 2 + 397 k (~37 ms), carried by the next video packet
                    assert h['pcr'] == index * PCR_TICKS_PER_PACKET
                    assert 0 <= index - (2 + 397 * pcrs) <= 3, (index, pcrs)
                    pcrs += 1
                p = h['payload']
                assert int.from_bytes(ts[p:p + 4], 'big') == index
                assert all(ts[j] == (index + j) & 0xFF for j in range(p + 4, 188))
            index += 1
    assert talker_sent - 7 <= index <= talker_sent, (index, talker_sent)
    return {'pdus': len(parsed), 'ts_packets': index, 'pcr': pcrs, 'pat': psi[0], 'pmt': psi[0x1000]}


def check_wire(config, result_dir, scalars, tsn):
    sent = avtp_frames(result_dir / 'tuner.pcap')
    summary = {}
    for dst, (kind, stream_id, pcp) in STREAMS.items():
        frames = [(vlan, pdu) for d, vlan, pdu in sent if d == dst]
        assert all(vlan == ((pcp, 2) if tsn else None) for vlan, _ in frames), (config, kind)
        pdus = [pdu for _, pdu in frames]
        # The last PDU may still be queued in the talker's egress path at the end.
        assert 0 <= scalars[TALKERS[kind], 'avtpPdusSent'] - len(pdus) <= 1, (config, kind, len(pdus))
        if kind == 'aaf':
            summary[kind] = check_aaf(pdus, stream_id)
        elif kind == 'crf':
            summary[kind] = check_crf(pdus, stream_id)
        else:
            summary[kind] = check_ts(pdus, stream_id, scalars[TALKERS['ts'], 'tsPacketsSent'])
        # Frames arrive byte-identical at every listener (prefix: the last ones may be in flight).
        for node in ('headUnit', 'rearDisplay'):
            if node == 'rearDisplay' and (kind != 'ts' and tsn):
                continue
            received = [(v, p) for d, v, p in avtp_frames(result_dir / f'{node}.pcap') if d == dst]
            assert received == frames[:len(received)] and len(frames) - len(received) <= 2, (config, node, kind)
    return summary


# ---- network runs -----------------------------------------------------------------------

def stat(stats, module, name, field):
    return stats.get((module, f'{name}:stats'), {}).get(field, 0.0)


def check_run(config, scalars, stats):
    tsn, drift, synchronized = CONFIGS[config]
    result = {}
    for kind, module in LISTENERS.items():
        base = 'ts' if kind == 'tsRear' else kind
        for key in ERROR_COUNTERS + CONTENT_COUNTERS[base]:
            assert scalars[module, key] == 0, (config, module, key, scalars[module, key])
        received, sent = scalars[module, 'avtpPdusReceived'], scalars[TALKERS[base], 'avtpPdusSent']
        assert sent - 2 <= received <= sent, (config, module, received, sent)
        result[kind] = {'pdus': int(received)}
    # Content delivered up to the presentation time of the last PDU in flight.
    aaf, ts, crf = LISTENERS['aaf'], LISTENERS['ts'], LISTENERS['crf']
    assert abs(scalars[aaf, 'samplesPlayed'] - scalars[aaf, 'avtpPdusReceived'] * SPP) <= 2 * 17 * SPP   # <= 2 ms in flight
    for module in (ts, LISTENERS['tsRear']):
        missing = scalars[TALKERS['ts'], 'tsPacketsSent'] - scalars[module, 'tsPacketsOutput']
        assert 0 <= missing <= 0.051 / (TS_PACKET_NS * 1e-9) + 8, (config, module, missing)   # 50 ms presentation offset
        assert scalars[module, 'patReceived'] >= 9 and scalars[module, 'pmtReceived'] >= 9 and scalars[module, 'pcrReceived'] >= 20
        assert scalars[module, 'pcrJitterMax'] < 5e-9, (config, module)
    assert scalars[crf, 'crfTimestampsReceived'] == 6 * scalars[crf, 'avtpPdusReceived']
    # Media clock: timestamps carry the talker's 25 ppm; physically the talker produces at
    # 25 ppm plus its oscillator drift; listeners must play out at that rate when synchronized.
    for key, module in (('recoveredRatePpm', aaf), ('recoveredSystemClockPpm', ts), ('recoveredMediaClockPpm', crf)):
        assert abs(scalars[module, key] - MEDIA_PPM) < 0.05, (config, module, key, scalars[module, key])
    production = MEDIA_PPM + drift[0]
    for key, module in (('productionRatePpm', TALKERS['aaf']), ('productionSystemClockPpm', TALKERS['ts']),
                        ('productionMediaClockPpm', TALKERS['crf'])):
        assert abs(scalars[module, key] - production) < 0.05, (config, module, key, scalars[module, key])
    physical = {'aaf': scalars[aaf, 'playoutRatePpm'], 'ts': scalars[ts, 'outputSystemClockPpm'],
                'crf': scalars[crf, 'regeneratedMediaClockPpm'], 'tsRear': scalars[LISTENERS['tsRear'], 'outputSystemClockPpm']}
    for kind, value in physical.items():
        node_drift = drift[2] if kind == 'tsRear' else drift[1]
        # A free-running listener presents the talker's timestamp values on its own clock.
        expected = production if synchronized else ((1 + MEDIA_PPM * 1e-6) * (1 + node_drift * 1e-6) - 1) * 1e6
        assert abs(value - expected) < 1.0, (config, kind, value, expected)
        result[kind]['physical_rate_ppm'] = round(value, 3)
    # Presentation timing
    for kind, module in LISTENERS.items():
        if kind == 'crf':
            continue
        low, high = stat(stats, module, 'presentationError', 'min'), stat(stats, module, 'presentationError', 'max')
        if drift == (0, 0, 0):
            assert low == high == 0, (config, module, low, high)
        elif synchronized:
            assert max(abs(low), abs(high)) < 2e-6, (config, module, low, high)
        else:
            assert max(abs(low), abs(high)) > 1e-5, (config, module, low, high)
        result[kind]['presentation_error_ns'] = [round(low * 1e9), round(high * 1e9)]
        slack = stat(stats, module, 'presentationSlack', 'min')
        transit = (2e-3 if kind == 'aaf' else 50e-3) - 5e-6 - slack
        assert 0 < transit < (1e-3 if tsn else 5e-4), (config, module, transit)
        result[kind]['max_transit_us'] = round(transit * 1e6, 1)
    return result


def main():
    (ROOT / 'logs').mkdir(exist_ok=True)
    RESULTS.mkdir(parents=True, exist_ok=True)
    build_decoder()
    report = {}

    selftest_dir = RESULTS / 'selftest'
    completed = subprocess.run(
        ['bash', '-c', 'set -e; source "$1/scripts/env.sh"; set -u; cd "$1/tests/av"; '
         'exec opp_run -u Cmdenv -n "$1/tests:$INET_ROOT/src:$1/upstream/FiCo4OMNeT/src:$1/upstream/SignalsAndGateways/src-inet4" '
         '-l "$INET_ROOT/src/INET" -l "$1/upstream/FiCo4OMNeT/src/FiCo4OMNeT" '
         '-l "$1/upstream/SignalsAndGateways/src-inet4/SignalsAndGateways_INET4" -f selftest.ini --result-dir="$2"',
         'av-selftest', str(ROOT), str(selftest_dir)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    (ROOT / 'logs' / 'test-AvSelfTest.log').write_text(completed.stdout)
    assert completed.returncode == 0, completed.stdout[-4000:]
    sca = next(selftest_dir.glob('*.sca')).read_text()
    passed = int(float(next(l.split()[-1] for l in sca.splitlines() if ' checksPassed ' in l)))
    failed = int(float(next(l.split()[-1] for l in sca.splitlines() if ' checksFailed ' in l)))
    assert failed == 0 and passed >= 60, completed.stdout[-4000:]
    report['codec_selftest'] = {'passed': passed, 'failed': failed}

    for config, (tsn, _, _) in CONFIGS.items():
        scalars, stats, result_dir = run(config)
        report[config] = check_run(config, scalars, stats)
        if config in ('AvBasic', 'AvTsnGptp'):
            report[config]['wire'] = check_wire(config, result_dir, scalars, tsn)

    # Without TSN the overloaded switch egress delays and drops AV frames.
    scalars, stats, _ = run('AvOverload')
    aaf, ts = LISTENERS['aaf'], LISTENERS['ts']
    assert scalars[aaf, 'latePresentations'] > 100 and scalars[aaf, 'sequenceLost'] > 0
    assert scalars[ts, 'sequenceLost'] > 0 and scalars[ts, 'continuityErrors'] > 0
    report['AvOverload'] = {f'{kind}.{key}': int(scalars[m, key]) for kind, m, key in (
        ('aaf', aaf, 'latePresentations'), ('aaf', aaf, 'sequenceLost'), ('ts', ts, 'continuityErrors'), ('ts', ts, 'sequenceLost'))}

    # Negative: a listener configured for another stream ID discards everything.
    scalars, _, _ = run('AvBasic', 'AvWrongStreamId', ['--*.headUnit.app[0].listener[0].listenStreamId="0x0200000001010009"'])
    assert scalars[aaf, 'droppedStreamId'] == scalars[aaf, 'avtpPdusReceived'] > 0 and scalars[aaf, 'samplesPlayed'] == 0
    # Negative: a 1 us presentation offset cannot be met; the drop policy discards the audio.
    scalars, _, _ = run('AvBasic', 'AvLateDrop', ['--*.tuner.app[0].talker[0].maxTransitTime=1us',
                                                  '--*.headUnit.app[0].listener[0].latePresentationPolicy="drop"'])
    assert scalars[aaf, 'droppedLate'] == scalars[aaf, 'avtpPdusReceived'] > 0 and scalars[aaf, 'samplesPlayed'] == 0
    report['negative'] = {'wrong_stream_id': 'all dropped', 'late_drop': 'all dropped'}

    (RESULTS / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    print('AV stream tests passed')


if __name__ == '__main__':
    main()
