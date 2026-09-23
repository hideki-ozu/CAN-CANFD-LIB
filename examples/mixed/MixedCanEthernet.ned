package mixed;

import fico4omnet.bus.can.CanBus;
import fico4omnet.nodes.can.CanNode;
import signalsandgateways.inet4.CanGatewayNode;
import inet.node.contract.IEthernetNetworkNode;
import inet.node.inet.StandardHost;
import inet.node.tsn.TsnDevice;
import inet.node.ethernet.Eth100M;

// Gateway host: CAN port plus one Ethernet interface.
moduleinterface ICanEthernetHost extends IEthernetNetworkNode {
    gates:
        inout can;
}

module CanEthernetHost extends StandardHost like ICanEthernetHost {
    parameters:
        numEthInterfaces = default(1);
        numApps = 1;
        app[0].typename = default("signalsandgateways.inet4.CanEthernetApp");
        @display("i=device/router");
    gates:
        inout can;
    submodules:
        canPort: CanGatewayNode {
            @display("p=100,300");
        }
    connections allowunconnected:
        can <--> canPort.gate;
        canPort.upperLayerOut --> app[0].canIn;
        app[0].canOut --> canPort.upperLayerIn;
}

// Same gateway on INET's TSN device (modular Ethernet, 802.1Q streams, gPTP, shaping).
module CanTsnHost extends TsnDevice like ICanEthernetHost {
    parameters:
        numEthInterfaces = default(1);
        numApps = 1;
        app[0].typename = default("signalsandgateways.inet4.avtp.AvtpCanGatewayApp");
        @display("i=device/router");
    gates:
        inout can;
    submodules:
        canPort: CanGatewayNode {
            @display("p=100,300");
        }
    connections allowunconnected:
        can <--> canPort.gate;
        canPort.upperLayerOut --> app[0].canIn;
        app[0].canOut --> canPort.upperLayerIn;
}

module EthernetHost extends StandardHost like IEthernetNetworkNode {
    parameters:
        numEthInterfaces = default(1);
        numApps = 1;
}

module TsnEthernetHost extends TsnDevice like IEthernetNetworkNode {
    parameters:
        numEthInterfaces = default(1);
        numApps = 1;
}

// Node types are selectable from the ini file (e.g. TSN variants in [Config AvtpTsn*]).
network MixedCanEthernet {
    parameters:
        @display("bgb=1050,650");
    submodules:
        ecuA[2]: CanNode { @display("p=100,120,column,150"); }
        ecuB[2]: CanNode { @display("p=950,120,column,150"); }
        busA: CanBus { @display("p=250,200"); }
        busB: CanBus { @display("p=800,200"); }
        gatewayA: <default("CanEthernetHost")> like ICanEthernetHost {
            numEthInterfaces = 1;
            @display("p=370,200");
        }
        gatewayB: <default("CanEthernetHost")> like ICanEthernetHost {
            numEthInterfaces = 1;
            @display("p=670,200");
        }
        switch: <default("inet.node.ethernet.EthernetSwitch")> like IEthernetNetworkNode {
            numEthInterfaces = 4;
            @display("p=520,330");
        }
        background: <default("EthernetHost")> like IEthernetNetworkNode {
            numEthInterfaces = 1;
            @display("p=370,480");
        }
        receiver: <default("EthernetHost")> like IEthernetNetworkNode {
            numEthInterfaces = 1;
            @display("p=670,480");
        }
    connections:
        for i=0..1 {
            ecuA[i].gate <--> busA.gate++;
            ecuB[i].gate <--> busB.gate++;
        }
        gatewayA.can <--> busA.gate++;
        gatewayB.can <--> busB.gate++;
        gatewayA.ethg[0] <--> Eth100M <--> switch.ethg[0];
        gatewayB.ethg[0] <--> Eth100M <--> switch.ethg[1];
        background.ethg[0] <--> Eth100M <--> switch.ethg[2];
        receiver.ethg[0] <--> Eth100M <--> switch.ethg[3];
}
