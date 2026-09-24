# 検証結果（2026-09-23）

環境: Ubuntu 24.04 / WSL2 x86_64、OMNeT++6.4.0、INET4.7.0、g++13.3。

- 初回構築時（公開用スクリプト整理前）に、OMNeT++、INET、改修FiCo、選択CoREポート、ゲートウェイのreleaseビルドを確認。公開版の `build-all.sh` / `setup.sh` は既存OMNeT++を再構築しない。
- `python3 tests/test_canfd.py`: 15項目すべて成功。BRS、DLC不正値、FD RTR拒否、11/29bit仲裁、別送信元同一ID拒否、同一送信元の蓄積、旧CAN例を検証。
- `python3 tests/test_mixed.py`: 4構成すべて成功。ID、バイト列、生成時刻を両方向に保持。
- Qtenv: WSLg上で `Mixed #0` ウィンドウの生成とモデル読込みを確認。全実行と定量検証はCmdenvで実施。
- CoRE単体例: 1～4msに4フレーム送受信、5msのstopTime境界で生成停止。
- INET標準Ethernet例: 10秒、169356イベントで正常終了。
- 3リポジトリの差分チェック成功。保存パッチを基準コミットの未改修cloneに適用・逆適用チェック成功。

| 構成 | 各ゲートウェイ送信/受信 | 各ECU受信 | Ethernet負荷受信 |
|---|---:|---:|---:|
| Classic | 20/20 | 20 | 89 |
| Mixed | 20/20 | 20 | 89 |
| FdNoBrs | 20/20 | 20 | 89 |
| LoadedEthernet | 20/20 | 20 | 594 |

FD 64Bの平均エンドツーエンド遅延は、この設定でBRS有効1.112ms、無効2.726ms。CAN単体の受信遅延は有効0.335ms、無効1.142msです。固定オーバーヘッドとスタッフィング割合の近似モデルによる値であり、実機の測定値やISO適合性の証拠ではありません。

生の結果: `results/canfd/report.json`、`results/mixed/verification.json`、各フォルダの`.sca`/`.vec`。ビルド・実行ログは `logs/`。

再実行: `make test`。GUI: `make gui`。

## 公開版の導入検証

公開対象のスクリプト・パッチ・設定例・テストだけを新しい空のディレクトリへコピーし、既存OMNeT++ 6.4.0を指定して `BUILD_JOBS=6 scripts/setup.sh` を実行しました。既存のINETやモデルのビルド成果物はコピー・共有していません。

- 固定コミットの4リポジトリを新規取得し、パッチを適用。
- INETおよび3つのモデルライブラリをソースからreleaseビルド。
- CAN単体15項目、混在4構成がすべて成功。
- OMNeT++本体はダウンロード・再構築していません。
- 使用したOMNeT++の `Makefile.inc` と `configure.user` のSHA256は導入前後で一致しました。

この検証は同じLinuxマシン上の独立したソース／ビルドディレクトリで実施したもので、別OS・別マシンでの検証ではありません。

## IEEE 1722 AVTP（2026-09-23）

`python3 tests/test_avtp.py` がすべて成功しました（結果: `results/avtp/report.json`）。内容の詳細は [AVTP.md](AVTP.md) を参照してください。

- コーデック自己試験: 33項目成功、失敗0。
- ワイヤ検証: 9構成すべてで、各ゲートウェイのpcapに記録された全AVTPDUを独立のPythonパーサで検査しました。Open1722（commit `e0a9fca`）の参照デコーダでも全PDUが `IsValid` と判定され、全フィールドが一致しました。送信側と受信側のpcapはバイト単位で一致しました。
- 異常系: stream_id不一致20/20件破棄、can_bus_id不一致20/20件破棄、提示時刻超過の `drop` で20/20件破棄、`forward` で20/20件転送。
- 変異試験: serializerのBRS↔FDF入替え、RTR・TUのビット位置誤り、timestampのバイト順誤りを、すべて自己試験で検出しました。

| 構成 | 各ゲートウェイPDU | ACF/PDU | ECU B平均遅延 ID256（8B） | ID512（FD 64B） | 提示時刻の余裕 最小/最大 |
|---|---:|---:|---:|---:|---:|
| AvtpNtscf | 20 | 1 | 0.779ms | 1.112ms | – |
| AvtpTscf | 20 | 1 | 0.953ms | 1.397ms | 474.1/483.1us |
| AvtpBriefAggregated | 10 | 2 | 0.811ms | 1.144ms | – |
| AvtpLoadedEthernet | 20 | 1 | 0.953ms | 1.397ms | 367.4/483.1us |
| AvtpFdNoBrs | 20 | 1 | 1.586ms | 2.726ms | – |

いずれの構成でも、各ゲートウェイ20フレーム送受信、各ECU20フレーム受信、破棄・欠落・順序異常0件でした。背景Ethernet負荷はLoadedEthernetで594フレーム、それ以外で89フレームを受信しています。TSCFでは約75Mbpsの負荷によって提示時刻の余裕が約107us減りますが、CAN側の遅延は無負荷時と一致しました。NTSCFのID512遅延1.112msは、独自ヘッダの `Mixed` 構成と同じ値です。

### INET TSNとの組合せ

| 構成 | 各ECU受信 | 提示時刻超過 | Ethernet最大通過時間 A→B | 提示時刻誤差 最小/最大 |
|---|---:|---:|---:|---:|
| AvtpTscfOverload（TSNなし） | 20 | 0 | 270.1us | 0 / 0 |
| AvtpTsn（PCP 3 + CBS） | 20 | 0 | 134.1us | 0 / 0 |
| AvtpTsnGptp（+gPTP、±50ppm） | 20 | 0 | 121.5us | −105ns / +105ns |
| AvtpTsnFreeRunning（±50ppm、同期なし） | 20 | 0 | – | −9.21us / +9.21us |

TSN構成のpcapでは、全AVTPフレームに802.1Qタグ（PCP 3、VID 2、内側EtherType 0x22F0）が付き、Open1722でも全PDUが有効と判定されました。

既存の試験（CAN単体15項目、混在4構成）も、AVTP追加後に再実行してすべて成功しました。値は上記の近似モデルによるもので、実機測定ではありません。

## SOA4CoRE SOME/IP・SOME/IP-SD（2026-09-23）

`python3 tests/test_someip.py` がすべて成功しました（結果: `results/someip/report.json`）。内容の詳細は [SOMEIP.md](SOMEIP.md) を参照してください。

- コーデック自己試験: 21項目成功、失敗0。
- 配送: 3構成とも、公開50件に対して各サブスクライバが48件受信しました（最初の2件は購読成立前）。SOME/IPの不正0件、セッション欠番0件、SDの不正0件でした。
- ワイヤ検証: 各構成でSD 32メッセージとイベント全件を独立のPythonパーサで検査し、Scapy 2.6.1のSOME/IP実装とも全フィールドが一致しました。TCPはストリームを再構成して48メッセージを確認しました。
- TSN: TsnDevice上で、通知にPCP 5 / VID 10が付き、SDにはタグが付かないことを確認しました。
- 異常系: Eventgroup不一致ではAckなしで受信0、未知サービスではFind 4回で購読なし、インスタンス不一致では購読なし。
- 複数インスタンス（2026-09-25追加）: 同一ホストでインスタンス1と2を別々に購読し、各48件を正しい公開側からだけ受信しました。
- 第2オプションラン（2026-09-25追加）: 第2ランのエンドポイントで購読が成立し、範囲外参照を1件検出しました。
- 変異試験: シリアライザの4種の誤りをすべて自己試験で検出しました（カウンタの位置の誤りは正解バイト列の追加後に検出）。

| 構成 | Node2 | 平均遅延 | Node3 | 平均遅延 |
|---|---|---:|---|---:|
| SomeIpTcpUdp | TCP 48件 | 23.5us | UDP 48件 | 34.2us |
| SomeIpUdpOnly | UDP 48件 | 21.6us | UDP 48件 | 33.3us |
| SomeIpUdpMcast | マルチキャスト 48件 | 21.6us | マルチキャスト 48件 | 21.6us |

既存の試験（CAN単体15項目、混在4構成、AVTP）も、SOA4CoRE追加後に再実行してすべて成功しました。

## AUTOSAR E2E / SecOC（2026-09-24）

`python3 tests/test_protection.py` がすべて成功しました（結果: `results/protection/report.json`）。詳細は [PROTECTION.md](PROTECTION.md) を参照してください。

- 自己試験119項目（CRC、E2E P01/P02/P04/P05/P07の既知解、状態機械、RFC 4493 CMAC、SecOC）。
- 設定の拒否（2026-09-25追加）: 負の `e2eOffset`・`e2eMaxDeltaCounter`、受理ウィンドウなしの `secocFreshnessTxBits=0` は、明示的なエラーで停止します。修正前の実装では、負のオフセットが巨大な符号なし値に変換され（CANでは範囲外書き込み）、FV 0ビットは1件の欠落で以後すべて認証失敗になっていました。
- 参照実装照合: E2E 260件（autosar-e2e 1.0.0）、SecOC 60件（pycryptodome 3.23.0）がバイト一致。
- CAN 6構成（独自トンネル、IEEE 1722 NTSCF/TSCF、故障注入3構成）、SOME/IP 4構成（TCP、UDP、UDPマルチキャスト、故障注入、鍵違い）。AVTPとSOME/IPはpcapの全PDUを参照実装で検証。
- 変異試験5件（P05のCRCバイト順、MACの切り詰め位置、DataIdのバイト順、P01の最終XOR、P07のCRC範囲）をすべて検出。
- 既存の `make test`（CAN単体15項目、混在4構成、AVTP、SOME/IP）も変更後に全て成功。
- パッチを固定コミットの未改修cloneに適用し、別ディレクトリでFiCo4OMNeT・CoRE4INET・AUTOSAR保護ライブラリ・SignalsAndGateways・SOA4CoREをビルドして `tests/test_protection.py` が成功（INETは既存のビルドを共有、試験用venvは新規作成）。

環境: OpenSSL 3.0.13（Ubuntu 24.04のlibssl3。開発ヘッダは `scripts/fetch-openssl-dev.sh` で `.local/` に展開）。

## IEEE 1722 AVストリーム（2026-09-24）

`python3 tests/test_av.py` がすべて成功しました（結果: `results/av/report.json`）。詳細は [AV.md](AV.md) を参照してください。

- 自己試験50項目（AAF・CRF・IEC 61883-4の手計算ゴールデンバイト列、不正PDU 26種、MPEG-2 TS／PCR／CRC）。
- 5構成（理想、TSNなし過負荷、TSN、TSN+gPTP、同期なし）。同期時は全listenerが生成速度の1ppm以内で再生、提示時刻誤差は±1us未満。
- ワイヤ検証: AAF 15120件・CRF 96件をOpen1722で、61883-4 7558PDU（TSパケット約2万件）を独立パーサで検証。受信側pcapと送信側のバイト一致。
- 変異試験5件をすべて検出（うちPCR拡張ビットは試験強化後に検出）。
- パッチを固定コミットの未改修SignalsAndGatewaysに適用し、作業ツリーと一致することを確認。
