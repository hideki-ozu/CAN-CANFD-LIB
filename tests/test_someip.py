#!/usr/bin/env python3
"""SOME/IP and SOME/IP-SD acceptance tests for the SOA4CoRE INET4 port.

1. Codec self-test inside OMNeT++ (golden vectors, INET round trips, malformed input).
2. Three service configurations (TCP+UDP, UDP only, UDP multicast): delivery counts,
   SOME/IP header validation, session gaps, SD message validity.
3. Wire check of the recorded pcap: an independent Python parser written from the
   AUTOSAR PRS field tables, and Scapy's SOME/IP / SD implementation as reference.
4. Negative scenarios: eventgroup mismatch, unknown service, instance mismatch.
5. INET TSN devices: publisher pcp/vlan_id become IEEE 802.1Q C-tags on UDP notifications.
"""
import json
import os
import pathlib
import shlex
import shutil
import struct
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
RESULTS = ROOT / 'results' / 'someip'
VENV = ROOT / '.local' / 'venv-someip-test'
REQUIREMENTS = ROOT / 'tests' / 'someiptest' / 'requirements.txt'

IP = {'Node1': '10.0.0.1', 'Node2': '10.0.0.2', 'Node3': '10.0.0.3'}
SD_PORT, SD_GROUP = 30490, '224.0.2.254'
MCAST_GROUP, MCAST_PORT = '225.0.1.42', 13171
PUBLISHER_PORT, PAYLOAD = 3171, 64
SUBSCRIBER_PORT = {'Node2': 3172, 'Node3': 3173}
PUBLISHED, DELIVERED = 50, 48     # first two messages precede the subscription
CONFIGS = {
    'SomeIpTcpUdp': {'Node2': 'tcp', 'Node3': 'udp'},
    'SomeIpUdpOnly': {'Node2': 'udp', 'Node3': 'udp'},
    'SomeIpUdpMcast': {'Node2': 'mcast', 'Node3': 'mcast'},
}


def run(config, name=None, extra=()):
    name = name or config
    result_dir = RESULTS / name
    if result_dir.exists():
        shutil.rmtree(result_dir)
    result = subprocess.run([str(ROOT / 'scripts/run-someip.sh'), config, f'--result-dir={result_dir}', *extra],
                            cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, stdin=subprocess.DEVNULL)
    (ROOT / 'logs' / f'test-{name}.log').write_text(result.stdout)
    assert result.returncode == 0, result.stdout[-6000:]
    files = list(result_dir.glob('*.sca'))
    assert len(files) == 1, files
    scalars, stats, current = {}, {}, None
    for line in files[0].read_text().splitlines():
        if line.startswith('scalar '):
            _, module, key, value = shlex.split(line)
            scalars[module.removeprefix('SomeIpSmallNetwork.'), key] = float(value)
            current = None
        elif line.startswith('statistic '):
            _, module, key = shlex.split(line)
            current = stats.setdefault((module.removeprefix('SomeIpSmallNetwork.'), key), {})
        elif line.startswith('field ') and current is not None:
            _, field, value = shlex.split(line)
            current[field] = float(value)
    return scalars, stats, result_dir


def ensure_scapy():
    """Scapy (GPL-2.0) is a test-only reference decoder in a private venv, pinned by hash."""
    python = VENV / 'bin' / 'python'
    probe = [str(python), '-c', 'import scapy; print(scapy.__version__)']
    if python.exists() and subprocess.run(probe, stdout=subprocess.PIPE, text=True).stdout.strip() == '2.6.1':
        return python
    if VENV.exists():
        shutil.rmtree(VENV)
    subprocess.run([sys.executable, '-m', 'venv', str(VENV)], check=True)
    subprocess.run([str(python), '-m', 'pip', 'install', '-q', '--require-hashes', '-r', str(REQUIREMENTS)], check=True)
    return python


# ---- independent SOME/IP (PRS_SOMEIP / PRS_SOMEIPSD) parser ------------------------

def read_pcap(path):
    data = path.read_bytes()
    assert struct.unpack('<I', data[:4])[0] == 0xa1b23c4d and struct.unpack('<I', data[20:24])[0] == 1
    offset, frames = 24, []
    while offset < len(data):
        seconds, nanos, captured, _ = struct.unpack('<IIII', data[offset:offset + 16])
        offset += 16
        frames.append((seconds * 1_000_000_000 + nanos, data[offset:offset + captured]))
        offset += captured
    return frames


def ip_packets(path, with_vlan=False):
    """(time, protocol, src, sport, dst, dport, l4 payload, tcp seq[, (pcp, vid)]) of IPv4 UDP/TCP frames."""
    result = []
    for time_ns, frame in read_pcap(path):
        ethertype, offset, vlan = int.from_bytes(frame[12:14], 'big'), 14, None
        if ethertype == 0x8100:
            tci = int.from_bytes(frame[14:16], 'big')
            vlan, ethertype, offset = (tci >> 13, tci & 0xfff), int.from_bytes(frame[16:18], 'big'), 18
        if ethertype != 0x0800:
            continue
        ip = frame[offset:-4]
        ihl = (ip[0] & 15) * 4
        total = int.from_bytes(ip[2:4], 'big')
        protocol, src, dst = ip[9], '.'.join(map(str, ip[12:16])), '.'.join(map(str, ip[16:20]))
        l4 = ip[ihl:total]
        if protocol == 17:
            sport, dport, length = struct.unpack('>HHH', l4[:6])
            result.append((time_ns, 'udp', src, sport, dst, dport, l4[8:length], None) + ((vlan,) if with_vlan else ()))
        elif protocol == 6:
            sport, dport, seq = struct.unpack('>HHI', l4[:8])
            offset = (l4[12] >> 4) * 4
            result.append((time_ns, 'tcp', src, sport, dst, dport, l4[offset:], seq) + ((vlan,) if with_vlan else ()))
    return result


def parse_someip(data):
    service, method, length, client, session, pv, iv, mtype, rc = struct.unpack('>HHIHHBBBB', data[:16])
    return {'service': service, 'method': method, 'length': length, 'client': client, 'session': session,
            'protocol_version': pv, 'interface_version': iv, 'message_type': mtype, 'return_code': rc,
            'payload': data[16:8 + length], 'size': 8 + length}


def parse_sd(data):
    msg = parse_someip(data)
    assert msg['size'] == len(data), (msg['size'], len(data))
    body = data[16:]
    msg['flags'], msg['reserved'] = body[0], body[1:4]
    entries_length = int.from_bytes(body[4:8], 'big')
    assert entries_length % 16 == 0
    entries = []
    for i in range(entries_length // 16):
        e = body[8 + 16 * i:24 + 16 * i]
        entry = {'type': e[0], 'index1': e[1], 'index2': e[2], 'n1': e[3] >> 4, 'n2': e[3] & 15,
                 'service': int.from_bytes(e[4:6], 'big'), 'instance': int.from_bytes(e[6:8], 'big'),
                 'major': e[8], 'ttl': int.from_bytes(e[9:12], 'big')}
        if entry['type'] in (0x00, 0x01):
            entry['minor'] = int.from_bytes(e[12:16], 'big')
        else:
            entry['reserved'] = (e[12] << 4) | (e[13] >> 4)
            entry['counter'] = e[13] & 15
            entry['eventgroup'] = int.from_bytes(e[14:16], 'big')
        entries.append(entry)
    offset = 8 + entries_length
    options_length = int.from_bytes(body[offset:offset + 4], 'big')
    offset += 4
    end = offset + options_length
    assert end == len(body), (end, len(body))
    options = []
    while offset < end:
        length = int.from_bytes(body[offset:offset + 2], 'big')
        otype, reserved = body[offset + 2], body[offset + 3]
        content = body[offset + 4:offset + 3 + length]
        option = {'type': otype, 'length': length, 'reserved': reserved}
        if otype in (0x04, 0x14, 0x24):
            assert length == 9
            option.update(address='.'.join(map(str, content[0:4])), reserved2=content[4], l4=content[5],
                          port=int.from_bytes(content[6:8], 'big'))
        elif otype == 0x01:
            option['config'] = content
        options.append(option)
        offset += 3 + length
    msg['entries'], msg['options'] = entries, options
    return msg


def scapy_decode(python, payloads):
    """Decode UDP payloads with Scapy's SOME/IP implementation (reference, test-only)."""
    script = r'''
import json, sys
from scapy.contrib.automotive.someip import SOMEIP, SD
out = []
for line in sys.stdin:
    raw = bytes.fromhex(line.strip())
    msg = SOMEIP(raw)
    item = {"service": msg.srv_id, "method": msg.sub_id, "length": msg.len, "client": msg.client_id,
            "session": msg.session_id, "protocol_version": msg.proto_ver, "interface_version": msg.iface_ver,
            "message_type": int(msg.msg_type), "return_code": int(msg.retcode)}
    if msg.srv_id == 0xFFFF and msg.sub_id == 0x8100:
        sd = SD(raw[16:])
        item["flags"] = int(sd.flags)
        item["entries"] = [{"type": e.type, "service": e.srv_id, "instance": e.inst_id, "major": e.major_ver,
                            "ttl": e.ttl, "n1": e.n_opt_1, "index1": e.index_1,
                            **({"minor": e.minor_ver} if e.type in (0, 1) else {"eventgroup": e.eventgroup_id, "counter": e.cnt})}
                           for e in sd.entry_array]
        item["options"] = [{"type": o.type, **({"address": o.addr, "l4": o.l4_proto, "port": o.port} if o.type in (0x04, 0x14, 0x24) else {})}
                           for o in sd.option_array]
    else:
        item["payload_length"] = len(bytes(msg.payload))
    out.append(item)
json.dump(out, sys.stdout)
'''
    completed = subprocess.run([str(python), '-c', script], input=''.join(p.hex() + '\n' for p in payloads),
                               stdout=subprocess.PIPE, text=True, check=True)
    return json.loads(completed.stdout)


def check_sd_message(msg, sender):
    assert (msg['service'], msg['method'], msg['client']) == (0xFFFF, 0x8100, 0x0000)
    assert (msg['protocol_version'], msg['interface_version'], msg['message_type'], msg['return_code']) == (1, 1, 0x02, 0)
    assert msg['flags'] == 0xC0 and msg['reserved'] == b'\x00\x00\x00'   # reboot (no wrap yet) + unicast
    assert msg['session'] >= 1
    for entry in msg['entries']:
        assert entry['index1'] + entry['n1'] <= len(msg['options']) and entry['n2'] == 0
        assert entry['service'] == 1 and entry['major'] == 0xFF and entry['ttl'] == 0xFFFFFF
        if entry['type'] in (0x00, 0x01):
            assert entry['minor'] == 0xFFFFFFFF
        else:
            assert entry['reserved'] == 0 and entry['counter'] == 0 and entry['eventgroup'] == 1
    for option in msg['options']:
        assert option['reserved'] == 0 and option.get('reserved2', 0) == 0


def check_wire(config, result_dir, python):
    transports = CONFIGS[config]
    captures = {node: ip_packets(result_dir / f'{node}.pcap') for node in IP}
    summary = {'sd_messages': 0, 'events': {}}
    # ---- SOME/IP-SD: every datagram each node transmitted
    sd_payloads, sd_parsed, sessions = [], [], {}
    for node, packets in captures.items():
        for time_ns, proto, src, sport, dst, dport, payload, _ in packets:
            if proto == 'udp' and src == IP[node] and sport == SD_PORT:
                assert dport == SD_PORT
                msg = parse_sd(payload)
                check_sd_message(msg, node)
                # PRS_SOMEIPSD: separate session counters for multicast and each unicast peer
                key = (src, 'multicast' if dst == SD_GROUP else dst)
                sessions.setdefault(key, []).append(msg['session'])
                msg.update(time=time_ns, src=src, dst=dst)
                sd_payloads.append(payload)
                sd_parsed.append(msg)
    for key, values in sessions.items():
        assert values == list(range(1, len(values) + 1)), (config, key, values)
    summary['sd_messages'] = len(sd_parsed)
    offers = [m for m in sd_parsed if m['src'] == IP['Node1'] and any(e['type'] == 0x01 for e in m['entries'])]
    assert offers
    for offer in offers:
        endpoints = {(o['type'], o['address'], o['l4'], o['port']) for o in offer['options']}
        assert endpoints == {(0x04, IP['Node1'], 0x11, PUBLISHER_PORT), (0x04, IP['Node1'], 0x06, PUBLISHER_PORT),
                             (0x14, MCAST_GROUP, 0x11, MCAST_PORT)}, endpoints
        assert offer['entries'][0]['n1'] == 3
    for node, transport in transports.items():
        finds = [m for m in sd_parsed if m['src'] == IP[node] and any(e['type'] == 0x00 for e in m['entries'])]
        assert finds and all(m['dst'] == SD_GROUP for m in finds)
        subscribes = [m for m in sd_parsed if m['src'] == IP[node] and any(e['type'] == 0x06 for e in m['entries'])]
        acks = [m for m in sd_parsed if m['src'] == IP['Node1'] and m['dst'] == IP[node]
                and any(e['type'] == 0x07 for e in m['entries'])]
        assert subscribes and acks and all(m['dst'] == IP['Node1'] for m in subscribes)
        expected = {'tcp': (0x04, IP[node], 0x06, SUBSCRIBER_PORT[node]),
                    'udp': (0x04, IP[node], 0x11, SUBSCRIBER_PORT[node]),
                    'mcast': (0x14, MCAST_GROUP, 0x11, MCAST_PORT)}[transport]
        for sub in subscribes:
            assert [(o['type'], o['address'], o['l4'], o['port']) for o in sub['options']] == [expected], sub['options']
        if transport == 'mcast':
            for ack in acks:
                assert [(o['type'], o['address'], o['l4'], o['port']) for o in ack['options']] == [expected]
        first_offer_to_node = min(m['time'] for m in sd_parsed if m['src'] == IP['Node1'] and m in offers
                                  and m['dst'] in (IP[node], SD_GROUP))
        assert first_offer_to_node < min(m['time'] for m in subscribes) < min(m['time'] for m in acks)
        # ---- events
        if transport == 'tcp':
            segments = sorted({seq: data for _, proto, src, sp, dst, dp, data, seq in captures['Node1']
                               if proto == 'tcp' and src == IP['Node1'] and dst == IP[node] and data}.items())
            stream = b''.join(data for _, data in segments)
            events, offset = [], 0
            while offset < len(stream):
                msg = parse_someip(stream[offset:])
                events.append(msg)
                offset += msg['size']
            assert offset == len(stream)
            times = [t for t, proto, src, sp, dst, dp, data, _ in captures['Node1'] if proto == 'tcp' and src == IP['Node1']
                     and dst == IP[node] and data]
        else:
            dst_ip, dst_port = (MCAST_GROUP, MCAST_PORT) if transport == 'mcast' else (IP[node], SUBSCRIBER_PORT[node])
            received = [(t, p) for t, proto, src, sp, dst, dp, p, _ in captures[node]
                        if proto == 'udp' and src == IP['Node1'] and sp == PUBLISHER_PORT and dst == dst_ip and dp == dst_port]
            events = [parse_someip(p) for _, p in received]
            times = [t for t, _ in received]
            reference = scapy_decode(python, [p for _, p in received])
            for ours, theirs in zip(events, reference):
                for key in ('service', 'method', 'length', 'client', 'session', 'protocol_version',
                            'interface_version', 'message_type', 'return_code'):
                    assert ours[key] == theirs[key], (config, key, ours[key], theirs[key])
                assert theirs['payload_length'] == PAYLOAD
        assert len(events) == DELIVERED, (config, node, len(events))
        for msg in events:
            assert (msg['service'], msg['method'], msg['client']) == (1, 0x8001, 0)
            assert (msg['protocol_version'], msg['interface_version'], msg['message_type'], msg['return_code']) == (1, 1, 0x02, 0)
            assert msg['length'] == 8 + PAYLOAD and msg['payload'] == bytes(PAYLOAD)
        sessions_seen = [m['session'] for m in events]
        assert sessions_seen == list(range(sessions_seen[0], sessions_seen[0] + DELIVERED)), sessions_seen
        assert min(times) > min(m['time'] for m in acks)
        summary['events'][node] = {'transport': transport, 'count': len(events), 'first_session': sessions_seen[0]}
    # ---- Scapy cross-check of every SD message
    for ours, theirs in zip(sd_parsed, scapy_decode(python, sd_payloads)):
        for key in ('service', 'method', 'length', 'client', 'session', 'message_type', 'flags'):
            assert ours[key] == theirs[key], (config, key, ours[key], theirs[key])
        assert len(ours['entries']) == len(theirs['entries']) and len(ours['options']) == len(theirs['options'])
        for a, b in zip(ours['entries'], theirs['entries']):
            for key in b:
                assert a[key] == b[key], (config, key, a[key], b[key])
        for a, b in zip(ours['options'], theirs['options']):
            for key in b:
                assert a[key] == b[key], (config, key, a[key], b[key])
    summary['scapy_checked'] = len(sd_parsed)
    return summary


def check_delivery(config, scalars, stats):
    assert scalars['Node1.services[0]', 'msgCount:count'] == PUBLISHED
    for node in ('Node2', 'Node3'):
        assert scalars[f'{node}.services[0]', 'rxPk:count'] == DELIVERED, (config, node)
        assert scalars[f'{node}.middleware.subscriberEndpoints[0]', 'someipReceived'] == DELIVERED
        assert scalars[f'{node}.middleware.subscriberEndpoints[0]', 'someipInvalid'] == 0
        assert scalars[f'{node}.middleware.subscriberEndpoints[0]', 'someipSessionGaps'] == 0
        latency = stats[f'{node}.services[0]', 'rxLatency:stats']
        assert latency['count'] == DELIVERED and 0 < latency['min'] <= latency['max'] < 1e-3, latency
    for node in IP:
        assert scalars[f'{node}.middleware.sd', 'sdMessagesInvalid'] == 0
        assert scalars[f'{node}.middleware.sd', 'sdInvalidOptionReferences'] == 0
    return {node: stats[f'{node}.services[0]', 'rxLatency:stats']['mean'] for node in ('Node2', 'Node3')}


def main():
    (ROOT / 'logs').mkdir(exist_ok=True)
    RESULTS.mkdir(parents=True, exist_ok=True)
    python = ensure_scapy()
    report = {}

    selftest_dir = RESULTS / 'selftest'
    completed = subprocess.run(
        ['bash', '-c', 'set -e; source "$1/scripts/env.sh"; set -u; cd "$1/tests/someiptest"; '
         'exec opp_run -u Cmdenv -n "$1/tests:$INET_ROOT/src:$1/upstream/SOA4CoRE/src-inet4" '
         '-l "$INET_ROOT/src/INET" -l "$1/upstream/SOA4CoRE/src-inet4/SOA4CoRE_INET4" '
         '-f selftest.ini --result-dir="$2"', 'someip-selftest', str(ROOT), str(selftest_dir)],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, stdin=subprocess.DEVNULL)
    (ROOT / 'logs' / 'test-SomeIpSelfTest.log').write_text(completed.stdout)
    assert completed.returncode == 0, completed.stdout[-4000:]
    sca = next(selftest_dir.glob('*.sca')).read_text()
    passed = int(float(next(l.split()[-1] for l in sca.splitlines() if ' checksPassed ' in l)))
    failed = int(float(next(l.split()[-1] for l in sca.splitlines() if ' checksFailed ' in l)))
    assert failed == 0 and passed >= 19, completed.stdout[-4000:]
    report['codec_selftest'] = {'passed': passed, 'failed': failed}

    for config in CONFIGS:
        scalars, stats, result_dir = run(config)
        latency = check_delivery(config, scalars, stats)
        wire = check_wire(config, result_dir, python)
        report[config] = {'published': PUBLISHED, 'delivered_each': DELIVERED, 'latency_mean_seconds': latency, 'wire': wire}

    # INET TSN devices: notifications tagged PCP 5 / VID 10, SD and TCP untagged.
    scalars, stats, result_dir = run('SomeIpTsnPcp')
    for node in ('Node2', 'Node3'):
        assert scalars[f'{node}.services[0]', 'rxPk:count'] == DELIVERED
        assert scalars[f'{node}.middleware.subscriberEndpoints[0]', 'someipInvalid'] == 0
    tags = {}
    for packet in ip_packets(result_dir / 'Node1.pcap', with_vlan=True):
        _, proto, src, sport, dst, dport, payload, _, vlan = packet
        if src == IP['Node1']:
            kind = 'event' if sport == PUBLISHER_PORT else 'sd' if sport == SD_PORT else 'other'
            tags.setdefault((kind, dst), set()).add(vlan)
    assert tags[('event', MCAST_GROUP)] == {(5, 10)} and tags[('event', IP['Node3'])] == {(5, 10)}, tags
    assert all(value == {None} for key, value in tags.items() if key[0] == 'sd'), tags
    report['SomeIpTsnPcp'] = {'delivered_each': DELIVERED, 'event_vlan': [5, 10], 'sd_untagged': True}

    negative = {}
    scalars, _, _ = run('SomeIpTcpUdp', 'SomeIpWrongEventgroup', ('--*.Node3.services[0].eventgroupId=2',))
    assert scalars['Node3.services[0]', 'rxPk:count'] == 0 and scalars['Node2.services[0]', 'rxPk:count'] == DELIVERED
    assert scalars['Node3.middleware.sd', 'sdEntriesReceivedSubscribeAck'] == 0
    assert scalars['Node3.middleware.sd', 'sdEntriesSentSubscribe'] > 0
    negative['wrong_eventgroup'] = {'subscribes': scalars['Node3.middleware.sd', 'sdEntriesSentSubscribe'], 'acks': 0, 'delivered': 0}
    scalars, _, _ = run('SomeIpTcpUdp', 'SomeIpUnknownService', ('--*.Node3.services[0].serviceId=2',))
    # Initial find plus repetitionsMax (3) repetitions, then the subscriber stays silent (no offer).
    assert scalars['Node3.services[0]', 'rxPk:count'] == 0 and scalars['Node3.middleware.sd', 'sdEntriesSentFind'] == 4
    assert scalars['Node3.middleware.sd', 'sdEntriesSentSubscribe'] == 0
    negative['unknown_service'] = {'finds': 4, 'subscribes': 0, 'delivered': 0}
    scalars, _, _ = run('SomeIpTcpUdp', 'SomeIpWrongInstance', ('--*.Node2.services[0].instanceID=2',))
    assert scalars['Node2.services[0]', 'rxPk:count'] == 0 and scalars['Node2.middleware.sd', 'sdEntriesSentSubscribe'] == 0
    assert scalars['Node3.services[0]', 'rxPk:count'] == DELIVERED
    negative['wrong_instance'] = {'subscribes': 0, 'delivered': 0}
    report['negative'] = negative

    path = RESULTS / 'report.json'
    path.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    print('SOME/IP validation passed')


if __name__ == '__main__':
    main()
