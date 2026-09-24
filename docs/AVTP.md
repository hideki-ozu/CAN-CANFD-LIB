# IEEE 1722 (AVTP) CAN/CAN-FDトンネリング

CAN／CAN-FDフレームを **IEEE 1722 AVTP** でEthernetへ載せるゲートウェイです。従来の24B独自ヘッダ（`CanEthernetApp`）と同じゲートウェイ枠に差し替えて使います。実装は `upstream/SignalsAndGateways/src-inet4/signalsandgateways/inet4/avtp/` にあり、`patches/SignalsAndGateways.patch` に含まれます。

## 対応範囲

| 項目 | 内容 |
|---|---|
| EtherType | `0x22F0`（INETの `Protocol::tsn`） |
| AVTPDU形式 | NTSCF（subtype `0x82`、12Bヘッダ）、TSCF（subtype `0x05`、24Bヘッダ） |
| ACFメッセージ | ACF CAN（type `0x01`、16Bヘッダ、message_timestamp付き）、ACF CAN Brief（type `0x02`、8Bヘッダ） |
| CANフレーム | 11/29bit ID、Classical CAN 0～8B、CAN-FD 0～8/12/16/20/24/32/48/64B、BRS。4B境界への `pad` を自動設定 |
| 宛先 | ストリームごとのマルチキャストMAC（例 `91-E0-F0-00-FE-01`）。リスナはそのアドレスへ参加 |
| stream_id | 既定は「送信インタフェースMAC << 16 \| `streamUniqueId`」。`streamId`で直接指定も可 |
| 集約 | `maxAcfMessagesPerPdu` 件まで1つのAVTPDUへ格納。`aggregationTimeout` で最初のフレームの待ち時間を制限。`maxPduBytes`（既定1500B）を超える場合は分割 |
| TSCF提示時刻 | `avtp_timestamp` = 送信時刻 + `maxTransitTime`（gPTP ns下位32bit、`tv=1`）。リスナは提示時刻にCANへ送出。遅延到着は `latePresentationPolicy`（`forward`／`drop`） |
| 受信検証 | 受信バイト列を独立のデコーダ（`AvtpCodec`）で解析。subtype、version=0、sv=1、データ長、ACF長、pad、ID範囲、長さ、BRS/ESIとFDFの整合、FD RTR、Brief+mtvを検査 |
| フィルタ | `listenStreamId`（stream_id）、`acceptCanBusId`（can_bus_id） |
| 順序監視 | 8bit sequence_numの欠落（`sequenceLost`）と逆行・重複（`sequenceOutOfOrder`）をストリームごとに計数 |
| 未知ACF | ACF長に従って読み飛ばし、`unsupportedAcfMessages` に計数 |
| バイト精度 | 全チャンクにINET serializerを実装。`fcsMode="computed"` とPCAP記録が使えます |
| Ethernet接続 | INETのプロトコル登録（`Protocol::tsn`、Gptpと同じ方式）で送受信。StandardHostとTsnDeviceのどちらでも同じモジュールが動きます |
| gPTP時刻 | `clockModule` を指定するとノードのクロック（gPTPで同期されるTsnDeviceの`clock`）をgPTP時刻として使用。未指定ならシミュレーション時刻 |

ビット配置はIEEE Std 1722-2016のNTSCF/TSCF/ACF CAN定義に従い、[COVESA Open1722](https://github.com/COVESA/Open1722)（BSD-3-Clause、`include/avtp/acf/*.h`）のフィールド表と照合しました。Open1722はIEEE 1722-2025対応で、0x01/0x02もその型表に含まれます。

### ワイヤ形式

```text
NTSCF  | subtype=0x82 | sv(1) ver(3) r(1) ntscf_data_length(11) | sequence_num(8) | stream_id(64) |
TSCF   | subtype=0x05 | sv ver(3) mr rsv(2) tv | sequence_num | rsv(7) tu | stream_id(64) |
       | avtp_timestamp(32) | reserved(32) | stream_data_length(16) | reserved(16) |
ACF CAN| acf_msg_type(7)=1 acf_msg_length(9) | pad(2) mtv rtr eff brs fdf esi | rsv(3) can_bus_id(5) |
       | message_timestamp(64) | rsv(3) can_identifier(29) | payload | 0～3B pad |
Brief  | acf_msg_type=2 ... | （message_timestampなし）| rsv(3) can_identifier(29) | payload | pad |
```

`acf_msg_length` はヘッダを含む4B単位の長さ、`pad` は末尾パディングのバイト数です。受信側は `*_data_length` を超える部分（Ethernet最小長パディング）を無視します。

## 使い方

`examples/mixed` の各ゲートウェイの `app[0]` を差し替えます。

```ini
*.gateway*.app[0].typename = "signalsandgateways.inet4.avtp.AvtpCanGatewayApp"
*.gateway*.app[0].format = "tscf"               # または "ntscf"
*.gateway*.app[0].acfMessageType = "can"        # または "canBrief"
*.gatewayA.app[0].destAddress = "91-E0-F0-00-FE-01"     # 自ストリームの宛先
*.gatewayA.app[0].listenAddress = "91-E0-F0-00-FE-02"   # 受信する相手ストリーム
*.gatewayA.app[0].listenStreamId = "0x0200000000020001"
*.gatewayA.app[0].canBusId = 1
*.gatewayA.app[0].acceptCanBusId = 2
```

| 設定 | 内容 |
|---|---|
| `AvtpNtscf` | NTSCF + ACF CAN（mtv有効）。Classical 8BとFD 64B/BRSの双方向 |
| `AvtpTscf` | TSCF + ACF CAN。`maxTransitTime=500us` の提示時刻で送出 |
| `AvtpBriefAggregated` | NTSCF + ACF CAN Brief。1PDUに2フレームを集約 |
| `AvtpLoadedEthernet` | `AvtpTscf` に約75MbpsのEthernet背景負荷を追加 |
| `AvtpFdNoBrs` | `AvtpNtscf` でFD 64BのBRSを無効化 |
| `AvtpTscfOverload` | `AvtpTscf` で、宛先不明の背景トラフィック（約104%、スイッチが全ポートへ転送）によりスイッチ出力を輻輳させる（TSNなし） |
| `AvtpTsn` | `AvtpTscfOverload` と同じ負荷をINET TSN上で実行。AVTPに802.1Q（PCP 3／VID 2）、スイッチでクレジットベースシェーパ、静的マルチキャスト登録 |
| `AvtpTsnGptp` | `AvtpTsn` + gPTP（gatewayAがグランドマスタ、スイッチがブリッジ）。ゲートウェイの発振器は±50ppm |
| `AvtpTsnFreeRunning` | `AvtpTsn` の発振器を±50ppmにし、時刻同期なし（比較用） |

```bash
./scripts/run-mixed.sh AvtpTscf       # CLI
./scripts/run-gui.sh AvtpTscf         # Qtenv
python3 tests/test_avtp.py            # AVTPの検証のみ（make test-avtp）
```

各実行で `results/mixed/<設定>/gatewayA.pcap` と `gatewayB.pcap`（ナノ秒精度の標準pcap、Ethernetリンク）を記録します。内容はテストでOpen1722により検証済みです。Wiresharkでの表示は未確認です。

### 主なパラメータ

| パラメータ | 既定値 | 説明 |
|---|---|---|
| `format` | `ntscf` | `ntscf` / `tscf` |
| `acfMessageType` | `can` | `can` / `canBrief` |
| `messageTimestampValid` | `true` | ACF CANの `mtv`。値はゲートウェイがCANフレームを受信した時刻（gPTP ns） |
| `destAddress` | `""` | 送信先MAC。空ならCAN→Ethernet方向を使わない（受信したCANフレームはエラー） |
| `streamId` / `streamUniqueId` | `""` / `1` | stream_id |
| `canBusId` | `0` | 送信時の `can_bus_id`（0～31） |
| `maxAcfMessagesPerPdu` / `aggregationTimeout` / `maxPduBytes` | `1` / `0s` / `1500` | 集約 |
| `maxTransitTime` | `2ms` | TSCF提示時刻のオフセット |
| `listenAddress` | `""` | 受信するストリームMAC。空なら受信しない |
| `listenStreamId` | `""` | 受け入れるstream_id。空なら全て |
| `acceptCanBusId` | `-1` | 受け入れる `can_bus_id`。-1は全て |
| `latePresentationPolicy` | `forward` | 提示時刻に間に合わないPDUの扱い |
| `processingDelay` | `5us` | 送信・受信それぞれの変換処理時間 |
| `clockModule` | `""` | gPTP時刻に使うクロック（例 `"^.clock"`）。空ならシミュレーション時刻 |

スカラー結果: `canToAvtp`、`avtpPdusSent`、`avtpToCan`、`avtpPdusReceived`、`sequenceLost`、`sequenceOutOfOrder`、`droppedMalformedPdus`、`droppedStreamId`、`droppedBusId`、`droppedInvalidMessages`、`droppedRtr`、`unsupportedAcfMessages`、`latePresentations`、`droppedLate`、`originTagMissing`、`ignoredOtherDestinations`（他ストリーム宛てのフレーム）。統計: `gatewayLatency`、`acfMessagesPerPdu`、`avtpPduLength`、`presentationSlack`（提示時刻までの余裕）、`presentationLateness`、`presentationError`（リスナの送出時刻 − トーカが意図した提示時刻）。

## INET TSNとの組合せ

INET 4.7のTSN機能は設定で使えます。例は `examples/mixed/omnetpp.ini` の `AvtpTsn*` 構成です。

- **ノード**: ゲートウェイを `CanTsnHost`（`TsnDevice`派生）、スイッチを `inet.node.tsn.TsnSwitch` に差し替えます（`*.gateway*.typename` 等）。ネットワークはノード型をiniで選べるようにしています。モジュール型のEthernetインタフェースでは `**.eth[*].bitrate` の指定が必要です。EthernetSocketIoを使う背景ホストには `ethernet.hasSocketSupport = true` が要ります。
- **ストリーム識別とタグ付け（802.1CB/802.1Q）**: `bridging.streamIdentifier.identifier.mapping` でAVTPパケット（名前 `AVTP-*`）をストリームに割り当て、`bridging.streamCoder.encoder.mapping` でPCP 3／VID 2（SRクラスA相当）のC-tagを付けます。リスナは `hasIncomingStreams` でタグを外します。
- **帯域制御（802.1Qav）**: スイッチの `hasEgressTrafficShaping` と4トラフィッククラス（802.1Q表8-5でPCP 3→クラス1）、クラス1に `Ieee8021qCreditBasedShaper`（idleSlope 5Mbps）。
- **マルチキャスト転送**: SRP/MSRPのリスナ登録に相当する静的エントリ（`macTable.forwardingTable`、VLAN 2）。各ストリームはリスナのポートにだけ転送されます。
- **時刻同期（802.1AS）**: `hasTimeSynchronization` でGptpとSettableClockを有効にし、ゲートウェイの `clockModule = "^.clock"`。スイッチでは、gPTPフレームがベストエフォートの後ろに並ばないよう、専用の最上位クラスに分類します（`ContentBasedClassifier`。INETの `gptpandtas` 例と同じ方法）。

結果（`results/avtp/report.json` の `tsn`）:

| 構成 | Ethernet最大通過時間 A→B | 提示時刻誤差 |
|---|---:|---:|
| `AvtpTscfOverload`（TSNなし） | 270.1us | 0（理想時刻） |
| `AvtpTsn` | 134.1us | 0（理想時刻） |
| `AvtpTsnGptp` | 121.5us | −105～+105ns |
| `AvtpTsnFreeRunning` | – | −9.21～+9.21us |

最大通過時間は「提示時刻オフセット500us − 処理5us − 最小余裕」から求めています。TSNありでは、送信中のベストエフォートフレーム1個（1400B、約115us）を待つ分が残ります。フレームプリエンプション（802.1Qbu、`hasFramePreemption`）は未検証です。

## 検証（`tests/test_avtp.py`）

1. **コーデック自己試験（33項目）**: 仕様表から手計算した5種類のゴールデンバイト列と、serializer出力の一致。全フラグビット（mtv/rtr/eff/brs/fdf/esi、mr/tv/tu）、29bit ID、padを含みます。INETデシリアライズの往復、複数ACF・未知ACF・Ethernetパディングの解析、不正PDU 17種の拒否、29bit IDの受理も確認します。
2. **ネットワーク9構成**（TSN系4構成を含む）: 各ゲートウェイ20フレーム送受信、各ECU 20フレーム受信、ペイロード全バイトを照合。破棄・欠落・順序異常・提示時刻超過の各カウンタが0であることも確認。
3. **ワイヤ検証**: 記録したpcapを、C++実装とは独立にPythonで書いたIEEE 1722パーサで全フィールド検査します（EtherType、802.1QタグのPCP/VID（TSN構成のみ付与、それ以外は無し）、マルチキャスト宛先、stream_id、連番、長さ、予約ビット0、pad、ID、フラグ、ペイロード、message_timestamp、TSCFの提示時刻範囲）。送信側と受信側のpcapがバイト一致することも確認します。さらに全PDUを **Open1722参照実装** でデコードし、`IsValid`判定と全フィールドの一致を確認します。
4. **異常系**: stream_id不一致で20件破棄、can_bus_id不一致で20件破棄、提示時刻超過（`maxTransitTime=1us`）の `drop` で全件破棄、`forward` で全件転送。
5. **時間特性**: TSCFはNTSCFより遅延が大きく（提示時刻分）、75Mbps負荷時もTSCFのCAN側遅延が無負荷時と1ns未満の差で一致（ネットワーク揺らぎを提示時刻が吸収）。BRS無効時はFD 64Bの遅延が増加。
6. **TSN**: TSNありの最大通過時間がTSNなしより小さく、ベストエフォート1フレーム+30us以内。理想時刻で提示時刻誤差0、gPTPで1us未満、同期なしで5us超。

serializerのビット位置を故意に入れ替える変異試験（BRS↔FDF、RTR位置、TU位置、timestampのバイト順）がすべて検出されることを確認済みです。

## 未対応事項・モデルの前提

- **既定構成は理想時刻・TSNなし**: `AvtpNtscf` などは StandardHost／EthernetSwitch 上で、gPTP時刻＝シミュレーション時刻、802.1Qタグなしのベストエフォートです。TSN・gPTPは `AvtpTsn*` 構成（上記）で使います。
- **SRP/MSRPプロトコル自体はない**: INET 4.7にSRPの実装がないため、ストリーム予約はスイッチの静的マルチキャストエントリとシェーパの静的設定で代替しています。帯域の受付制御（予約拒否）は行いません。
- **提示時刻の変換**: リスナは受信時点のクロックで提示時刻をシミュレーション時刻へ換算して送出を予約します。予約後にgPTPがクロックを補正した場合、その補正分は反映されません（同期間隔1msでは誤差の主要因ではありません）。
- **INET Gptpの制約**: スイッチでgPTPフレームがベストエフォートの後ろに長く並ぶと、INET 4.7のGptpがnull参照で異常終了しました。gPTPを専用の最上位クラスに分類すると回避できます（`AvtpTsnGptp`）。
- **ACF CAN / CAN Briefのv1形式（0x01/0x02）のみ**: IEEE 1722-2025のCAN V2（0x21/0x22）、CAN XL（0x11/0x12）、LIN・FlexRay等の他ACF型は送信せず、受信時は読み飛ばします。AAF（PCM）・CRF・IEC 61883-4（MPEG-2 TS）は [AV.md](AV.md) のAVストリームとして別モジュールで対応しています。CVF/RVF等の他のメディア形式、AVTP over UDP、IEEE 1722.1（AVDECC）、MAAPによるアドレス自動割当はありません（アドレスは静的設定）。
- **RTRは転送しない**: 送信側でリモートフレームを受けるとエラー、受信側ではRTRメッセージを `droppedRtr` として破棄します（既存ゲートウェイと同じ方針）。
- **ESI、mr、tuは常に0で送信**: FiCo4OMNeTにエラー状態表示がないためです。受信側は値を解析します。
- **エンドツーエンド遅延の計測用メタデータ**: ECUでの生成時刻を、ワイヤに載らないINETのリージョンタグで運びます。欠落した場合は `mtv` のmessage_timestamp、または受信時刻で代替し、`originTagMissing` に計数します。
- CAN側の時間計算は既存のFiCo近似モデル（[README](../README.md#モデルの範囲)）のままです。
