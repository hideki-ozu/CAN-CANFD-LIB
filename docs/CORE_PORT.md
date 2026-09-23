# CoRE4INET selected INET4 migration

This is a selected application migration, not a complete CoRE4INET port.
Upstream: CoRE-RG/CoRE4INET, commit
`55439ae79b0960b345b68d2bfb04eb499b384969` (LGPL-3.0-or-later).
The original `BGTrafficSourceApp.cc` now selects its INET4 implementation with
`CORE4INET_INET4`; its original implementation remains available to legacy builds.

## Migrated behavior

The background Ethernet traffic application retains its upstream name, periodic
self-message scheduling, `enabled`, `startTime`, exclusive `stopTime`, volatile
`payload`, volatile `sendInterval`, `payloadSignal`, and `intervalSignal`.
Its relevant `TrafficSourceAppBase` behavior is incorporated into the selected
application; that base class is not claimed to be fully migrated.
The old cached-interval scheduling order is preserved.

INET4 `Packet` with `ByteCountChunk` replaces `EthernetIIFrame` plus encapsulated
`cPacket`. `EthernetSocketIo` supplies address/interface tags and hands packets to
the native INET4 Ethernet stack, which supplies framing, padding, and queues.
The original `sendDirect` fanout to CoRE `BGBuffer` instances is replaced by one
selected native network interface; instantiate multiple apps for multiple links.

The destination default is broadcast rather than an automatically generated,
unassigned MAC address. `destAddress` accepts a MAC or resolvable node path through
`EthernetSocketIo`. `localAddress` controls receive binding: set it to the host MAC
(or the resolvable host path) for a unicast sink. `enabled=false` disables generation
while continuing reception. Remote filtering follows `EthernetSocketIo` behavior;
for a sink use `destAddress=""` to accept any source. The on-wire protocol is INET's
simulation-specific `unknown` EtherType, with a byte-count payload; no real-world
application protocol or serializer is claimed.

`payload` remains restricted to 0..1500 bytes; nonpositive or nonfinite intervals
are rejected. Stop-before-start is rejected, including stopTime=0 with a later
start. Timers are canceled during destruction. Runtime node crash/restart is not
supported by the generator; normal static simulations are the validated scope.

## Build and load

```bash
source scripts/env.sh
make -C upstream/CoRE4INET -f Makefile.inet4 -j2
```

Load `upstream/CoRE4INET/out-inet4/libCoRE4INET_INET4.so` with `opp_run -l`.
Use `upstream/CoRE4INET/src-inet4` as this project's NED root and also include
`upstream/inet/src`. Do not include the legacy `CoRE4INET/src` NED root alongside
this profile: it defines overlapping module names and imports INET3 modules.

For a `StandardHost` or `TsnDevice` application slot:

```ini
*.sender.app[0].typename = "core4inet.applications.trafficsource.base.BGTrafficSourceApp"
*.sender.app[0].interface = "eth0"
*.sender.app[0].destAddress = "receiver"
*.sender.app[0].payload = 256Byte
*.sender.app[0].sendInterval = 1ms
*.receiver.app[0].typename = "core4inet.applications.trafficsource.base.BGTrafficSourceApp"
*.receiver.app[0].enabled = false
*.receiver.app[0].localAddress = "receiver"
*.receiver.app[0].destAddress = ""
```

Statistics are under `app[0].source` and `app[0].io`.

## Not migrated

`ApplicationBase` buffer discovery; BGBuffer and the CoRE NIC/switch layer;
CoRE clocks and schedulers; AS6802 TT/RC/synchronization; AVB/SRP;
IEEE802.1Q/Qbv shaper implementations; IPv4-over-real-time-Ethernet; and legacy
examples. Native INET4 Ethernet/TSN components used alongside this application are
INET implementations, not migrated CoRE implementations. CAN/CAN-FD belongs to
FiCo4OMNeT; gateway migration belongs to SignalsAndGateways.

## Focused regression scenario

`examples-inet4/bgtraffic` sends at 1, 2, 3, and 4 ms and checks the exclusive
5 ms stop boundary through the generated scalar counts (4 sent, 4 received).
Run from that directory after building:

```bash
opp_run -u Cmdenv -n .:../../src-inet4:../../../inet/src \
  -l ../../../inet/src/INET -l ../../out-inet4/CoRE4INET_INET4 omnetpp.ini
```

Verified on OMNeT++ 6.4.0 / INET 4.7.0 in this workspace: the focused profile
compiles and links; the background traffic scenario completes successfully at
10 ms. Both source and Ethernet socket statistics report 4 sent at the sender and
4 received at the receiver. NED syntax validation and diff whitespace checks pass.
