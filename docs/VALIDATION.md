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
