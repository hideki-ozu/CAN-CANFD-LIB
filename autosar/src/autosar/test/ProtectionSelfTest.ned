// SPDX-License-Identifier: BSD-3-Clause
package autosar.test;

// Known-answer tests of CRC, E2E, E2E state machine, AES-CMAC and SecOC.
simple ProtectionSelfTest
{
    parameters:
        @class(autosar::ProtectionSelfTest);
        string vectorFile = default("");   // JSON with random protected PDUs for external checks
}
