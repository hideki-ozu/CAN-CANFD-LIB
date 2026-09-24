# AUTOSAR E2E保護とSecOC

CAN／CAN-FDフレームとSOME/IPイベントに、**AUTOSAR E2E**（Profile 1/2/4/5/7、E2E状態機械）と **SecOC**（AES-128-CMAC、カウンタ方式のフレッシュネス値）を付けます。送信ECU（またはPublisher）で保護し、受信ECU（またはSubscriber）で検証します。ゲートウェイはバイト列をそのまま転送するため、CAN → Ethernet（独自トンネル／IEEE 1722）→ CAN の全区間をエンドツーエンドで保護します。

| 部分 | 場所 | 内容 |
|---|---|---|
| プロトコル本体 | `autosar/src/autosar/protection/`（本リポジトリ、BSD-3-Clause） | CRCライブラリ、E2Eプロファイル、E2E状態機械、SecOC。INETに依存しない共通ライブラリ `libAutosarProtection.so` |
| CAN/CAN-FD | `upstream/SignalsAndGateways/src-inet4/signalsandgateways/inet4/protection/`（`patches/SignalsAndGateways.patch`） | `SecuredCanSourceApp`（送信ECU）、`SecuredCanSink`（受信ECU） |
| CANの送信フック | `patches/FiCo4OMNeT.patch` | `CanTrafficSourceAppBase::prepareTransmission()`（送信直前にペイロードを書き換える仮想関数） |
| SOME/IP | `upstream/SOA4CoRE/src-inet4/soa4core/protection/`（`patches/SOA4CoRE.patch`） | Publisher／Subscriberのパラメータで、SOME/IPエンドポイントが保護・検証 |
| MAC計算 | OpenSSL 3 libcrypto（`EVP_MAC` の CMAC） | 動的リンクのみ。OpenSSL自体は同梱しません |

AES-128-CMACは決定的なアルゴリズムで、正しい実装なら自前実装でもlibcryptoでも出力は同じです（違いは定数時間性・速度・保守性で、シミュレーション結果には影響しません）。そのためlibcryptoを使い、試験では別実装のpycryptodomeと照合しています。

## 対応範囲

### E2E

| プロファイル | CRC | ヘッダ（`e2eOffset`の位置） | カウンタ | DataID | 主な用途 |
|---|---|---|---|---|---|
| P01 | CRC-8 SAE J1850（0x1D） | CRC 1B、次のバイトの下位4bitにカウンタ | 0～14 | 16bit。`both`／`alt`／`low`／`nibble`（1C: 上位バイトの下位4bitを上位4bitに送信） | Classical CAN |
| P02 | CRC-8H2F（0x2F） | 先頭固定: CRC 1B、次のバイトの下位4bitにカウンタ | 0～15 | カウンタごとのDataIDList（16バイト） | Classical CAN |
| P04 | CRC-32P4（0xF4ACFB13） | Length 16bit・Counter 16bit・DataID 32bit・CRC 32bit（ビッグエンディアン、12B） | 16bit | 32bit | SOME/IP・大きいPDU |
| P05 | CRC-16 CCITT-FALSE（0x1021） | CRC 16bit（リトルエンディアン）・Counter 8bit（3B） | 8bit | 16bit（CRC計算の最後に下位・上位バイト） | CAN-FD |
| P07 | CRC-64（ECMA-182） | CRC 64bit・Length 32bit・Counter 32bit・DataID 32bit（ビッグエンディアン、20B） | 32bit | 32bit | 大きいPDU・SOME/IP |

- CRCは、保護対象バイト列のうちCRCフィールド以外の全バイトにかかります（ヘッダより前のバイトも含む。SOME/IPでは後述の上位ヘッダ8B）。P04/P07は長さとDataIDのフィールドも照合します。
- 受信側のチェック結果（E2E_PCheckStatusType相当）: `OK`、`OKSOMELOST`（カウンタの飛びが`e2eMaxDeltaCounter`以下）、`REPEATED`、`WRONGSEQUENCE`、`ERROR`（CRC・DataID・長さ・P01のカウンタ15）、`NONEWDATA`（`e2eReceptionTimeout`の間、新しいデータなし。CANのみ）。
- **E2E状態機械**: `NODATA`→`INIT`→`VALID`／`INVALID`。直近`e2eSmWindowSize`回の結果のうち、OK（OKSOMELOSTを含む）とERRORの数を、状態ごとの閾値（`e2eSmMinOkState*`、`e2eSmMaxErrorState*`）と比べます。REPEATED・WRONGSEQUENCE・NONEWDATAはどちらにも数えません（AUTOSAR PRS_E2E_00466: ErrorCountはE2E_P_ERRORの数のみ。カウンタ異常はウィンドウの枠を占めるのでOKの数を減らします）。

### SecOC

```text
Secured I-PDU       = Authentic I-PDU | 送信するFV（下位ビット） | MAC（上位ビット）   （ビット詰め、MSBから）
DataToAuthenticator = SecOCDataId（16bit） | Authentic I-PDU | 完全なFV
MAC                 = AES-128-CMAC(key, DataToAuthenticator) を上位 secocMacTxBits に切り詰め
```

- FVは送信PDUごとに1ずつ増えるカウンタ（1から開始、`secocFreshnessBits`＝8～64bit）。`secocFreshnessTxBits` だけを送ります（0～全ビット）。
- 受信側は最後に受理したFVから完全なFVを復元します。受信した下位ビットが最後の値の下位ビットより大きければ上位ビットはそのまま、そうでなければ上位ビット+1とします。復元値が最後の値以下なら `FRESHNESS_FAILED`（完全なFVを送る場合のみ起こる）、`secocAcceptanceWindow` を超える飛びも `FRESHNESS_FAILED` です。MACが一致しなければ `AUTHENTICATION_FAILED` です。
- FVを送らない構成（`secocFreshnessTxBits=0`）では、受信側は最後の値+1から+`secocAcceptanceWindow`までのFVを順に試し、MACが一致したFVで同期し直します。PDUを失っても受理ウィンドウ内なら復帰できます。無制限の探索はできないため、この構成では `secocAcceptanceWindow` ≥ 1 が必須です（0なら設定エラー）。
- 検証に失敗したPDUは破棄し、E2Eには渡しません。切り詰めたFVでは、再送（リプレイ）されたPDUの復元FVが新しい値になるため、MAC不一致（`AUTHENTICATION_FAILED`）として検出されます。
- 重ね順は **E2Eが内側、SecOCが外側** です。E2EヘッダはAuthentic I-PDUの中にあり、MACの対象になります。

### PDUレイアウト

**CAN/CAN-FD**（`SecuredCanSourceApp`）: CANペイロード長は変えず、その中に配置します。DataIDの既定値（`-1`）はCAN IDです。E2Eヘッダ以外のデータバイトは、FiCoの試験パターン（(CAN ID + バイト位置) & 0xFF）のままです。

```text
Classical CAN 8B, P01 + SecOC(FV 8bit, MAC 24bit):   | CRC | Ctr | data 2B | FV | MAC 3B |
CAN-FD 64B,      P05 + SecOC(FV 16bit, MAC 64bit):   | CRC16 | Ctr | data 51B | FV 2B | MAC 8B |
CAN-FD 64B,      P07 + SecOC(FV 32bit, MAC 128bit):  | P07 header 20B | data 24B | FV 4B | MAC 16B |
```

**SOME/IP**（通知イベント。SOME/IP-SDは対象外）:

```text
E2E対象     = SOME/IPヘッダのRequest ID～Return Code（8B） | ペイロード   （E2Eヘッダは e2eOffset=8、ペイロードの先頭）
Authentic I-PDU = Message ID（4B） | E2E対象                      （Lengthフィールドは除外）
ワイヤ上のペイロード = E2Eヘッダ | イベントデータ | FV | MAC      （Lengthはこの長さで設定）
```

E2E対象の取り方は、SOME/IP変換器の上にE2E変換器を重ねた構成（上位ヘッダ64bitの後にE2Eヘッダ）に合わせています。既定のDataIDは、E2E P04/P07が「サービスID << 16 | イベントID」、その他のプロファイルとSecOCがイベントIDです。保護状態（カウンタ・FV）はPublisherのエンドポイントごとに持ちます。Subscriberにはイベントデータだけを渡します（E2EヘッダとSecOCの付加部分は除去）。イベントデータのバイトは (セッションID + バイト位置) & 0xFF です。

## 使い方

### CAN/CAN-FD（`examples/mixed`）

```ini
*.ecu*[*].sourceApp[0].typename = "signalsandgateways.inet4.protection.SecuredCanSourceApp"
*.ecu*[*].sinkApp[*].typename = "signalsandgateways.inet4.protection.SecuredCanSink"
*.ecu*[0].sourceApp[0].e2eProfile = "P01"
*.ecu*[0].sourceApp[0].secocEnabled = true
*.ecu*[*].sinkApp[0].e2eProfile = "P01"
*.ecu*[*].sinkApp[0].secocEnabled = true
**.secocKey = "2b7e151628aed2a6abf7158809cf4f3c"
```

受信側のパラメータはシンクごとに1組です。受信ECUが複数のストリームを受ける例では、入力バッファとシンクを2つずつにし（`numInputBuffer = 2`、`numSinkApps = 2`、`bufferIn[1].destination_gates = "sinkApp[1].dataIn"`）、Classical CAN用とCAN-FD用で別の設定にしています。

| 設定 | 内容 |
|---|---|
| `E2eSecOc` | Classical CAN 8B: P01 + SecOC（FV 8bit、MAC 24bit）。CAN-FD 64B: P05 + SecOC（FV 16bit、MAC 64bit）。独自トンネル |
| `E2eSecOcAvtp` | `E2eSecOc` をIEEE 1722 NTSCF + ACF CANで転送（pcapでワイヤ検証） |
| `E2eP02P07Avtp` | Classical CAN: P02のみ（SecOCなし）。CAN-FD: P07 + SecOC（FV 32bit、MAC 128bit）。TSCF |
| `E2eSecOcFaults` | ID 256（ecuA[0]）の30フレームのうち、5・20・21番目に1bit誤り、10番目に9番目の再送、15番目にカウンタを3つ飛ばす。受信タイムアウト12ms |
| `E2eOnlyFaults` | 同じ故障でSecOCなし（E2Eのみ） |
| `SecOcWrongKey` | ecuA[0]がID 256を別の鍵で署名 |

```bash
./scripts/run-mixed.sh E2eSecOcAvtp       # CLI（make run-protection）
./scripts/run-gui.sh E2eSecOcFaults       # Qtenv。sinkAppのe2eStatus/e2eSmState/secocResultベクタを表示可能
python3 tests/test_protection.py          # E2E/SecOCの検証（make test-protection）
```

### SOME/IP（`examples/someip`）

Publisher・Subscriber（`soa4core.applications.*`）に同名のパラメータがあります。`**.services[0].e2eProfile = "P04"` のように両方に同じ値を設定します。

| 設定 | 内容 |
|---|---|
| `SomeIpE2eSecOc` | P04 + SecOC（FV 32bit、MAC 64bit）。Node2はSOME/IP TCP、Node3はSOME/IP UDP |
| `SomeIpE2eP07Mcast` | P07 + SecOC（完全なFV 64bit、MAC 128bit）。UDPマルチキャスト |
| `SomeIpE2eSecOcFaults` | 各Publisherエンドポイントで、10番目に1bit誤り、20番目に19番目の再送、30番目にカウンタを3つ飛ばす |
| `SomeIpSecOcWrongKey` | Node3だけ別の鍵で検証 |

```bash
./scripts/run-someip.sh SomeIpE2eSecOc
```

### パラメータ

| パラメータ | 既定値 | 説明 |
|---|---|---|
| `e2eProfile` | `none` | `none`／`P01`／`P02`／`P04`／`P05`／`P07` |
| `e2eDataId` | `-1` | DataID。-1はモジュールの既定値（CAN ID、SOME/IPは上記） |
| `e2eDataIdMode` | `both` | P01のDataIDの含め方 |
| `e2eDataIdList` | `""` | P02のDataIDList（16個のバイト値） |
| `e2eOffset` | CAN `0`、SOME/IP `8` | E2Eヘッダの位置（保護対象の先頭からのバイト数）。P02は0固定 |
| `e2eMaxDeltaCounter` | `1` | `OKSOMELOST` とするカウンタの最大の飛び |
| `e2eSmWindowSize` ほか | `3`、INIT: OK≥1・ERROR≤1、VALID: OK≥1・ERROR≤1、INVALID: OK≥2・ERROR≤0 | E2E状態機械 |
| `e2eReceptionTimeout` | `0s` | CANの受信側のみ。SecOCを通過したPDUがこの時間ない場合に `NONEWDATA` |
| `secocEnabled` | `false` | SecOCを使う |
| `secocDataId` | `-1` | SecOCDataId（16bit） |
| `secocKey` | `000102…0e0f` | AES-128鍵（16進32桁）。送受信で同じ値を設定 |
| `secocFreshnessBits` / `secocFreshnessTxBits` / `secocMacTxBits` | `64` / `8` / `24` | 完全なFV長、送るFVのビット数、送るMACのビット数 |
| `secocAcceptanceWindow` | `0` | 受理するFVの最大の飛び。0は無制限（`secocFreshnessTxBits=0` のときは1以上が必須） |
| `faultCorruptAt` / `faultReplayAt` / `faultSkipAt` / `faultSkipCount` | `""` / `""` / `""` / `3` | 送信側のみ。故障注入（1から数える送信番号、CAN IDごと／エンドポイントごと） |

スカラー結果（受信側）: `receivedFrames`（CAN）／`someipReceived`（SOME/IP）、`deliveredFrames`／`protectionDelivered`、`e2eOK`・`e2eOKSOMELOST`・`e2eREPEATED`・`e2eWRONGSEQUENCE`・`e2eERROR`・`e2eNONEWDATA`、`secocOK`・`secocAUTHENTICATION_FAILED`・`secocFRESHNESS_FAILED`・`secocMALFORMED`、`e2eSmValidReceptions`・`e2eSmInvalidReceptions`、`patternErrors`。CANではCAN IDごとに `id_<ID>_` 付きでも記録し、`id_<ID>_e2eSmFinalState`（0 NODATA、1 INIT、2 VALID、3 INVALID）もあります。送信側: `protectedFrames`／`protectedMessages`、`faultCorrupted`、`faultReplayed`。

## 検証（`tests/test_protection.py`）

1. **自己試験（119項目、OMNeT++内）**: CRC 6種の "123456789" チェック値と連結計算、E2E P01（4モード）・P02・P04・P05・P07の既知解（autosar-e2eの試験に収録されたAUTOSAR例と同じ値。オフセット8のSOME/IP形式を含む）、全ビットの1bit誤り検出、各チェック結果とカウンタの折り返し、状態機械の遷移、RFC 4493のAES-CMACテストベクタ4件、SecOCのバイト配置、リプレイ・改ざん・鍵違い・FVの折り返しと欠落・同期外れ・受理ウィンドウ・ビット詰め・FVの枯渇、FVを送らない構成での欠落後の再同期・ウィンドウ超過・リプレイ、ヘッダ位置の桁あふれの拒否。
2. **参照実装との照合**: C++で保護した乱数PDU（E2E 260件、SecOC 60件）を、C++やOpenSSLとは別の実装で検証します。E2Eは **autosar-e2e 1.0.0**（MIT）のcheckとprotectでバイト一致、MACは **pycryptodome 3.23.0** のCMACで一致を確認します。どちらも試験専用で、ハッシュ固定で `.local/venv-protection-test` に入れます。
3. **CAN/CAN-FD 3構成**: 全8シンクで10フレームを受信・配送し、E2E OK・SecOC OK、パターン誤り0。AVTP構成は両ゲートウェイのpcapからCANペイロード40件を取り出し、参照実装でE2E（CRC・カウンタの連続性）とSecOC（FV・MAC）を検証します。
4. **CANの故障注入**（ID 256の受信シンク。期待値はテスト内に手計算で記載）:

   | 構成 | 配送 | E2E | SecOC | 状態機械 |
   |---|---:|---|---|---|
   | `E2eSecOcFaults` | 24/30 | OK 23、OKSOMELOST 1、WRONGSEQUENCE 2、NONEWDATA 4 | OK 26、AUTH_FAILED 4（誤り3＋再送1） | INVALID 3回（NONEWDATA2回の後）→VALIDに復帰 |
   | `E2eOnlyFaults` | 24/30 | OK 23、ERROR 3、REPEATED 1、OKSOMELOST 1、WRONGSEQUENCE 2 | – | 連続誤りでINVALID 3回→VALIDに復帰 |
   | `SecOcWrongKey` | 0/10 | – | AUTH_FAILED 10 | NODATAのまま |

   SecOCがあると誤りや再送のPDUは破棄され、E2Eからは「データが来ない（NONEWDATA）」「カウンタの飛び」に見えます。SecOCなしでは、E2EがERRORとREPEATEDを直接検出します。故障のないストリームはすべて正常なことも確認します。
5. **SOME/IP**: `SomeIpE2eSecOc`（TCP・UDP）と `SomeIpE2eP07Mcast` で各48件を配送。pcapから全通知を取り出し（TCPはストリームを再構成）、参照実装でE2E（Request ID以降＋ペイロード、オフセット8）、カウンタ0からの連続、FV 1からの連続、MAC、イベントデータを検証します。SOME/IP-SDには付加部分がないことも確認します。故障注入では配送45件（E2E OK 44、OKSOMELOST 1、WRONGSEQUENCE 1、SecOC AUTH_FAILED 2）。pcap上で、10番目のCRCとMACが不一致であること、20番目が19番目とバイト一致すること、30番目のカウンタが4つ進むことを確認します。鍵違いではNode3の配送0件、Node2は48件です。

実装を故意に誤らせる変異試験（P05のCRCのバイト順、MACの下位ビット切り詰め、DataIdのバイト順、P01の最終XOR、P07のCRC範囲）は、すべて自己試験と参照照合の両方で検出されました。

## 未対応事項・前提

- **仕様との照合の確度**: バイト配置は、E2EがAUTOSARの例と同じ値を出すautosar-e2e、CMACがRFC 4493で確認済みです。一方、次はAUTOSAR SWS/PRS本文と照合していません（**要確認**）。
  - SecOCのFV復元手順とDataToAuthenticatorの構成（SWS SecOCの記述に基づく実装。FVの管理方法（FvM）はOEM固有です）。
  - E2Eを内側・SecOCを外側とする重ね順、およびSOME/IP-SDをE2E対象外とする扱い（一般的な整理に従っています）。
  - SOME/IPでのAuthentic I-PDUの取り方（Message ID＋Request ID以降。Lengthを除外）は本リポジトリの設計です。実際のSecOCとSOME/IPの組合せは構成に依存します。
- **E2E状態機械は単一ウィンドウ**（R4.2相当）: R4.4以降の状態別ウィンドウ長、状態遷移時のウィンドウ初期化は実装していません。P01/P02の旧チェック結果（INITIAL・SYNC等）ではなく、共通の結果（R4.2以降の対応付け）を使います。初回受信は、カウンタの初期値からの差で判定します（途中から購読すると最初はWRONGSEQUENCE）。
- **未対応のプロファイル**: P06、P11、P22、P44、P4m、P7m、P8など。E2E変換器（E2EXf）の構成項目、P01のCRC/カウンタ位置の個別指定（ヘッダは`e2eOffset`からの標準配置のみ）。
- **SecOCの未対応機能**: Secured I-PDUヘッダ、メッセージリンク、FV同期メッセージ、検証の再試行（SecOCFreshnessCounterSyncAttempts等）、鍵管理（鍵はiniで静的に共有）、MAC計算の処理時間（0として扱う）。
- **NONEWDATAはCANの受信側のみ**（`e2eReceptionTimeout`）。SOME/IPのエンドポイントは受信時だけ判定します。
- **故障注入は送信側で保護の後に行います**（伝送路での誤り・攻撃者による再送に相当する効果）。再送は「その回の送信を前回のPDUで置き換える」動作で、カウンタとFVは進めません。
- **CAN**: 保護するのはデータフレームだけです（リモートフレームは対象外）。ペイロード長とDLCは変えず、E2EヘッダとSecOCの付加部分はペイロード内に確保します。
