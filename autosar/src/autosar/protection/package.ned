// SPDX-License-Identifier: BSD-3-Clause
//
// Common parameters of every module that protects or checks PDUs
// (signalsandgateways.inet4.protection.*, soa4core Publisher/Subscriber):
//
//   string e2eProfile            "none", "P01", "P02", "P04", "P05", "P07"
//   int    e2eDataId             DataID; -1 = default of the module (CAN: identifier)
//   string e2eDataIdMode         P01 only: "both", "alt", "low", "nibble"
//   string e2eDataIdList         P02 only: 16 byte values, e.g. "0x10 0x11 ..."
//   int    e2eOffset             byte offset of the E2E header in the protected area
//   int    e2eMaxDeltaCounter    largest counter jump reported as OKSOMELOST
//   int    e2eSm*                E2E state machine window and thresholds
//   bool   secocEnabled          append FV and MAC (AES-128-CMAC) to the PDU
//   int    secocDataId           SecOCDataId (16 bit); -1 = default of the module
//   string secocKey              AES-128 key, 32 hex digits
//   int    secocFreshnessBits    complete FV length (8..64, multiple of 8)
//   int    secocFreshnessTxBits  transmitted FV bits
//   int    secocMacTxBits        transmitted MAC bits
//   int    secocAcceptanceWindow largest accepted FV jump, 0 = unlimited
package autosar.protection;
