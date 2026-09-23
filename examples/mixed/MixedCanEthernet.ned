package mixed;

import fico4omnet.bus.can.CanBus;
import fico4omnet.nodes.can.CanNode;
import signalsandgateways.inet4.CanGatewayNode;
import inet.node.inet.StandardHost;
import inet.node.ethernet.EthernetSwitch;
import inet.node.ethernet.Eth100M;

module CanEthernetHost extends StandardHost {
    parameters:
        numEthInterfaces = 1;
        numApps = 1;
        app[0].typename = "signalsandgateways.inet4.CanEthernetApp";
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

network MixedCanEthernet {
    parameters:
        @display("bgb=1050,650");
    submodules:
        ecuA[2]: CanNode { @display("p=100,120,column,150"); }
        ecuB[2]: CanNode { @display("p=950,120,column,150"); }
        busA: CanBus { @display("p=250,200"); }
        busB: CanBus { @display("p=800,200"); }
        gatewayA: CanEthernetHost { @display("p=370,200"); }
        gatewayB: CanEthernetHost { @display("p=670,200"); }
        switch: EthernetSwitch {
            numEthInterfaces = 4;
            @display("p=520,330");
        }
        background: StandardHost {
            numEthInterfaces = 1;
            numApps = 1;
            @display("p=370,480");
        }
        receiver: StandardHost {
            numEthInterfaces = 1;
            numApps = 1;
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
