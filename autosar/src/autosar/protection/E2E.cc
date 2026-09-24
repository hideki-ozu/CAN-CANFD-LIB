// SPDX-License-Identifier: BSD-3-Clause
#include "autosar/protection/E2E.h"
#include "autosar/protection/Crc.h"

#include <stdexcept>

namespace autosar {
namespace {

void put16be(uint8_t *p, uint16_t v) { p[0] = v >> 8; p[1] = v & 0xFF; }
void put32be(uint8_t *p, uint32_t v) { for (int i = 0; i < 4; ++i) p[i] = (v >> (24 - 8 * i)) & 0xFF; }
void put64be(uint8_t *p, uint64_t v) { for (int i = 0; i < 8; ++i) p[i] = (v >> (56 - 8 * i)) & 0xFF; }
uint16_t get16be(const uint8_t *p) { return uint16_t(p[0] << 8 | p[1]); }
uint32_t get32be(const uint8_t *p) { return uint32_t(p[0]) << 24 | uint32_t(p[1]) << 16 | uint32_t(p[2]) << 8 | p[3]; }
uint64_t get64be(const uint8_t *p) { return uint64_t(get32be(p)) << 32 | get32be(p + 4); }

// Profile 1: DataID bytes first, then all bytes except the CRC byte. The start value
// 0xFF and the final XOR compensate the CRC library's own XOR (net: init 0, xorout 0).
uint8_t p01Crc(const E2EConfig& c, const uint8_t *data, size_t length, uint8_t counter)
{
    uint8_t lo = c.dataId & 0xFF, hi = (c.dataId >> 8) & 0xFF, zero = 0;
    uint8_t crc = 0;
    switch (c.dataIdMode) {
        case P01DataIdMode::Both:
            crc = crc8(&lo, 1, 0xFF, false);
            crc = crc8(&hi, 1, crc, false);
            break;
        case P01DataIdMode::Low:
            crc = crc8(&lo, 1, 0xFF, false);
            break;
        case P01DataIdMode::Alt:
            crc = crc8(counter % 2 == 0 ? &lo : &hi, 1, 0xFF, false);
            break;
        case P01DataIdMode::Nibble:
            crc = crc8(&lo, 1, 0xFF, false);
            crc = crc8(&zero, 1, crc, false);
            break;
    }
    crc = crc8(data, c.offset, crc, false);
    crc = crc8(data + c.offset + 1, length - c.offset - 1, crc, false);
    return crc ^ 0xFF;
}

uint8_t p02Crc(const E2EConfig& c, const uint8_t *data, size_t length, uint8_t counter)
{
    uint8_t crc = crc8h2f(data + 1, length - 1, 0xFF, true);
    return crc8h2f(&c.dataIdList[counter], 1, crc, false);
}

uint32_t p04Crc(const E2EConfig& c, const uint8_t *data, size_t length)
{
    uint32_t crc = crc32p4(data, c.offset + 8, 0xFFFFFFFFu, true);
    return crc32p4(data + c.offset + 12, length - c.offset - 12, crc, false);
}

uint16_t p05Crc(const E2EConfig& c, const uint8_t *data, size_t length)
{
    uint8_t id[2] = {uint8_t(c.dataId & 0xFF), uint8_t((c.dataId >> 8) & 0xFF)};
    uint16_t crc = crc16(data, c.offset, 0xFFFF, true);
    crc = crc16(data + c.offset + 2, length - c.offset - 2, crc, false);
    return crc16(id, 2, crc, false);
}

uint64_t p07Crc(const E2EConfig& c, const uint8_t *data, size_t length)
{
    uint64_t crc = crc64(data, c.offset, ~0ull, true);
    return crc64(data + c.offset + 8, length - c.offset - 8, crc, false);
}

} // namespace

E2EProfile parseE2EProfile(const std::string& name)
{
    if (name == "none" || name.empty()) return E2EProfile::None;
    if (name == "P01") return E2EProfile::P01;
    if (name == "P02") return E2EProfile::P02;
    if (name == "P04") return E2EProfile::P04;
    if (name == "P05") return E2EProfile::P05;
    if (name == "P07") return E2EProfile::P07;
    throw std::invalid_argument("unknown E2E profile '" + name + "' (none, P01, P02, P04, P05, P07)");
}

P01DataIdMode parseP01DataIdMode(const std::string& name)
{
    if (name == "both") return P01DataIdMode::Both;
    if (name == "alt") return P01DataIdMode::Alt;
    if (name == "low") return P01DataIdMode::Low;
    if (name == "nibble") return P01DataIdMode::Nibble;
    throw std::invalid_argument("unknown Profile 1 DataID mode '" + name + "' (both, alt, low, nibble)");
}

const char *toString(E2EProfile profile)
{
    switch (profile) {
        case E2EProfile::None: return "none";
        case E2EProfile::P01: return "P01";
        case E2EProfile::P02: return "P02";
        case E2EProfile::P04: return "P04";
        case E2EProfile::P05: return "P05";
        case E2EProfile::P07: return "P07";
    }
    return "?";
}

const char *toString(E2ECheckStatus status)
{
    switch (status) {
        case E2ECheckStatus::Ok: return "OK";
        case E2ECheckStatus::NoNewData: return "NONEWDATA";
        case E2ECheckStatus::Error: return "ERROR";
        case E2ECheckStatus::Repeated: return "REPEATED";
        case E2ECheckStatus::OkSomeLost: return "OKSOMELOST";
        case E2ECheckStatus::WrongSequence: return "WRONGSEQUENCE";
    }
    return "?";
}

const char *toString(E2ESmState state)
{
    switch (state) {
        case E2ESmState::NoData: return "NODATA";
        case E2ESmState::Init: return "INIT";
        case E2ESmState::Valid: return "VALID";
        case E2ESmState::Invalid: return "INVALID";
    }
    return "?";
}

size_t e2eHeaderBytes(E2EProfile profile)
{
    switch (profile) {
        case E2EProfile::None: return 0;
        case E2EProfile::P01: return 2;
        case E2EProfile::P02: return 2;
        case E2EProfile::P04: return 12;
        case E2EProfile::P05: return 3;
        case E2EProfile::P07: return 20;
    }
    return 0;
}

uint64_t e2eCounterModulus(E2EProfile profile)
{
    switch (profile) {
        case E2EProfile::P01: return 15;
        case E2EProfile::P02: return 16;
        case E2EProfile::P04: return 0x10000ull;
        case E2EProfile::P05: return 0x100ull;
        case E2EProfile::P07: return 0x100000000ull;
        case E2EProfile::None: return 1;
    }
    return 1;
}

void validateE2EConfig(const E2EConfig& c, size_t length)
{
    if (c.profile == E2EProfile::None)
        return;
    if ((c.offset > length || e2eHeaderBytes(c.profile) > length - c.offset))
        throw std::invalid_argument(std::string("E2E ") + toString(c.profile) + " header does not fit into "
                + std::to_string(length) + " bytes at offset " + std::to_string(c.offset));
    if (c.maxDeltaCounter < 1 || c.maxDeltaCounter >= e2eCounterModulus(c.profile))
        throw std::invalid_argument("E2E maxDeltaCounter out of range for the profile counter");
    switch (c.profile) {
        case E2EProfile::P01:
        case E2EProfile::P05:
            if (c.dataId > 0xFFFF)
                throw std::invalid_argument("E2E P01/P05 DataID is 16 bit");
            if (c.profile == E2EProfile::P01 && c.dataIdMode == P01DataIdMode::Nibble && c.dataId > 0x0FFF)
                throw std::invalid_argument("E2E P01 nibble mode transmits 12 DataID bits (max 0x0FFF)");
            break;
        case E2EProfile::P02:
            if (c.offset != 0)
                throw std::invalid_argument("E2E P02 has a fixed header at byte 0");
            break;
        case E2EProfile::P04:
            if (length > 0xFFFF)
                throw std::invalid_argument("E2E P04 length field is 16 bit");
            break;
        default:
            break;
    }
}

void e2eWrite(const E2EConfig& c, uint8_t *data, size_t length, uint64_t counter)
{
    uint8_t *h = data + c.offset;
    switch (c.profile) {
        case E2EProfile::None:
            return;
        case E2EProfile::P01:
            h[1] = (h[1] & 0xF0) | (counter & 0x0F);
            if (c.dataIdMode == P01DataIdMode::Nibble)
                h[1] = (h[1] & 0x0F) | ((c.dataId >> 4) & 0xF0);
            h[0] = p01Crc(c, data, length, counter & 0x0F);
            return;
        case E2EProfile::P02:
            h[1] = (h[1] & 0xF0) | (counter & 0x0F);
            h[0] = p02Crc(c, data, length, counter & 0x0F);
            return;
        case E2EProfile::P04:
            put16be(h, uint16_t(length));
            put16be(h + 2, uint16_t(counter));
            put32be(h + 4, c.dataId);
            put32be(h + 8, p04Crc(c, data, length));
            return;
        case E2EProfile::P05:
            h[2] = uint8_t(counter);
            {
                const uint16_t crc = p05Crc(c, data, length);
                h[0] = crc & 0xFF;      // little endian
                h[1] = crc >> 8;
            }
            return;
        case E2EProfile::P07:
            put32be(h + 8, uint32_t(length));
            put32be(h + 12, uint32_t(counter));
            put32be(h + 16, c.dataId);
            put64be(h, p07Crc(c, data, length));
            return;
    }
}

bool e2eVerify(const E2EConfig& c, const uint8_t *data, size_t length, uint64_t *counter)
{
    if ((c.offset > length || e2eHeaderBytes(c.profile) > length - c.offset))
        return false;
    const uint8_t *h = data + c.offset;
    switch (c.profile) {
        case E2EProfile::None:
            return true;
        case E2EProfile::P01: {
            const uint8_t ctr = h[1] & 0x0F;
            if (ctr > 14)
                return false;
            if (c.dataIdMode == P01DataIdMode::Nibble && (h[1] >> 4) != ((c.dataId >> 8) & 0x0F))
                return false;
            *counter = ctr;
            return h[0] == p01Crc(c, data, length, ctr);
        }
        case E2EProfile::P02: {
            const uint8_t ctr = h[1] & 0x0F;
            *counter = ctr;
            return h[0] == p02Crc(c, data, length, ctr);
        }
        case E2EProfile::P04:
            *counter = get16be(h + 2);
            return get16be(h) == length && get32be(h + 4) == c.dataId && get32be(h + 8) == p04Crc(c, data, length);
        case E2EProfile::P05:
            *counter = h[2];
            return uint16_t(h[0] | h[1] << 8) == p05Crc(c, data, length);
        case E2EProfile::P07:
            *counter = get32be(h + 12);
            return get32be(h + 8) == length && get32be(h + 16) == c.dataId && get64be(h) == p07Crc(c, data, length);
    }
    return false;
}

void E2EProtector::protect(uint8_t *data, size_t length)
{
    validateE2EConfig(config, length);
    e2eWrite(config, data, length, counter);
    counter = (counter + 1) % e2eCounterModulus(config.profile);
}

E2EChecker::E2EChecker(const E2EConfig& config)
    : config(config), last(e2eCounterModulus(config.profile) - 1)  // first counter 0 is then OK
{
}

E2ECheckStatus E2EChecker::check(const uint8_t *data, size_t length, bool newDataAvailable)
{
    if (!newDataAvailable)
        return E2ECheckStatus::NoNewData;
    uint64_t received = 0;
    if (!e2eVerify(config, data, length, &received))
        return E2ECheckStatus::Error;
    const uint64_t modulus = e2eCounterModulus(config.profile);
    const uint64_t delta = (received + modulus - last) % modulus;
    last = received;
    if (delta == 0)
        return E2ECheckStatus::Repeated;
    if (delta == 1)
        return E2ECheckStatus::Ok;
    if (delta <= config.maxDeltaCounter)
        return E2ECheckStatus::OkSomeLost;
    return E2ECheckStatus::WrongSequence;
}

E2EStateMachine::E2EStateMachine(const E2ESmConfig& config) : config(config)
{
    if (config.windowSize == 0)
        throw std::invalid_argument("E2E state machine window size must be at least 1");
}

unsigned E2EStateMachine::okCount() const
{
    unsigned n = 0;
    for (auto s : window)
        n += s == E2ECheckStatus::Ok || s == E2ECheckStatus::OkSomeLost;
    return n;
}

// [PRS_E2E_00466] E2E_SMAddStatus: ErrorCount is the number of E2E_P_ERROR entries only.
// REPEATED and WRONGSEQUENCE are counter errors that occupy a window slot (and so lower
// OKCount) but add to neither count; NONEWDATA likewise.
unsigned E2EStateMachine::errorCount() const
{
    unsigned n = 0;
    for (auto s : window)
        n += s == E2ECheckStatus::Error;
    return n;
}

E2ESmState E2EStateMachine::check(E2ECheckStatus status)
{
    // E2E_SMCheck: sliding window of the last windowSize statuses.
    if (window.size() < config.windowSize)
        window.push_back(status);
    else
        window[next] = status;
    next = (next + 1) % config.windowSize;
    const unsigned ok = okCount(), errors = errorCount();
    switch (current) {
        case E2ESmState::NoData:
            if (status != E2ECheckStatus::Error && status != E2ECheckStatus::NoNewData)
                current = E2ESmState::Init;
            break;
        case E2ESmState::Init:
            if (errors <= config.maxErrorStateInit && ok >= config.minOkStateInit)
                current = E2ESmState::Valid;
            else if (errors > config.maxErrorStateInit)
                current = E2ESmState::Invalid;
            break;
        case E2ESmState::Valid:
            if (!(errors <= config.maxErrorStateValid && ok >= config.minOkStateValid))
                current = E2ESmState::Invalid;
            break;
        case E2ESmState::Invalid:
            if (errors <= config.maxErrorStateInvalid && ok >= config.minOkStateInvalid)
                current = E2ESmState::Valid;
            break;
    }
    return current;
}

} // namespace autosar
