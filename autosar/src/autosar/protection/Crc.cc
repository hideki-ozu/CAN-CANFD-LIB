// SPDX-License-Identifier: BSD-3-Clause
#include "autosar/protection/Crc.h"

#include <array>

namespace autosar {
namespace {

// Table-driven CRC with the parameters of the Rocksoft model. Tables are built once
// from the polynomial, so there are no hand-copied constants to get wrong.
template <typename T, T Poly, bool Reflected>
struct CrcTable {
    std::array<T, 256> entries{};
    CrcTable() {
        constexpr int width = sizeof(T) * 8;
        for (unsigned i = 0; i < 256; ++i) {
            T crc;
            if (Reflected) {
                crc = static_cast<T>(i);
                for (int bit = 0; bit < 8; ++bit)
                    crc = (crc & 1) ? static_cast<T>((crc >> 1) ^ Poly) : static_cast<T>(crc >> 1);
            }
            else {
                crc = static_cast<T>(static_cast<T>(i) << (width - 8));
                for (int bit = 0; bit < 8; ++bit)
                    crc = (crc >> (width - 1)) & 1 ? static_cast<T>((crc << 1) ^ Poly) : static_cast<T>(crc << 1);
            }
            entries[i] = crc;
        }
    }
};

template <typename T, T Poly, bool Reflected, T Init, T XorOut>
T calculate(const uint8_t *data, size_t length, T startValue, bool isFirstCall)
{
    static const CrcTable<T, Poly, Reflected> table;
    constexpr int width = sizeof(T) * 8;
    // A continued calculation undoes the final XOR of the previous call.
    T crc = isFirstCall ? Init : static_cast<T>(startValue ^ XorOut);
    for (size_t i = 0; i < length; ++i) {
        if (Reflected)
            crc = static_cast<T>((width > 8 ? (crc >> 8) : 0) ^ table.entries[(crc ^ data[i]) & 0xFF]);
        else
            crc = static_cast<T>((width > 8 ? static_cast<T>(crc << 8) : 0) ^ table.entries[((crc >> (width - 8)) ^ data[i]) & 0xFF]);
    }
    return static_cast<T>(crc ^ XorOut);
}

} // namespace

uint8_t crc8(const uint8_t *data, size_t length, uint8_t startValue, bool isFirstCall)
{
    return calculate<uint8_t, 0x1D, false, 0xFF, 0xFF>(data, length, startValue, isFirstCall);
}

uint8_t crc8h2f(const uint8_t *data, size_t length, uint8_t startValue, bool isFirstCall)
{
    return calculate<uint8_t, 0x2F, false, 0xFF, 0xFF>(data, length, startValue, isFirstCall);
}

uint16_t crc16(const uint8_t *data, size_t length, uint16_t startValue, bool isFirstCall)
{
    return calculate<uint16_t, 0x1021, false, 0xFFFF, 0x0000>(data, length, startValue, isFirstCall);
}

uint32_t crc32(const uint8_t *data, size_t length, uint32_t startValue, bool isFirstCall)
{
    // 0xEDB88320 is the bit-reversed form of 0x04C11DB7.
    return calculate<uint32_t, 0xEDB88320u, true, 0xFFFFFFFFu, 0xFFFFFFFFu>(data, length, startValue, isFirstCall);
}

uint32_t crc32p4(const uint8_t *data, size_t length, uint32_t startValue, bool isFirstCall)
{
    // 0xC8DF352F is the bit-reversed form of 0xF4ACFB13.
    return calculate<uint32_t, 0xC8DF352Fu, true, 0xFFFFFFFFu, 0xFFFFFFFFu>(data, length, startValue, isFirstCall);
}

uint64_t crc64(const uint8_t *data, size_t length, uint64_t startValue, bool isFirstCall)
{
    // 0xC96C5795D7870F42 is the bit-reversed form of 0x42F0E1EBA9EA3693.
    return calculate<uint64_t, 0xC96C5795D7870F42ull, true, ~0ull, ~0ull>(data, length, startValue, isFirstCall);
}

} // namespace autosar
