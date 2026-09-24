// SPDX-License-Identifier: LGPL-3.0-or-later
//
// INET4 port of SOA4CoRE examples/someip/small_network: three middleware hosts and
// one Ethernet switch. Node1 publishes service 1 (SOME/IP UDP, UDP multicast, TCP);
// Node2 and Node3 subscribe after SOME/IP-SD find/offer/subscribe/ack.
//
package someip;

import inet.networklayer.configurator.ipv4.Ipv4NetworkConfigurator;
import inet.node.contract.IEthernetNetworkNode;
import inet.node.ethernet.Eth100M;
import soa4core.nodes.MiddlewareHost;

network SomeIpSmallNetwork
{
    parameters:
        @display("bgb=420,260");
    submodules:
        configurator: Ipv4NetworkConfigurator {
            @display("p=360,220");
        }
        Node1: <default("MiddlewareHost")> like IEthernetNetworkNode {
            numEthInterfaces = 1;
            @display("p=60,60");
        }
        Node2: <default("MiddlewareHost")> like IEthernetNetworkNode {
            numEthInterfaces = 1;
            @display("p=210,200");
        }
        Node3: <default("MiddlewareHost")> like IEthernetNetworkNode {
            numEthInterfaces = 1;
            @display("p=360,60");
        }
        Switch: <default("inet.node.ethernet.EthernetSwitch")> like IEthernetNetworkNode {
            numEthInterfaces = 3;
            @display("p=210,90");
        }
    connections:
        Node1.ethg[0] <--> Eth100M <--> Switch.ethg[0];
        Node2.ethg[0] <--> Eth100M <--> Switch.ethg[1];
        Node3.ethg[0] <--> Eth100M <--> Switch.ethg[2];
}
