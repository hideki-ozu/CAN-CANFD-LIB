// SPDX-License-Identifier: LGPL-3.0-or-later
//
// Test helper: decodes AAF PCM and CRF AVTPDUs with the COVESA Open1722 reference
// library (IEC 61883: common header only; Open1722 has no 61883 accessors).
// Input: one hex-encoded AVTPDU per line on stdin. Output: one JSON object per line.
// Used by tests/test_av.py to cross-check the simulator's wire format.
#include <inttypes.h>
#include <stdio.h>
#include <string.h>

#include "avtp/CommonHeader.h"
#include "avtp/Crf.h"
#include "avtp/aaf/Pcm.h"

int main(void)
{
    static char line[16384];
    static uint8_t pdu[8192];
    while (fgets(line, sizeof line, stdin)) {
        size_t size = 0;
        for (const char *p = line; p[0] && p[1] && p[0] != '\n' && size < sizeof pdu; p += 2) {
            unsigned value;
            if (sscanf(p, "%2x", &value) != 1)
                break;
            pdu[size++] = (uint8_t)value;
        }
        const Avtp_CommonHeader_t *common = (const Avtp_CommonHeader_t *)pdu;
        const uint8_t subtype = Avtp_CommonHeader_GetSubtype(common);
        printf("{\"subtype\":%u,\"version\":%u", subtype, Avtp_CommonHeader_GetVersion(common));
        if (subtype == AVTP_SUBTYPE_AAF) {
            const Avtp_Pcm_t *pcm = (const Avtp_Pcm_t *)pdu;
            printf(",\"valid\":%s,\"sv\":%d,\"mr\":%d,\"tv\":%d,\"tu\":%d,\"sequence\":%u,\"stream_id\":%" PRIu64
                   ",\"avtp_timestamp\":%u,\"format\":%u,\"nsr\":%u,\"channels\":%u,\"bit_depth\":%u"
                   ",\"data_length\":%u,\"sp\":%d,\"evt\":%u",
                   Avtp_Pcm_IsValid(pcm, size) ? "true" : "false", Avtp_Pcm_IsSv(pcm), Avtp_Pcm_IsMr(pcm),
                   Avtp_Pcm_IsTv(pcm), Avtp_Pcm_IsTu(pcm), Avtp_Pcm_GetSequenceNum(pcm), Avtp_Pcm_GetStreamId(pcm),
                   Avtp_Pcm_GetAvtpTimestamp(pcm), (unsigned)Avtp_Pcm_GetFormat(pcm), (unsigned)Avtp_Pcm_GetNsr(pcm),
                   Avtp_Pcm_GetChannelsPerFrame(pcm), Avtp_Pcm_GetBitDepth(pcm), Avtp_Pcm_GetStreamDataLength(pcm),
                   Avtp_Pcm_IsSp(pcm), Avtp_Pcm_GetEvt(pcm));
        }
        else if (subtype == AVTP_SUBTYPE_CRF) {
            const Avtp_Crf_t *crf = (const Avtp_Crf_t *)pdu;
            printf(",\"valid\":%s,\"sv\":%d,\"mr\":%d,\"fs\":%d,\"tu\":%d,\"sequence\":%u,\"type\":%u"
                   ",\"stream_id\":%" PRIu64 ",\"pull\":%u,\"base_frequency\":%u,\"data_length\":%u"
                   ",\"timestamp_interval\":%u",
                   Avtp_Crf_IsValid(crf, size) ? "true" : "false", Avtp_Crf_IsSv(crf), Avtp_Crf_IsMr(crf),
                   Avtp_Crf_IsFs(crf), Avtp_Crf_IsTu(crf), Avtp_Crf_GetSequenceNum(crf), (unsigned)Avtp_Crf_GetType(crf),
                   Avtp_Crf_GetStreamId(crf), (unsigned)Avtp_Crf_GetPull(crf), Avtp_Crf_GetBaseFrequency(crf),
                   Avtp_Crf_GetCrfDataLength(crf), Avtp_Crf_GetTimestampInterval(crf));
        }
        printf("}\n");
    }
    return 0;
}
