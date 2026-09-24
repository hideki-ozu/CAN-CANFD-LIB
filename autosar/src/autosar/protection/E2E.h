// SPDX-License-Identifier: BSD-3-Clause
// AUTOSAR E2E protection profiles 1, 2, 4, 5 and 7 (PRS E2E Protocol) and the
// E2E state machine. Protect/check work on a byte buffer in place; the buffer is the
// complete area covered by the CRC (for SOME/IP: the header from Request ID onward
// plus the payload, with the E2E header at 'offset').
#ifndef AUTOSAR_PROTECTION_E2E_H
#define AUTOSAR_PROTECTION_E2E_H

#include <array>
#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace autosar {

enum class E2EProfile { None, P01, P02, P04, P05, P07 };

// Profile 1 DataID inclusion modes (variants 1A/1B use BOTH/ALT, 1C uses NIBBLE).
enum class P01DataIdMode { Both, Alt, Low, Nibble };

// Result of one check call, as mapped to the state machine (E2E_PCheckStatusType).
enum class E2ECheckStatus { Ok, NoNewData, Error, Repeated, OkSomeLost, WrongSequence };

enum class E2ESmState { NoData, Init, Valid, Invalid };

struct E2EConfig {
    E2EProfile profile = E2EProfile::None;
    uint32_t dataId = 0;                          // P01/P05: 16 bit, P04/P07: 32 bit
    P01DataIdMode dataIdMode = P01DataIdMode::Both;
    std::array<uint8_t, 16> dataIdList{};         // P02: DataID per counter value
    size_t offset = 0;                            // byte offset of the E2E header
    uint32_t maxDeltaCounter = 1;                 // largest accepted counter jump
};

struct E2ESmConfig {
    unsigned windowSize = 3;
    unsigned minOkStateInit = 1;
    unsigned maxErrorStateInit = 1;
    unsigned minOkStateValid = 1;
    unsigned maxErrorStateValid = 1;
    unsigned minOkStateInvalid = 2;
    unsigned maxErrorStateInvalid = 0;
};

E2EProfile parseE2EProfile(const std::string& name);
P01DataIdMode parseP01DataIdMode(const std::string& name);
const char *toString(E2EProfile profile);
const char *toString(E2ECheckStatus status);
const char *toString(E2ESmState state);

// Size of the E2E header in bytes (P01/P02: CRC byte + counter nibble byte).
size_t e2eHeaderBytes(E2EProfile profile);
// Number of distinct counter values (P01 uses 0..14, 15 is invalid).
uint64_t e2eCounterModulus(E2EProfile profile);
// Throws std::invalid_argument if the configuration cannot protect 'length' bytes.
void validateE2EConfig(const E2EConfig& config, size_t length);

// Stateless primitives: write header and CRC for 'counter'; verify CRC, DataID and
// length. e2eVerify stores the received counter on success.
void e2eWrite(const E2EConfig& config, uint8_t *data, size_t length, uint64_t counter);
bool e2eVerify(const E2EConfig& config, const uint8_t *data, size_t length, uint64_t *counter);

class E2EProtector {
public:
    explicit E2EProtector(const E2EConfig& config) : config(config) {}
    // Protects with the current counter, then advances it (E2E_PXXProtect).
    void protect(uint8_t *data, size_t length);
    uint64_t nextCounter() const { return counter; }
    // Fault injection: advance the counter without sending.
    void skip(uint64_t count) { counter = (counter + count) % e2eCounterModulus(config.profile); }
    const E2EConfig& getConfig() const { return config; }
private:
    E2EConfig config;
    uint64_t counter = 0;
};

class E2EChecker {
public:
    explicit E2EChecker(const E2EConfig& config);
    // E2E_PXXCheck followed by the mapping to E2E_PCheckStatusType (R4.2 behaviour).
    E2ECheckStatus check(const uint8_t *data, size_t length, bool newDataAvailable = true);
    uint64_t lastCounter() const { return last; }
private:
    E2EConfig config;
    uint64_t last;
};

class E2EStateMachine {
public:
    explicit E2EStateMachine(const E2ESmConfig& config);
    E2ESmState check(E2ECheckStatus status);
    E2ESmState state() const { return current; }
    unsigned okCount() const;
    unsigned errorCount() const;
private:
    E2ESmConfig config;
    E2ESmState current = E2ESmState::NoData;
    std::vector<E2ECheckStatus> window;
    size_t next = 0;
};

} // namespace autosar

#endif
