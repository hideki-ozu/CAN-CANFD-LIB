# SOA4CoRE（SOME/IP・SOME/IP-SD）のINET4移植

[SOA4CoRE](https://github.com/CoRE-RG/SOA4CoRE)（commit `0c79bae`、LGPL-3.0）は、INET 3.x と旧CoRE4INET向けに書かれたサービス指向ミドルウェアです。本リポジトリでは、そのうち **SOME/IP と SOME/IP-SD の経路を OMNeT++ 6.4 / INET 4.7 に移植**しました。移植版は `upstream/SOA4CoRE/src-inet4/` にあり（`patches/SOA4CoRE.patch`）、元の `src/` は変更していません。

## 移植範囲

| 区分 | 内容 |
|---|---|
| 移植済み | サービスマネージャ（`Manager`、`SomeIpManager`）、SOME/IP-SD（`SomeIpSD`）、静的ディスカバリ、レジストリ、コネクタ、アプリケーション（`Publisher`、`Subscriber`）、エンドポイント（SOME/IP UDP・UDPマルチキャスト・TCP、素のUDP・UDPマルチキャスト・TCP）、ミドルウェアとホスト（`MiddlewareHost`＝StandardHost、`MiddlewareTsnHost`＝TsnDevice） |
| 未移植 | AVBエンドポイント（CoRE4INETのSRP/AVBフレームに依存）、`SyncPublisher`（CoRE4INETの時刻同期スケジューラ）、ゲートウェイ用アプリ・ホスト（旧SignalsAndGatewaysのゲートウェイ枠）、QoSネゴシエーション（`QoSManager`・`QoSNegotiationProtocol`・`QoSBroker`）、元の例のうち上記に依存するもの |

未移植部分は `src-inet4/` に含めていないため、ビルドにもNEDパスにも現れません。`hasQoSNP=true` や `registerStream=true` を指定した場合は、明示的なエラーで停止します。

## 元の実装からの主な変更

- **INET 4 API へ置き換え**: `UDPSocket`/`TCPSocket` を `UdpSocket`/`TcpSocket`（コールバック方式）へ、`IPv4Address` 等を `Ipv4Address` へ、制御情報 `UDPDataIndication` を `L3AddressInd` タグへ置き換えました。INET 3 の `UDPBasicApp` から派生していた SOME/IP-SD は、独立したモジュールに書き直しました。
- **トランスポートへの接続**: 実行時に生成されるエンドポイントは、ホストのアプリケーション層ディスパッチャ（`at`）に、入出力の番号をそろえたゲートで接続します（INET 4 はアプリを UDP/TCP に直結しないため）。
- **バイト精度のメッセージ**: SOME/IP ヘッダと SOME/IP-SD（エントリ・オプション）を INET の `FieldsChunk` として再定義し、シリアライザを実装しました（`messages/someip/SomeIp.msg`、`SomeIpSerializer.cc`）。`fcsMode="computed"` と pcap 記録が使えます。
- **仕様への準拠（AUTOSAR PRS_SOMEIP / PRS_SOMEIPSD）**:
  - SD のセッションIDを実装しました。マルチキャストと各ユニキャスト相手で別カウンタを持ち、1から始まり、0xFFFFの次は1に戻ります。Reboot フラグは最初の一巡まで1、Unicast フラグは常に1です。元の実装ではどちらも未設定でした。
  - SubscribeEventgroup と Ack に Eventgroup ID を載せます（`eventgroupId` パラメータ、既定1）。一致しない購読には Ack を返しません。
  - イベントは NOTIFICATION（0x02）として送ります。メッセージIDは「サービスID＋イベントID（`eventId`、最上位ビットが1、既定0x8001）」、クライアントIDは0x0000、セッションIDは1〜0xFFFFで巡回します。元の実装は REQUEST・セッション0でした。
  - SOA4CoRE 独自の QoS 属性（PCP/VLAN、最大ペイロード、最小間隔、デッドライン）は、AUTOSAR の Configuration Option（type 0x01、`<長さ>key=value` 形式）として送ります（`include*Config` パラメータ）。
- **受信側の検証**:
  - SD: サービス／メソッドID、バージョン、メッセージ種別、長さ、エントリ長、オプション長、オプション参照の範囲を検査し、不正なものは破棄して数えます。長さフィールドは受信した値のまま保持し、実際に読み取った構造の長さと一致しなければ破棄します。元の実装は参照範囲を検査していませんでした。
  - SD のエントリが参照する2つのオプションラン（`index1stOptions`/`num1stOptions` と `index2ndOptions`/`num2ndOptions`）を両方とも検査・処理します。個数0のランのインデックスは参照しません。
  - SOME/IP サブスクライバ: プロトコルバージョン、NOTIFICATION であること、イベントID、長さ、サービスIDを検査します。あわせてセッションIDの欠番を数えます。
- **インスタンスごとの購読**: サブスクライバのコネクタは（サービスID、QoS グループ、要求インスタンスID）の組ごとに作ります。同じホストで同じサービス・QoS の別インスタンスを要求するアプリは、それぞれ別の購読・エンドポイントを持ち、他のインスタンスの通知を受け取りません。特定インスタンスと任意インスタンス（0xFFFF）を同じホスト・QoS で同時に要求する構成は、エラーで停止します（元の実装の制限）。
- **TCP の再構成**: SOME/IP over TCP では、バイトストリームを長さフィールドに従って1メッセージずつ切り出します。
- **PCP/VLAN**: CoRE4INET の RT-IP フィルタの代わりに、INET 4 の `PcpReq`/`VlanReq` タグと 802.1Q カプセル化要求を付けます。`MiddlewareTsnHost`（`hasOutgoingStreams=true`）では、UDP の通知に 802.1Q タグが付きます。TCP のセグメントには付きません。SRP による帯域予約はありません。
- **遅延の統計**: INET 4 ではメッセージオブジェクトが引き継がれないため、発行時刻をペイロードの `CreationTimeTag` で運び、サブスクライバの `rxLatency` に記録します。

## 使い方

```bash
./scripts/run-someip.sh SomeIpTcpUdp      # CLI（5秒間）
./scripts/run-someip-gui.sh SomeIpTcpUdp  # Qtenv
python3 tests/test_someip.py              # SOME/IPの検証のみ（make test-someip）
```

例（`examples/someip`）は、元の `examples/someip/small_network` の移植です。Node1 がサービス1を SOME/IP UDP・UDPマルチキャスト・TCP で公開し、Node2 と Node3 が SOME/IP-SD で見つけて購読します。

| 設定 | Node2 | Node3 |
|---|---|---|
| `SomeIpTcpUdp` | SOME/IP TCP（インスタンス1） | SOME/IP UDP（任意インスタンス0xFFFF） |
| `SomeIpUdpOnly` | SOME/IP UDP | SOME/IP UDP |
| `SomeIpUdpMcast` | SOME/IP UDPマルチキャスト | SOME/IP UDPマルチキャスト |
| `SomeIpTsnPcp` | UDPマルチキャスト | UDP。全ノードが TsnDevice で、公開側は PCP 5 / VLAN 10 |
| `SomeIpTwoInstances` | UDP でインスタンス1（Node1）とインスタンス2（Node3）を別々に購読 | インスタンス2の公開側 |
| `SomeIpSecondOptionRun` | 試験用の SD 注入アプリ（`SomeIpSdInjector`） | サービス7を購読。注入された Offer（エンドポイントは第2オプションラン）だけで見つかる |

アドレスは 10.0.0.1〜3（`Ipv4NetworkConfigurator` で固定）、SD は 224.0.2.254:30490（SOA4CoRE の既定値）です。各ノードの pcap を `results/someip/<設定>/Node*.pcap` に記録します。

## 検証（`tests/test_someip.py`）

1. **コーデック自己試験（21項目）**: 仕様表から手計算した正解バイト列と、シリアライザ出力の一致を確認します（Find、3種類のオプション付き Offer、SubscribeEventgroup、カウンタ付き Nack、通知）。INET でのデシリアライズと往復変換、未知オプションの読み飛ばし、受信した長さフィールドの保持、不正入力7種の拒否も確認します。
2. **配送（3構成）**: 公開50件、各サブスクライバ48件受信（最初の2件は購読成立前）。SOME/IP の不正0件、セッション欠番0件、SD の不正0件、オプション参照範囲外0件、遅延は1ms未満。
3. **ワイヤ検証**: pcap を、C++実装とは別に書いた Python パーサで検査します。
   - SD の全フィールド: 予約ビット0、Reboot/Unicast フラグ、相手ごとに1から連続するセッションID、エントリとオプションの対応、Offer のエンドポイント3種、購読側のエンドポイント、マルチキャスト Ack。
   - 順序: Offer → Subscribe → Ack → 最初のイベント。
   - イベント: 48件、連番のセッションID、長さ、ペイロード。TCP はストリームを再構成して検査します。
   - SD メッセージとUDPイベントは **Scapy 2.6.1 の SOME/IP 実装**（試験専用、ハッシュ固定）でもデコードし、全フィールドが一致することを確認します。
4. **異常系**: Eventgroup 不一致では Ack なしで受信0、未知サービスでは Find 4回（初回＋繰り返し3回）で購読なし、インスタンス不一致では購読なし。
5. **TSN**: `SomeIpTsnPcp` で、通知に PCP 5 / VID 10 の 802.1Q タグが付き、SD にはタグが付かないことを確認します。
6. **複数インスタンス**: `SomeIpTwoInstances` で、Node2 の2つのサブスクライバがそれぞれ48件受信し、pcap 上でポート3172にはNode1、ポート3174にはNode3からの通知だけが届くことを確認します。
7. **第2オプションラン**: `SomeIpSecondOptionRun` で、エンドポイントが第2ランにある Offer を受けて購読し、第2ランが範囲外のエントリを不正参照として1件数えることを確認します。

6・7と自己試験の長さ保持の検査は、修正前の実装（QoS だけでコネクタを照合、第1ランのみ処理、復号時に長さを再計算）に戻すと失敗することを確認済みです。

シリアライザのビット位置を故意に誤らせる変異試験（オプション数のニブル入替え、クライアント／セッションIDの入替え、カウンタの位置、TTLの切り詰め）は、すべて自己試験で検出されます。カウンタの位置の誤りは当初見逃していたため、正解バイト列を追加しました。

## 未対応事項・前提

- 上記の未移植部分（AVB/SRP、QoS ネゴシエーション、ゲートウェイ、同期パブリッシャ）。
- SOME/IP-TP（分割）、リクエスト／レスポンス（メソッド呼び出し）、フィールド（getter/setter）、StopOffer・StopSubscribe・Nack の送信、TTL 失効処理、IPv6 エンドポイントオプション、Load Balancing による選択は扱いません。TTL 0 のエントリは受信時に無視します。
- 購読は Offer を受け取るたびに更新します（元の実装と同じ）。
- マルチキャストのエンドポイントオプションを Offer にも載せます（元の実装と同じ。AUTOSAR では通常 Ack に載せます）。
- 静的ディスカバリ（`StaticServiceDiscovery`）は移植していますが、それを使う QoS マネージャは未移植です。
