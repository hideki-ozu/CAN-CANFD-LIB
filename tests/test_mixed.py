#!/usr/bin/env python3
"""Run real simulations, assert bidirectional delivery, bytes, and BRS effect."""
import json
import pathlib
import shlex
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]


def scalars(config):
    result = subprocess.run([str(ROOT / 'scripts/run-mixed.sh'), config], cwd=ROOT,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    (ROOT / 'logs' / f'test-{config}.log').write_text(result.stdout)
    assert result.returncode == 0, result.stdout[-6000:]
    files = list((ROOT / 'results/mixed' / config).glob('*.sca'))
    assert len(files) == 1, files
    values = {}
    for line in files[0].read_text().splitlines():
        if line.startswith('scalar '):
            _, module, name, value = shlex.split(line)
            values[module.removeprefix('MixedCanEthernet.'), name] = float(value)
    return values


def main():
    (ROOT / "logs").mkdir(exist_ok=True)
    report = {}
    all_values = {}
    for config in ('Classic', 'Mixed', 'FdNoBrs', 'LoadedEthernet'):
        values = scalars(config)
        all_values[config] = values
        for gateway in ('gatewayA', 'gatewayB'):
            for direction in ('canToEthernet', 'ethernetToCan'):
                assert values[f'{gateway}.app[0].bridge', direction] == 20
        for side in ('A', 'B'):
            for node in range(2):
                module = f'ecu{side}[{node}].sinkApp[0]'
                assert values[module, 'receivedFrames'] == 20
                assert values[module, 'receivedPayloadBytes'] == (160 if config == 'Classic' else 720)
                for can_id in ((768, 1024) if side == 'A' else (256, 512)):
                    assert values[module, f'id_{can_id}_received'] == 10
                    assert values[module, f'id_{can_id}_delayMean'] > 0
        sent = values['background.app[0].source', 'packets sent']
        received = values['receiver.app[0].source', 'packets received']
        assert sent > 0 and sent == received, (sent, received)
        report[config] = {'gateway_tx_each': 20, 'gateway_rx_each': 20,
                          'ecu_rx_each': 20, 'ethernet_background_delivered': received}
    for side, frame_id in (('A', 1024), ('B', 512)):
        module = f'ecu{side}[0].sinkApp[0]'
        key = (module, f'id_{frame_id}_delayMean')
        assert all_values['Mixed'][key] < all_values['FdNoBrs'][key]
        report[f'fd_id_{frame_id}_delay_seconds'] = {
            'brs_on': all_values['Mixed'][key], 'brs_off': all_values['FdNoBrs'][key]}
    path = ROOT / 'results/mixed/verification.json'
    path.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
