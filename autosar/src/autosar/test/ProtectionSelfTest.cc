// SPDX-License-Identifier: BSD-3-Clause
//
// Known-answer tests for the CRC library, the E2E profiles, the E2E state machine,
// AES-128-CMAC and SecOC. Expected values come from sources independent of this code:
// CRC "123456789" check values of the AUTOSAR CRC catalogue, E2E examples reproduced
// by the MIT-licensed autosar-e2e package (its test suite), and RFC 4493 for CMAC.
// With 'vectorFile' set, protected random PDUs are written as JSON so that
// tests/test_protection.py can verify them with autosar-e2e and pycryptodome.
#include <omnetpp.h>

#include <algorithm>
#include <fstream>
#include <functional>
#include <sstream>

#include "autosar/protection/Crc.h"
#include "autosar/protection/E2E.h"
#include "autosar/protection/SecOC.h"

using namespace omnetpp;

namespace autosar {

class ProtectionSelfTest : public cSimpleModule
{
    int passed = 0, failed = 0;

    void check(const std::string& name, bool condition)
    {
        condition ? ++passed : ++failed;
        EV_INFO << "CHECK " << name << (condition ? " PASS" : " FAIL") << endl;
        if (!condition)
            std::cout << "Protection self-test FAILED: " << name << endl;
    }

    static Bytes hex(const std::string& text)
    {
        Bytes out;
        for (size_t i = 0; i + 1 < text.size();) {
            if (text[i] == ' ') { ++i; continue; }
            out.push_back(uint8_t(std::stoul(text.substr(i, 2), nullptr, 16)));
            i += 2;
        }
        return out;
    }

    static std::string toHex(const uint8_t *data, size_t length)
    {
        static const char digits[] = "0123456789abcdef";
        std::string s;
        for (size_t i = 0; i < length; ++i) {
            s.push_back(digits[data[i] >> 4]);
            s.push_back(digits[data[i] & 15]);
        }
        return s;
    }
    static std::string toHex(const Bytes& b) { return toHex(b.data(), b.size()); }

    // Protects 'data' with consecutive counters and compares each result.
    void e2eVector(const std::string& name, const E2EConfig& config, Bytes data, const std::vector<std::string>& expected,
                   uint64_t firstCounter = 0)
    {
        for (size_t i = 0; i < expected.size(); ++i) {
            e2eWrite(config, data.data(), data.size(), firstCounter + i);
            check(name + "-counter" + std::to_string(firstCounter + i), data == hex(expected[i]));
            uint64_t counter = 0;
            check(name + "-verify" + std::to_string(firstCounter + i),
                  e2eVerify(config, data.data(), data.size(), &counter) && counter == firstCounter + i);
        }
    }

    static E2EConfig e2e(E2EProfile profile, uint32_t dataId, size_t offset = 0)
    {
        E2EConfig c;
        c.profile = profile;
        c.dataId = dataId;
        c.offset = offset;
        return c;
    }

    void testCrc()
    {
        const Bytes s = {'1', '2', '3', '4', '5', '6', '7', '8', '9'};
        check("crc8-check", crc8(s.data(), s.size(), 0, true) == 0x4B);
        check("crc8h2f-check", crc8h2f(s.data(), s.size(), 0, true) == 0xDF);
        check("crc16-check", crc16(s.data(), s.size(), 0, true) == 0x29B1);
        check("crc32-check", crc32(s.data(), s.size(), 0, true) == 0xCBF43926u);
        check("crc32p4-check", crc32p4(s.data(), s.size(), 0, true) == 0x1697D06Au);
        check("crc64-check", crc64(s.data(), s.size(), 0, true) == 0x995DC9BBDF1939FAull);
        // Chained calls over split areas equal one call over the whole buffer.
        check("crc8-chained", crc8(s.data() + 4, 5, crc8(s.data(), 4, 0, true), false) == 0x4B);
        check("crc16-chained", crc16(s.data() + 1, 8, crc16(s.data(), 1, 0, true), false) == 0x29B1);
        check("crc32p4-chained", crc32p4(s.data() + 7, 2, crc32p4(s.data(), 7, 0, true), false) == 0x1697D06Au);
        check("crc64-chained", crc64(s.data() + 3, 6, crc64(s.data(), 3, 0, true), false) == 0x995DC9BBDF1939FAull);
    }

    void testE2EVectors()
    {
        const Bytes zero8(8, 0);
        E2EConfig p01 = e2e(E2EProfile::P01, 0x123);
        e2eVector("p01-both", p01, zero8, {"cc 00 00 00 00 00 00 00", "91 01 00 00 00 00 00 00"});
        p01.dataIdMode = P01DataIdMode::Alt;
        e2eVector("p01-alt", p01, zero8, {"ce 00 00 00 00 00 00 00", "02 01 00 00 00 00 00 00"});
        p01.dataIdMode = P01DataIdMode::Low;
        e2eVector("p01-low", p01, zero8, {"ce 00 00 00 00 00 00 00", "93 01 00 00 00 00 00 00"});
        p01.dataIdMode = P01DataIdMode::Nibble;
        e2eVector("p01-nibble", p01, zero8, {"2a 10 00 00 00 00 00 00", "77 11 00 00 00 00 00 00"});

        E2EConfig p02 = e2e(E2EProfile::P02, 0);
        e2eVector("p02-zero-list", p02, zero8, {"45 01 00 00 00 00 00 00"}, 1);
        for (int i = 0; i < 16; ++i)
            p02.dataIdList[i] = uint8_t(i);
        Bytes ramp = {0, 1, 2, 3, 4, 5, 6, 7};
        e2eVector("p02-ramp", p02, ramp, {"61 01 02 03 04 05 06 07", "bc 02 02 03 04 05 06 07"}, 1);
        for (int i = 0; i < 16; ++i)
            p02.dataIdList[i] = uint8_t(i + 1);
        e2eVector("p02-list1", p02, zero8,
                  {"1b 01 00 00 00 00 00 00", "98 02 00 00 00 00 00 00", "31 03 00 00 00 00 00 00"}, 1);

        e2eVector("p04-short", e2e(E2EProfile::P04, 0x0A0B0C0D), Bytes(16, 0),
                  {"00 10 00 00 0a 0b 0c 0d 86 2b 05 56 00 00 00 00", "00 10 00 01 0a 0b 0c 0d a5 8e 68 07 00 00 00 00"});
        e2eVector("p04-someip-offset8", e2e(E2EProfile::P04, 0x0A0B0C0D, 8), Bytes(24, 0),
                  {"00 00 00 00 00 00 00 00 00 18 00 00 0a 0b 0c 0d 69 d7 50 2e 00 00 00 00",
                   "00 00 00 00 00 00 00 00 00 18 00 01 0a 0b 0c 0d 4a 72 3d 7f 00 00 00 00"});
        e2eVector("p05-short", e2e(E2EProfile::P05, 0x1234), zero8,
                  {"1c ca 00 00 00 00 00 00", "cf 8d 01 00 00 00 00 00"});
        e2eVector("p05-offset8", e2e(E2EProfile::P05, 0x1234, 8), Bytes(16, 0),
                  {"00 00 00 00 00 00 00 00 28 91 00 00 00 00 00 00", "00 00 00 00 00 00 00 00 fb d6 01 00 00 00 00 00"});
        e2eVector("p07-short", e2e(E2EProfile::P07, 0x0A0B0C0D), Bytes(24, 0),
                  {"1f b2 e7 37 fc ed bc d9 00 00 00 18 00 00 00 00 0a 0b 0c 0d 00 00 00 00",
                   "7b de 72 68 b8 e9 bc 27 00 00 00 18 00 00 00 01 0a 0b 0c 0d 00 00 00 00"});
        e2eVector("p07-offset8", e2e(E2EProfile::P07, 0x0A0B0C0D, 8), Bytes(32, 0),
                  {"00 00 00 00 00 00 00 00 17 f7 c8 17 32 38 65 a8 00 00 00 20 00 00 00 00 0a 0b 0c 0d 00 00 00 00",
                   "00 00 00 00 00 00 00 00 73 9b 5d 48 76 3c 65 56 00 00 00 20 00 00 00 01 0a 0b 0c 0d 00 00 00 00"});
    }

    // Protects PDUs 0..max(sendOrder) and feeds them to one checker in 'sendOrder'.
    std::vector<E2ECheckStatus> e2eSequence(E2EConfig config, size_t length, const std::vector<int>& sendOrder)
    {
        E2EChecker checker(config);
        std::vector<Bytes> sent;
        for (int i = 0; i <= *std::max_element(sendOrder.begin(), sendOrder.end()); ++i) {
            Bytes pdu(length, uint8_t(i));
            e2eWrite(config, pdu.data(), pdu.size(), i % e2eCounterModulus(config.profile));
            sent.push_back(pdu);
        }
        std::vector<E2ECheckStatus> statuses;
        for (int index : sendOrder)
            statuses.push_back(checker.check(sent[index].data(), length));
        return statuses;
    }

    void testE2EChecker()
    {
        using S = E2ECheckStatus;
        for (auto profile : {E2EProfile::P01, E2EProfile::P02, E2EProfile::P04, E2EProfile::P05, E2EProfile::P07}) {
            E2EConfig config = e2e(profile, 0x0123);
            config.maxDeltaCounter = 2;
            const std::string name = std::string("check-") + toString(profile);
            const size_t length = 24;
            check(name + "-sequence", e2eSequence(config, length, {0, 1, 1, 3, 6, 7})
                    == std::vector<S>({S::Ok, S::Ok, S::Repeated, S::OkSomeLost, S::WrongSequence, S::Ok}));
            // Counter wrap-around is continuous.
            if (e2eCounterModulus(profile) <= 256) {
                const int m = int(e2eCounterModulus(profile));
                check(name + "-wrap", e2eSequence(config, length, {m - 2, m - 1, m}).back() == S::Ok
                        && e2eSequence(config, length, {m - 2, m - 1, m})[1] == S::Ok);
            }
            // One flipped bit anywhere, including the header, is detected.
            E2EChecker checker(config);
            Bytes pdu(length, 0x5A);
            e2eWrite(config, pdu.data(), pdu.size(), 0);
            bool allDetected = true;
            for (size_t bit = 0; bit < length * 8; ++bit) {
                Bytes corrupt = pdu;
                corrupt[bit / 8] ^= uint8_t(1 << (bit % 8));
                uint64_t counter;
                // P01/P02 counter nibble bits change the counter; the CRC still covers them.
                allDetected &= !e2eVerify(config, corrupt.data(), corrupt.size(), &counter);
            }
            check(name + "-all-single-bit-errors", allDetected);
            check(name + "-nonewdata", checker.check(pdu.data(), length, false) == S::NoNewData);
            E2EConfig other = config;
            other.dataId = 0x0124;
            if (profile == E2EProfile::P02)
                other.dataIdList[0] ^= 1;
            uint64_t counter;
            check(name + "-wrong-dataid", !e2eVerify(other, pdu.data(), pdu.size(), &counter));
        }
        Bytes pdu(8, 0);
        E2EConfig p01 = e2e(E2EProfile::P01, 0x123);
        e2eWrite(p01, pdu.data(), pdu.size(), 14);
        pdu[1] = (pdu[1] & 0xF0) | 15;     // 15 is not a valid Profile 1 counter
        uint64_t counter;
        check("check-P01-counter15-invalid", !e2eVerify(p01, pdu.data(), pdu.size(), &counter));
        E2EConfig p04 = e2e(E2EProfile::P04, 0x0A0B0C0D);
        Bytes longer(20, 0);
        e2eWrite(p04, longer.data(), 16, 0);
        check("check-P04-length-field", !e2eVerify(p04, longer.data(), 20, &counter));
        bool rejected = false;
        try { validateE2EConfig(e2e(E2EProfile::P07, 1), 19); } catch (const std::invalid_argument&) { rejected = true; }
        check("reject-P07-header-too-long", rejected);
        rejected = false;
        try { E2EConfig p = e2e(E2EProfile::P02, 1, 2); validateE2EConfig(p, 8); } catch (const std::invalid_argument&) { rejected = true; }
        check("reject-P02-offset", rejected);
        rejected = false;
        try { validateE2EConfig(e2e(E2EProfile::P04, 1, size_t(-1)), 64); } catch (const std::invalid_argument&) { rejected = true; }
        check("reject-offset-wraparound", rejected);
    }

    void testStateMachine()
    {
        using S = E2ECheckStatus;
        using St = E2ESmState;
        E2ESmConfig config;   // window 3, init: 1 OK, valid: <=1 error, invalid: 2 OK and 0 errors
        E2EStateMachine sm(config);
        std::vector<St> states;
        for (auto s : {S::NoNewData, S::WrongSequence, S::Ok, S::Error, S::Ok, S::Error, S::Error, S::Ok, S::Ok, S::Ok, S::Ok})
            states.push_back(sm.check(s));
        check("sm-transitions", states == std::vector<St>({St::NoData, St::Init, St::Valid, St::Valid, St::Valid,
                St::Invalid, St::Invalid, St::Invalid, St::Invalid, St::Valid, St::Valid}));
        E2EStateMachine repeated(config);
        for (auto s : {S::Ok, S::Ok, S::Repeated, S::Repeated, S::Repeated})
            repeated.check(s);
        check("sm-repeated-invalidates", repeated.state() == St::Invalid);
        // [PRS_E2E_00466]: REPEATED and WRONGSEQUENCE are not E2E_P_ERROR; with 1 OK in the window
        // and no ERROR the VALID state holds (minOkStateValid 1, maxErrorStateValid 1).
        E2EStateMachine counterErrors(config);
        for (auto s : {S::Ok, S::Ok, S::Repeated, S::WrongSequence})
            counterErrors.check(s);
        check("sm-counter-errors-not-error-count", counterErrors.state() == St::Valid);
        counterErrors.check(S::Repeated);
        check("sm-counter-errors-lower-ok-count", counterErrors.state() == St::Invalid);
    }

    void testCmac()
    {
        const AesKey key = parseAesKey("2b7e151628aed2a6abf7158809cf4f3c");
        const Bytes m = hex("6bc1bee22e409f96e93d7e117393172aae2d8a571e03ac9c9eb76fac45af8e51"
                            "30c81c46a35ce411e5fbc1191a0a52eff69f2445df4f9b17ad2b417be66c3710");
        const std::pair<size_t, const char *> vectors[] = {
            {0, "bb1d6929e95937287fa37d129b756746"},
            {16, "070a16b46b4d4144f79bdd9dd04a287c"},
            {40, "dfa66747de9ae63030ca32611497c827"},
            {64, "51f0bebf7e3b9d92fc49741779363cfe"},
        };
        for (const auto& v : vectors) {
            const auto mac = aesCmac(key, m.data(), v.first);
            check("rfc4493-cmac-len" + std::to_string(v.first), toHex(mac.data(), mac.size()) == v.second);
        }
    }

    static SecOcConfig secoc(unsigned freshnessTxBits, unsigned macTxBits, unsigned freshnessBits = 64)
    {
        SecOcConfig c;
        c.dataId = 0x0100;
        c.key = parseAesKey("000102030405060708090a0b0c0d0e0f");
        c.freshnessBits = freshnessBits;
        c.freshnessTxBits = freshnessTxBits;
        c.macTxBits = macTxBits;
        return c;
    }

    void testSecOc()
    {
        using R = SecOcVerifyResult;
        const Bytes authentic = {0xDE, 0xAD, 0xBE, 0xEF};
        {
            // Layout: authentic | FV LSB | MAC MSBs, MAC over DataId|authentic|complete FV.
            SecOcConfig c = secoc(8, 24);
            SecOcSender tx(c);
            const Bytes secured = tx.secure(authentic.data(), authentic.size());
            const Bytes input = secOcDataToAuthenticator(c, authentic.data(), authentic.size(), 1);
            check("secoc-data-to-authenticator", toHex(input) == "0100deadbeef0000000000000001");
            const auto mac = aesCmac(c.key, input.data(), input.size());
            check("secoc-layout", secured.size() == 8 && std::equal(authentic.begin(), authentic.end(), secured.begin())
                    && secured[4] == 0x01 && std::equal(mac.begin(), mac.begin() + 3, secured.begin() + 5));
            SecOcReceiver rx(c);
            Bytes out;
            uint64_t fv = 0;
            check("secoc-verify-ok", rx.verify(secured.data(), secured.size(), out, &fv) == R::Ok && out == authentic && fv == 1);
            check("secoc-replay-truncated", rx.verify(secured.data(), secured.size(), out) == R::AuthenticationFailed);
            Bytes tampered = tx.secure(authentic.data(), authentic.size());
            tampered[0] ^= 0x01;
            check("secoc-tamper", rx.verify(tampered.data(), tampered.size(), out) == R::AuthenticationFailed);
            SecOcConfig wrongKey = c;
            wrongKey.key[15] ^= 0xFF;
            SecOcSender attacker(wrongKey);
            attacker.skip(2);
            const Bytes forged = attacker.secure(authentic.data(), authentic.size());
            check("secoc-wrong-key", rx.verify(forged.data(), forged.size(), out) == R::AuthenticationFailed);
            check("secoc-short-pdu", rx.verify(secured.data(), 3, out) == R::Malformed);
        }
        {
            // Truncated FV across the LSB wrap-around and after lost PDUs.
            SecOcConfig c = secoc(8, 32);
            SecOcSender tx(c);
            SecOcReceiver rx(c);
            Bytes out;
            bool ok = true;
            for (int i = 0; i < 600; ++i) {
                const Bytes s = tx.secure(authentic.data(), authentic.size());
                if (i % 7 == 3)
                    continue;       // lost PDU
                ok &= rx.verify(s.data(), s.size(), out) == R::Ok && rx.latestFreshness() == tx.lastFreshness();
            }
            check("secoc-truncated-wrap-and-loss", ok && rx.latestFreshness() == 600);
            tx.skip(256);           // a gap of more than 2^8 PDUs cannot be resynchronised
            const Bytes s = tx.secure(authentic.data(), authentic.size());
            check("secoc-truncated-desync", rx.verify(s.data(), s.size(), out) == R::AuthenticationFailed);
        }
        {
            SecOcConfig c = secoc(64, 128);
            SecOcSender tx(c);
            SecOcReceiver rx(c);
            Bytes out;
            const Bytes first = tx.secure(authentic.data(), authentic.size());
            const Bytes second = tx.secure(authentic.data(), authentic.size());
            check("secoc-full-fv", rx.verify(second.data(), second.size(), out) == R::Ok && rx.latestFreshness() == 2);
            check("secoc-full-fv-replay", rx.verify(first.data(), first.size(), out) == R::FreshnessFailed);
            c.acceptanceWindow = 3;
            SecOcReceiver windowed(c);
            tx.skip(4);
            const Bytes jump = tx.secure(authentic.data(), authentic.size());
            check("secoc-acceptance-window", windowed.verify(jump.data(), jump.size(), out) == R::FreshnessFailed);
        }
        {
            // Bit packed trailer: 4 FV bits + 28 MAC bits = 4 bytes.
            SecOcConfig c = secoc(4, 28, 16);
            SecOcSender tx(c);
            SecOcReceiver rx(c);
            Bytes out;
            bool ok = true;
            for (int i = 0; i < 40; ++i) {
                const Bytes s = tx.secure(authentic.data(), authentic.size());
                ok &= s.size() == 8 && (s[4] >> 4) == ((i + 1) & 0x0F) && rx.verify(s.data(), s.size(), out) == R::Ok;
            }
            check("secoc-bit-packed", ok);
        }
        {
            // No FV bits transmitted: the receiver tries latest+1 .. latest+acceptanceWindow.
            SecOcConfig c = secoc(0, 32);
            c.acceptanceWindow = 3;
            SecOcSender tx(c);
            SecOcReceiver rx(c);
            Bytes out;
            const Bytes s1 = tx.secure(authentic.data(), authentic.size());
            check("secoc-zero-fv-ok", s1.size() == 8 && rx.verify(s1.data(), s1.size(), out) == R::Ok && rx.latestFreshness() == 1);
            check("secoc-zero-fv-replay", rx.verify(s1.data(), s1.size(), out) == R::AuthenticationFailed);
            tx.secure(authentic.data(), authentic.size());      // lost: FV 2
            tx.secure(authentic.data(), authentic.size());      // lost: FV 3
            const Bytes s4 = tx.secure(authentic.data(), authentic.size());
            const Bytes s5 = tx.secure(authentic.data(), authentic.size());
            check("secoc-zero-fv-resync-after-loss", rx.verify(s4.data(), s4.size(), out) == R::Ok && rx.latestFreshness() == 4
                    && rx.verify(s5.data(), s5.size(), out) == R::Ok && rx.latestFreshness() == 5);
            tx.skip(3);                                         // FV 9 is 4 ahead of 5: outside the window
            const Bytes s9 = tx.secure(authentic.data(), authentic.size());
            check("secoc-zero-fv-window-exceeded", rx.verify(s9.data(), s9.size(), out) == R::AuthenticationFailed
                    && rx.latestFreshness() == 5);
            bool rejectedUnbounded = false;
            try { validateSecOcConfig(secoc(0, 32)); } catch (const std::invalid_argument&) { rejectedUnbounded = true; }
            check("reject-secoc-zero-fv-without-window", rejectedUnbounded);
        }
        {
            SecOcSender tx(secoc(8, 24, 8));
            tx.skip(255);
            bool exhausted = false;
            try { tx.secure(authentic.data(), authentic.size()); } catch (const std::runtime_error&) { exhausted = true; }
            check("secoc-freshness-exhausted", exhausted);
        }
        bool rejected = false;
        try { validateSecOcConfig(secoc(8, 0)); } catch (const std::invalid_argument&) { rejected = true; }
        check("reject-secoc-zero-mac", rejected);
        rejected = false;
        try { parseAesKey("00"); } catch (const std::invalid_argument&) { rejected = true; }
        check("reject-short-key", rejected);
    }

    // Random PDUs for the independent Python reference check.
    void writeVectors(const std::string& path)
    {
        cRNG *rng = getRNG(0);
        auto randomBytes = [&](size_t n) {
            Bytes b(n);
            for (auto& x : b)
                x = uint8_t(rng->intRand(256));
            return b;
        };
        std::ofstream out(path);
        out << "{\"e2e\": [";
        const char *separator = "";
        struct Case { E2EProfile profile; P01DataIdMode mode; size_t length, offset; };
        const Case cases[] = {
            {E2EProfile::P01, P01DataIdMode::Both, 8, 0}, {E2EProfile::P01, P01DataIdMode::Alt, 8, 0},
            {E2EProfile::P01, P01DataIdMode::Low, 6, 0}, {E2EProfile::P01, P01DataIdMode::Nibble, 8, 0},
            {E2EProfile::P01, P01DataIdMode::Both, 8, 3}, {E2EProfile::P02, P01DataIdMode::Both, 8, 0},
            {E2EProfile::P02, P01DataIdMode::Both, 32, 0}, {E2EProfile::P04, P01DataIdMode::Both, 12, 0},
            {E2EProfile::P04, P01DataIdMode::Both, 64, 8}, {E2EProfile::P05, P01DataIdMode::Both, 64, 0},
            {E2EProfile::P05, P01DataIdMode::Both, 40, 8}, {E2EProfile::P07, P01DataIdMode::Both, 20, 0},
            {E2EProfile::P07, P01DataIdMode::Both, 256, 8},
        };
        for (const auto& k : cases) {
            for (int n = 0; n < 20; ++n) {
                E2EConfig c = e2e(k.profile, 0, k.offset);
                c.dataIdMode = k.mode;
                c.dataId = k.profile == E2EProfile::P04 || k.profile == E2EProfile::P07 ? rng->intRand() : rng->intRand(0x10000);
                if (k.mode == P01DataIdMode::Nibble)
                    c.dataId &= 0x0FFF;
                for (auto& x : c.dataIdList)
                    x = uint8_t(rng->intRand(256));
                const uint64_t counter = rng->intRand() % e2eCounterModulus(k.profile);
                Bytes pdu = randomBytes(k.length);
                e2eWrite(c, pdu.data(), pdu.size(), counter);
                out << separator << "{\"profile\": \"" << toString(k.profile) << "\", \"mode\": " << int(k.mode)
                    << ", \"dataId\": " << c.dataId << ", \"offset\": " << k.offset << ", \"counter\": " << counter
                    << ", \"dataIdList\": \"" << toHex(c.dataIdList.data(), 16) << "\", \"pdu\": \"" << toHex(pdu) << "\"}";
                separator = ", ";
            }
        }
        out << "], \"secoc\": [";
        separator = "";
        const unsigned layouts[][3] = {{8, 24, 64}, {4, 28, 16}, {16, 64, 32}, {64, 128, 64}, {0, 32, 64}, {12, 20, 32}};
        for (const auto& layout : layouts) {
            for (int n = 0; n < 10; ++n) {
                SecOcConfig c = secoc(layout[0], layout[1], layout[2]);
                c.acceptanceWindow = layout[0] == 0 ? 1 : 0;    // required without FV bits; no effect on the sender
                c.dataId = uint16_t(rng->intRand(0x10000));
                const Bytes key = randomBytes(16);
                std::copy(key.begin(), key.end(), c.key.begin());
                SecOcSender tx(c);
                tx.skip(rng->intRand(layout[2] == 16 ? 60000 : 100000));
                const Bytes authentic = randomBytes(1 + rng->intRand(60));
                const Bytes secured = tx.secure(authentic.data(), authentic.size());
                out << separator << "{\"dataId\": " << c.dataId << ", \"key\": \"" << toHex(c.key.data(), 16)
                    << "\", \"freshnessBits\": " << c.freshnessBits << ", \"freshnessTxBits\": " << c.freshnessTxBits
                    << ", \"macTxBits\": " << c.macTxBits << ", \"freshness\": " << tx.lastFreshness()
                    << ", \"authentic\": \"" << toHex(authentic) << "\", \"secured\": \"" << toHex(secured) << "\"}";
                separator = ", ";
            }
        }
        out << "]}\n";
    }

  protected:
    virtual void initialize() override
    {
        testCrc();
        testE2EVectors();
        testE2EChecker();
        testStateMachine();
        testCmac();
        testSecOc();
        const std::string vectors = par("vectorFile").stdstringValue();
        if (!vectors.empty())
            writeVectors(vectors);
        std::cout << "Protection self-test: " << passed << " passed, " << failed << " failed" << endl;
    }

    virtual void finish() override
    {
        recordScalar("checksPassed", passed);
        recordScalar("checksFailed", failed);
    }
};

Define_Module(ProtectionSelfTest);

} // namespace autosar
