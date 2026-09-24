// SPDX-License-Identifier: BSD-3-Clause
// AUTOSAR SecOC (SWS SecOC) for one Secured I-PDU with a counter-based freshness value:
//
//   Secured I-PDU      = Authentic I-PDU | truncated FV | truncated MAC   (bit packed, MSB first)
//   DataToAuthenticator = SecOCDataId (16 bit) | Authentic I-PDU | complete FV
//   MAC                 = AES-128-CMAC (OpenSSL libcrypto), truncated to its most significant bits
//
// The receiver rebuilds the complete FV from the transmitted least significant bits and
// its latest accepted FV, and accepts only a strictly newer FV (replay protection). With no
// FV bits transmitted it tries each FV from latest + 1 to latest + acceptanceWindow.
#ifndef AUTOSAR_PROTECTION_SECOC_H
#define AUTOSAR_PROTECTION_SECOC_H

#include <array>
#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace autosar {

using AesKey = std::array<uint8_t, 16>;
using Bytes = std::vector<uint8_t>;

// AES-128-CMAC (RFC 4493 / NIST SP 800-38B) via OpenSSL's EVP_MAC interface.
std::array<uint8_t, 16> aesCmac(const AesKey& key, const uint8_t *data, size_t length);
AesKey parseAesKey(const std::string& hex);

struct SecOcConfig {
    uint16_t dataId = 0;
    AesKey key{};
    unsigned freshnessBits = 64;      // complete FV length, multiple of 8, 8..64
    unsigned freshnessTxBits = 8;     // transmitted FV bits (0..freshnessBits; 0 needs acceptanceWindow >= 1)
    unsigned macTxBits = 24;          // transmitted MAC bits (1..128)
    uint64_t acceptanceWindow = 0;    // max accepted FV jump; 0 = unlimited
};

enum class SecOcVerifyResult { Ok, AuthenticationFailed, FreshnessFailed, Malformed };
const char *toString(SecOcVerifyResult result);

void validateSecOcConfig(const SecOcConfig& config);
size_t secOcTrailerBytes(const SecOcConfig& config);
// Full DataToAuthenticator for a given FV (exposed for the self-test and tooling).
Bytes secOcDataToAuthenticator(const SecOcConfig& config, const uint8_t *authentic, size_t length, uint64_t freshness);

class SecOcSender {
public:
    explicit SecOcSender(const SecOcConfig& config);
    // Returns the Secured I-PDU for the next FV (FV starts at 1 and increments per PDU).
    Bytes secure(const uint8_t *authentic, size_t length);
    uint64_t lastFreshness() const { return freshness; }
    // Fault injection: pretend 'count' PDUs were sent.
    void skip(uint64_t count) { freshness += count; }
private:
    SecOcConfig config;
    uint64_t freshness = 0;
};

class SecOcReceiver {
public:
    explicit SecOcReceiver(const SecOcConfig& config);
    // On Ok, 'authentic' holds the Authentic I-PDU and the latest FV is updated.
    SecOcVerifyResult verify(const uint8_t *secured, size_t length, Bytes& authentic, uint64_t *freshnessOut = nullptr);
    uint64_t latestFreshness() const { return latest; }
    // Candidate complete FV for a received truncated FV (counter-based construction).
    uint64_t reconstruct(uint64_t truncated) const;
private:
    SecOcConfig config;
    uint64_t latest = 0;
};

} // namespace autosar

#endif
