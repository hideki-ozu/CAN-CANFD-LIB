// SPDX-License-Identifier: BSD-3-Clause
#include "autosar/protection/SecOC.h"

#include <openssl/core_names.h>
#include <openssl/evp.h>
#include <openssl/params.h>

#include <algorithm>
#include <memory>
#include <stdexcept>

namespace autosar {
namespace {

uint64_t lowBits(uint64_t value, unsigned bits) { return bits >= 64 ? value : value & ((1ull << bits) - 1); }

// Appends 'bits' bits of 'value' (MSB first) at bit position 'pos' of 'out'.
void putBits(Bytes& out, size_t& pos, uint64_t value, unsigned bits)
{
    for (unsigned i = 0; i < bits; ++i, ++pos)
        if ((value >> (bits - 1 - i)) & 1)
            out[pos / 8] |= uint8_t(0x80 >> (pos % 8));
}

uint64_t getBits(const uint8_t *in, size_t& pos, unsigned bits)
{
    uint64_t value = 0;
    for (unsigned i = 0; i < bits; ++i, ++pos)
        value = (value << 1) | ((in[pos / 8] >> (7 - pos % 8)) & 1);
    return value;
}

struct MacDeleter { void operator()(EVP_MAC *m) const { EVP_MAC_free(m); } };
struct MacCtxDeleter { void operator()(EVP_MAC_CTX *c) const { EVP_MAC_CTX_free(c); } };

} // namespace

std::array<uint8_t, 16> aesCmac(const AesKey& key, const uint8_t *data, size_t length)
{
    static std::unique_ptr<EVP_MAC, MacDeleter> mac(EVP_MAC_fetch(nullptr, "CMAC", nullptr));
    if (!mac)
        throw std::runtime_error("OpenSSL: CMAC is not available");
    std::unique_ptr<EVP_MAC_CTX, MacCtxDeleter> ctx(EVP_MAC_CTX_new(mac.get()));
    char cipher[] = "AES-128-CBC";
    OSSL_PARAM params[] = {
        OSSL_PARAM_construct_utf8_string(OSSL_MAC_PARAM_CIPHER, cipher, 0),
        OSSL_PARAM_construct_end(),
    };
    std::array<uint8_t, 16> out{};
    size_t outLength = 0;
    if (!ctx || EVP_MAC_init(ctx.get(), key.data(), key.size(), params) != 1
            || EVP_MAC_update(ctx.get(), data, length) != 1
            || EVP_MAC_final(ctx.get(), out.data(), &outLength, out.size()) != 1 || outLength != out.size())
        throw std::runtime_error("OpenSSL: AES-128-CMAC calculation failed");
    return out;
}

AesKey parseAesKey(const std::string& hex)
{
    if (hex.size() != 32)
        throw std::invalid_argument("SecOC key must be 32 hex digits (AES-128)");
    AesKey key{};
    for (size_t i = 0; i < 16; ++i) {
        const std::string byte = hex.substr(2 * i, 2);
        if (byte.find_first_not_of("0123456789abcdefABCDEF") != std::string::npos)
            throw std::invalid_argument("SecOC key contains a non-hex digit");
        key[i] = uint8_t(std::stoul(byte, nullptr, 16));
    }
    return key;
}

const char *toString(SecOcVerifyResult result)
{
    switch (result) {
        case SecOcVerifyResult::Ok: return "OK";
        case SecOcVerifyResult::AuthenticationFailed: return "AUTHENTICATION_FAILED";
        case SecOcVerifyResult::FreshnessFailed: return "FRESHNESS_FAILED";
        case SecOcVerifyResult::Malformed: return "MALFORMED";
    }
    return "?";
}

void validateSecOcConfig(const SecOcConfig& c)
{
    if (c.freshnessBits < 8 || c.freshnessBits > 64 || c.freshnessBits % 8 != 0)
        throw std::invalid_argument("SecOC freshnessBits must be a multiple of 8 in 8..64");
    if (c.freshnessTxBits > c.freshnessBits)
        throw std::invalid_argument("SecOC freshnessTxBits must not exceed freshnessBits");
    if (c.macTxBits < 1 || c.macTxBits > 128)
        throw std::invalid_argument("SecOC macTxBits must be in 1..128");
}

size_t secOcTrailerBytes(const SecOcConfig& c)
{
    return (c.freshnessTxBits + c.macTxBits + 7) / 8;
}

Bytes secOcDataToAuthenticator(const SecOcConfig& c, const uint8_t *authentic, size_t length, uint64_t freshness)
{
    Bytes data;
    data.reserve(2 + length + c.freshnessBits / 8);
    data.push_back(c.dataId >> 8);
    data.push_back(c.dataId & 0xFF);
    data.insert(data.end(), authentic, authentic + length);
    for (int shift = int(c.freshnessBits) - 8; shift >= 0; shift -= 8)
        data.push_back((freshness >> shift) & 0xFF);
    return data;
}

SecOcSender::SecOcSender(const SecOcConfig& config) : config(config)
{
    validateSecOcConfig(config);
}

Bytes SecOcSender::secure(const uint8_t *authentic, size_t length)
{
    if (freshness >= lowBits(~0ull, config.freshnessBits))
        throw std::runtime_error("SecOC freshness counter exhausted");
    ++freshness;
    const Bytes toAuthenticate = secOcDataToAuthenticator(config, authentic, length, freshness);
    const auto mac = aesCmac(config.key, toAuthenticate.data(), toAuthenticate.size());
    Bytes secured(length + secOcTrailerBytes(config), 0);
    std::copy(authentic, authentic + length, secured.begin());
    size_t pos = length * 8;
    putBits(secured, pos, lowBits(freshness, config.freshnessTxBits), config.freshnessTxBits);
    for (unsigned bit = 0; bit < config.macTxBits; bit += 8) {
        const unsigned n = std::min(8u, config.macTxBits - bit);
        putBits(secured, pos, mac[bit / 8] >> (8 - n), n);
    }
    return secured;
}

SecOcReceiver::SecOcReceiver(const SecOcConfig& config) : config(config)
{
    validateSecOcConfig(config);
}

uint64_t SecOcReceiver::reconstruct(uint64_t truncated) const
{
    const unsigned tx = config.freshnessTxBits;
    if (tx >= config.freshnessBits)
        return truncated;
    if (tx == 0)
        return latest + 1;
    // Received LSBs larger than the latest LSBs: same MSBs; otherwise the MSBs wrapped.
    const uint64_t msb = latest >> tx;
    const uint64_t high = truncated > lowBits(latest, tx) ? msb : msb + 1;
    return lowBits((high << tx) | truncated, config.freshnessBits);
}

SecOcVerifyResult SecOcReceiver::verify(const uint8_t *secured, size_t length, Bytes& authentic, uint64_t *freshnessOut)
{
    const size_t trailer = secOcTrailerBytes(config);
    if (length < trailer)
        return SecOcVerifyResult::Malformed;
    const size_t authenticLength = length - trailer;
    size_t pos = authenticLength * 8;
    const uint64_t truncated = getBits(secured, pos, config.freshnessTxBits);
    const uint64_t candidate = reconstruct(truncated);
    if (candidate <= latest)
        return SecOcVerifyResult::FreshnessFailed;       // only possible with the complete FV transmitted
    if (config.acceptanceWindow != 0 && candidate - latest > config.acceptanceWindow)
        return SecOcVerifyResult::FreshnessFailed;
    const Bytes toAuthenticate = secOcDataToAuthenticator(config, secured, authenticLength, candidate);
    const auto mac = aesCmac(config.key, toAuthenticate.data(), toAuthenticate.size());
    for (unsigned bit = 0; bit < config.macTxBits; bit += 8) {
        const unsigned n = std::min(8u, config.macTxBits - bit);
        if (getBits(secured, pos, n) != uint64_t(mac[bit / 8] >> (8 - n)))
            return SecOcVerifyResult::AuthenticationFailed;
    }
    latest = candidate;
    authentic.assign(secured, secured + authenticLength);
    if (freshnessOut)
        *freshnessOut = candidate;
    return SecOcVerifyResult::Ok;
}

} // namespace autosar
