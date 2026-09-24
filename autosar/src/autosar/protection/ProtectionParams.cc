// SPDX-License-Identifier: BSD-3-Clause
#include "autosar/protection/ProtectionParams.h"

#include <stdexcept>

using namespace omnetpp;

namespace autosar {
namespace {

std::array<uint8_t, 16> parseDataIdList(const char *text)
{
    std::array<uint8_t, 16> list{};
    cStringTokenizer tokenizer(text, " ,");
    size_t i = 0;
    while (tokenizer.hasMoreTokens()) {
        const char *token = tokenizer.nextToken();
        char *end = nullptr;
        const unsigned long value = std::strtoul(token, &end, 0);
        if (*end != '\0' || value > 0xFF || i >= list.size())
            throw cRuntimeError("e2eDataIdList must hold 16 byte values, got '%s'", text);
        list[i++] = uint8_t(value);
    }
    if (i != list.size())
        throw cRuntimeError("e2eDataIdList must hold 16 byte values, got %zu", i);
    return list;
}

// Reads an integer parameter that is stored in an unsigned field; a negative value would wrap.
unsigned long long nonNegative(cComponent *module, const char *name)
{
    const long long value = module->par(name).intValue();
    if (value < 0)
        throw std::invalid_argument(std::string(name) + " must not be negative, got " + std::to_string(value));
    return value;
}

} // namespace

ProtectionConfig readProtectionConfig(cComponent *module, uint32_t e2eDefaultDataId, uint32_t secocDefaultDataId)
{
    ProtectionConfig config;
    try {
        E2EConfig& e2e = config.e2e;
        e2e.profile = parseE2EProfile(module->par("e2eProfile").stdstringValue());
        const long long dataId = module->par("e2eDataId").intValue();
        e2e.dataId = dataId < 0 ? e2eDefaultDataId : uint32_t(dataId);
        e2e.dataIdMode = parseP01DataIdMode(module->par("e2eDataIdMode").stdstringValue());
        if (e2e.profile == E2EProfile::P02)
            e2e.dataIdList = parseDataIdList(module->par("e2eDataIdList").stringValue());
        e2e.offset = nonNegative(module, "e2eOffset");
        e2e.maxDeltaCounter = nonNegative(module, "e2eMaxDeltaCounter");
        E2ESmConfig& sm = config.sm;
        sm.windowSize = nonNegative(module, "e2eSmWindowSize");
        sm.minOkStateInit = nonNegative(module, "e2eSmMinOkStateInit");
        sm.maxErrorStateInit = nonNegative(module, "e2eSmMaxErrorStateInit");
        sm.minOkStateValid = nonNegative(module, "e2eSmMinOkStateValid");
        sm.maxErrorStateValid = nonNegative(module, "e2eSmMaxErrorStateValid");
        sm.minOkStateInvalid = nonNegative(module, "e2eSmMinOkStateInvalid");
        sm.maxErrorStateInvalid = nonNegative(module, "e2eSmMaxErrorStateInvalid");

        config.secocEnabled = module->par("secocEnabled").boolValue();
        SecOcConfig& secoc = config.secoc;
        const long long secocDataId = module->par("secocDataId").intValue();
        const uint32_t selected = secocDataId < 0 ? secocDefaultDataId : uint32_t(secocDataId);
        if (selected > 0xFFFF)
            throw std::invalid_argument("secocDataId is 16 bit");
        secoc.dataId = uint16_t(selected);
        secoc.key = parseAesKey(module->par("secocKey").stdstringValue());
        secoc.freshnessBits = nonNegative(module, "secocFreshnessBits");
        secoc.freshnessTxBits = nonNegative(module, "secocFreshnessTxBits");
        secoc.macTxBits = nonNegative(module, "secocMacTxBits");
        secoc.acceptanceWindow = nonNegative(module, "secocAcceptanceWindow");
        if (config.secocEnabled)
            validateSecOcConfig(secoc);
    }
    catch (const std::invalid_argument& e) {
        throw cRuntimeError(module, "%s", e.what());
    }
    return config;
}

std::set<long> parseIndexList(const char *text)
{
    std::set<long> indices;
    cStringTokenizer tokenizer(text, ", ");
    while (tokenizer.hasMoreTokens()) {
        const char *token = tokenizer.nextToken();
        char *end = nullptr;
        const long value = std::strtol(token, &end, 10);
        if (*end != '\0' || value < 1)
            throw cRuntimeError("fault index list expects positive integers, got '%s'", text);
        indices.insert(value);
    }
    return indices;
}

void ProtectionStatistics::count(E2ECheckStatus status)
{
    ++e2e[int(status)];
}

void ProtectionStatistics::count(SecOcVerifyResult result)
{
    ++secoc[int(result)];
}

void ProtectionStatistics::record(cComponent *owner, const std::string& prefix) const
{
    static const E2ECheckStatus statuses[] = {E2ECheckStatus::Ok, E2ECheckStatus::NoNewData, E2ECheckStatus::Error,
            E2ECheckStatus::Repeated, E2ECheckStatus::OkSomeLost, E2ECheckStatus::WrongSequence};
    for (auto status : statuses)
        owner->recordScalar((prefix + "e2e" + toString(status)).c_str(), e2e[int(status)]);
    static const SecOcVerifyResult results[] = {SecOcVerifyResult::Ok, SecOcVerifyResult::AuthenticationFailed,
            SecOcVerifyResult::FreshnessFailed, SecOcVerifyResult::Malformed};
    for (auto result : results)
        owner->recordScalar((prefix + "secoc" + toString(result)).c_str(), secoc[int(result)]);
    owner->recordScalar((prefix + "e2eSmValidReceptions").c_str(), smValid);
    owner->recordScalar((prefix + "e2eSmInvalidReceptions").c_str(), smInvalid);
}

} // namespace autosar
