// SPDX-License-Identifier: LGPL-3.0-or-later
//
// Test helper: decodes AVTPDUs with the COVESA Open1722 reference library.
// Input: one hex-encoded AVTPDU per line on stdin. Output: one JSON object per line.
// Used by tests/test_avtp.py to cross-check the simulator's wire format.
#include <inttypes.h>
#include <stdio.h>
#include <string.h>

#include "avtp/CommonHeader.h"
#include "avtp/acf/AcfCommon.h"
#include "avtp/acf/Can.h"
#include "avtp/acf/CanBrief.h"
#include "avtp/acf/Ntscf.h"
#include "avtp/acf/Tscf.h"

static void printPayload(const uint8_t *payload, unsigned length)
{
    printf("\"payload\":\"");
    for (unsigned i = 0; i < length; ++i)
        printf("%02x", payload[i]);
    printf("\"");
}

static void printAcf(const uint8_t *msg, size_t available)
{
    const Avtp_AcfCommon_t *common = (const Avtp_AcfCommon_t *)msg;
    const uint8_t type = Avtp_AcfCommon_GetAcfMsgType(common);
    const unsigned length = Avtp_AcfCommon_GetAcfMsgLengthInBytes(common);
    printf("{\"type\":%u,\"length\":%u", type, length);
    if (type == AVTP_ACF_TYPE_CAN) {
        const Avtp_Can_t *can = (const Avtp_Can_t *)msg;
        printf(",\"valid\":%s,\"pad\":%u,\"mtv\":%d,\"rtr\":%d,\"eff\":%d,\"brs\":%d,\"fdf\":%d,\"esi\":%d"
               ",\"bus\":%u,\"timestamp\":%" PRIu64 ",\"id\":%u,",
               Avtp_Can_IsValid(can, available) ? "true" : "false", Avtp_Can_GetPad(can),
               Avtp_Can_IsMtv(can), Avtp_Can_IsRtr(can), Avtp_Can_IsEff(can), Avtp_Can_IsBrs(can),
               Avtp_Can_IsFdf(can), Avtp_Can_IsEsi(can), Avtp_Can_GetCanBusId(can),
               Avtp_Can_GetMessageTimestamp(can), Avtp_Can_GetCanIdentifier(can));
        printPayload(Avtp_Can_GetPayload(can), Avtp_Can_GetPayloadLength(can));
    }
    else if (type == AVTP_ACF_TYPE_CAN_BRIEF) {
        const Avtp_CanBrief_t *can = (const Avtp_CanBrief_t *)msg;
        printf(",\"valid\":%s,\"pad\":%u,\"mtv\":%d,\"rtr\":%d,\"eff\":%d,\"brs\":%d,\"fdf\":%d,\"esi\":%d"
               ",\"bus\":%u,\"id\":%u,",
               Avtp_CanBrief_IsValid(can, available) ? "true" : "false", Avtp_CanBrief_GetPad(can),
               Avtp_CanBrief_IsMtv(can), Avtp_CanBrief_IsRtr(can), Avtp_CanBrief_IsEff(can),
               Avtp_CanBrief_IsBrs(can), Avtp_CanBrief_IsFdf(can), Avtp_CanBrief_IsEsi(can),
               Avtp_CanBrief_GetCanBusId(can), Avtp_CanBrief_GetCanIdentifier(can));
        printPayload(Avtp_CanBrief_GetPayload(can), Avtp_CanBrief_GetPayloadLength(can));
    }
    printf("}");
}

int main(void)
{
    static char line[8192];
    static uint8_t pdu[4096];
    while (fgets(line, sizeof line, stdin)) {
        size_t size = 0;
        for (const char *p = line; p[0] && p[1] && p[0] != '\n' && size < sizeof pdu; p += 2) {
            unsigned value;
            if (sscanf(p, "%2x", &value) != 1)
                break;
            pdu[size++] = (uint8_t)value;
        }
        const uint8_t subtype = Avtp_CommonHeader_GetSubtype((const Avtp_CommonHeader_t *)pdu);
        size_t header = 0, dataLength = 0;
        printf("{\"subtype\":%u,\"version\":%u", subtype,
               Avtp_CommonHeader_GetVersion((const Avtp_CommonHeader_t *)pdu));
        if (subtype == AVTP_SUBTYPE_NTSCF) {
            const Avtp_Ntscf_t *ntscf = (const Avtp_Ntscf_t *)pdu;
            header = AVTP_NTSCF_HEADER_LEN;
            dataLength = Avtp_Ntscf_GetNtscfDataLength(ntscf);
            printf(",\"valid\":%s,\"sv\":%d,\"sequence\":%u,\"stream_id\":%" PRIu64 ",\"data_length\":%zu",
                   Avtp_Ntscf_IsValid(ntscf, size) ? "true" : "false", Avtp_Ntscf_IsSv(ntscf),
                   Avtp_Ntscf_GetSequenceNum(ntscf), Avtp_Ntscf_GetStreamId(ntscf), dataLength);
        }
        else if (subtype == AVTP_SUBTYPE_TSCF) {
            const Avtp_Tscf_t *tscf = (const Avtp_Tscf_t *)pdu;
            header = AVTP_TSCF_HEADER_LEN;
            dataLength = Avtp_Tscf_GetStreamDataLength(tscf);
            printf(",\"valid\":%s,\"sv\":%d,\"tv\":%d,\"sequence\":%u,\"stream_id\":%" PRIu64
                   ",\"avtp_timestamp\":%u,\"data_length\":%zu",
                   Avtp_Tscf_IsValid(tscf, size) ? "true" : "false", Avtp_Tscf_IsSv(tscf),
                   Avtp_Tscf_IsTv(tscf), Avtp_Tscf_GetSequenceNum(tscf), Avtp_Tscf_GetStreamId(tscf),
                   Avtp_Tscf_GetAvtpTimestamp(tscf), dataLength);
        }
        printf(",\"messages\":[");
        size_t offset = header;
        int first = 1;
        while (header && offset + AVTP_ACF_COMMON_HEADER_LEN <= header + dataLength && offset < size) {
            const unsigned length = Avtp_AcfCommon_GetAcfMsgLengthInBytes((const Avtp_AcfCommon_t *)(pdu + offset));
            if (length == 0)
                break;
            printf(first ? "" : ",");
            first = 0;
            printAcf(pdu + offset, size - offset);
            offset += length;
        }
        printf("]}\n");
    }
    return 0;
}
