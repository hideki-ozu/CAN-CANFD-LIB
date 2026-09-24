package av;

import inet.node.contract.IEthernetNetworkNode;
import inet.node.ethernet.Eth100M;
import inet.node.inet.StandardHost;
import inet.node.tsn.TsnDevice;

// Host with one Ethernet port and the IEEE 1722 media endpoint (talkers/listeners).
module AvHost extends StandardHost like IEthernetNetworkNode {
    parameters:
        numEthInterfaces = default(1);
        numApps = 1;
        app[0].typename = default("signalsandgateways.inet4.avtp.media.AvtpMediaEndpoint");
        @display("i=device/pc2");
}

// Same endpoint on INET's TSN device (802.1Q stream encoding, gPTP, shaping).
module AvTsnHost extends TsnDevice like IEthernetNetworkNode {
    parameters:
        numEthInterfaces = default(1);
        numApps = 1;
        app[0].typename = default("signalsandgateways.inet4.avtp.media.AvtpMediaEndpoint");
        @display("i=device/pc2");
}

module LoadHost extends StandardHost like IEthernetNetworkNode {
    parameters:
        numEthInterfaces = default(1);
        numApps = 1;
}

module TsnLoadHost extends TsnDevice like IEthernetNetworkNode {
    parameters:
        numEthInterfaces = default(1);
        numApps = 1;
}

// Digital radio / TV distribution in a vehicle: the tuner ECU streams decoded radio
// audio (AAF PCM), the TV transport stream (IEC 61883-4 MPEG-2 TS) and its media
// clock (CRF) to the head unit; the rear seat display also receives the TV stream.
// Node types are selectable from the ini file (TSN variants in [Config AvTsn*]).
network AvNetwork {
    parameters:
        @display("bgb=800,500");
    submodules:
        tuner: <default("AvHost")> like IEthernetNetworkNode {
            @display("p=150,150");
        }
        headUnit: <default("AvHost")> like IEthernetNetworkNode {
            @display("p=650,150");
        }
        rearDisplay: <default("AvHost")> like IEthernetNetworkNode {
            @display("p=650,350");
        }
        background: <default("LoadHost")> like IEthernetNetworkNode {
            @display("p=150,350");
        }
        switch: <default("inet.node.ethernet.EthernetSwitch")> like IEthernetNetworkNode {
            numEthInterfaces = 4;
            @display("p=400,250");
        }
    connections:
        tuner.ethg[0] <--> Eth100M <--> switch.ethg[0];
        headUnit.ethg[0] <--> Eth100M <--> switch.ethg[1];
        rearDisplay.ethg[0] <--> Eth100M <--> switch.ethg[2];
        background.ethg[0] <--> Eth100M <--> switch.ethg[3];
}
