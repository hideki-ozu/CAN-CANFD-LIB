// SPDX-License-Identifier: BSD-3-Clause
// CRC routines of the AUTOSAR CRC library (SWS CRC) used by the E2E profiles.
// Each function follows the Crc_CalculateCRCx(data, length, startValue, isFirstCall)
// convention: a non-first call continues from the value returned by the previous
// call, so a CRC over several separate areas can be chained.
#ifndef AUTOSAR_PROTECTION_CRC_H
#define AUTOSAR_PROTECTION_CRC_H

#include <cstddef>
#include <cstdint>

namespace autosar {

// CRC-8 SAE J1850: poly 0x1D, init 0xFF, xorout 0xFF (Profile 1).
uint8_t crc8(const uint8_t *data, size_t length, uint8_t startValue, bool isFirstCall);
// CRC-8H2F: poly 0x2F, init 0xFF, xorout 0xFF (Profile 2).
uint8_t crc8h2f(const uint8_t *data, size_t length, uint8_t startValue, bool isFirstCall);
// CRC-16 CCITT-FALSE: poly 0x1021, init 0xFFFF, xorout 0 (Profile 5).
uint16_t crc16(const uint8_t *data, size_t length, uint16_t startValue, bool isFirstCall);
// CRC-32 (IEEE 802.3), reflected poly 0x04C11DB7, init/xorout 0xFFFFFFFF.
uint32_t crc32(const uint8_t *data, size_t length, uint32_t startValue, bool isFirstCall);
// CRC-32P4, reflected poly 0xF4ACFB13, init/xorout 0xFFFFFFFF (Profile 4).
uint32_t crc32p4(const uint8_t *data, size_t length, uint32_t startValue, bool isFirstCall);
// CRC-64 (ECMA-182, reflected), poly 0x42F0E1EBA9EA3693, init/xorout all ones (Profile 7).
uint64_t crc64(const uint8_t *data, size_t length, uint64_t startValue, bool isFirstCall);

} // namespace autosar

#endif
