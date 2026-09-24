// SPDX-License-Identifier: BSD-3-Clause
// Reads the common E2E/SecOC NED parameters (see autosar/protection/package.ned for
// the parameter list each protected module declares).
#ifndef AUTOSAR_PROTECTION_PROTECTIONPARAMS_H
#define AUTOSAR_PROTECTION_PROTECTIONPARAMS_H

#include <omnetpp.h>

#include <set>
#include <string>

#include "autosar/protection/E2E.h"
#include "autosar/protection/SecOC.h"

namespace autosar {

struct ProtectionConfig {
    E2EConfig e2e;
    E2ESmConfig sm;
    bool secocEnabled = false;
    SecOcConfig secoc;
};

// e2eDataId / secocDataId of -1 select the module's defaults (e.g. the CAN identifier).
ProtectionConfig readProtectionConfig(omnetpp::cComponent *module, uint32_t e2eDefaultDataId, uint32_t secocDefaultDataId);

// Comma separated 1-based transmission indices, e.g. "5,17" (fault injection).
std::set<long> parseIndexList(const char *text);

// Scalars and a status vector for one protected receive path.
class ProtectionStatistics {
public:
    void count(E2ECheckStatus status);
    void count(SecOcVerifyResult result);
    void record(omnetpp::cComponent *owner, const std::string& prefix) const;
    long e2e[6] = {};
    long secoc[4] = {};
    long smValid = 0, smInvalid = 0;
};

} // namespace autosar

#endif
