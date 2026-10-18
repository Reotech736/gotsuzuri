# 碁つづり — Gotsuzuri

実盤の囲碁対局をスマホから棋譜にするAndroidアプリ。現在は**背面カメラのプレビューと静止画保存を検証する最小アプリ**です。盤面認識・動画記録・SGF・KataGoは未実装です。

- applicationId / namespace: `io.github.reotech736.gotsuzuri`（所有者Reotech736の回答に基づき決定）
- GitHub: [Reotech736/gotsuzuri](https://github.com/Reotech736/gotsuzuri)（Public、main）
- 最低Android: 10（API 29）。MediaStoreによる保存でストレージ権限は不要です。
- 要求する権限: カメラのみ。インターネット権限なし。

## 全体のステップと現在地（2026-10-19）

**現在地はステップ1完了です。** 撮影・保存の土台が実機で動きました。盤面認識や棋譜生成の検証はこれからです。以下は実装を小さく進めるための順序で、日程や精度を保証するものではありません。

| ステップ | 到達点 | 状態 |
| --- | --- | --- |
| 1. 環境構築・撮影の土台 | Windowsでdebugビルドし、POCOでプレビュー・JPEG保存・表示・PC取得ができる | **完了・今回の終了地点** |
| 2. 撮影の追加確認 | 権限拒否と再許可、画面回転、ホーム復帰、連続撮影を確認し、問題があれば修正する | 次回の最初に確認 |
| 3. 盤面座標の指定 | 静止画像で碁盤の最外周交点4隅と向きを手動指定し、19×19交点を重ねる | 未着手 |
| 4. 静止画の石認識 | 各交点を空・黒・白・遮蔽／不明に分類し、実用的な撮影角度・高さを調べる | 未着手 |
| 5. 動画から一手を追跡 | 撮影済み映像を繰り返し検証できる入口を作り、開始局面・手番を指定して安定した着手を追う | 未着手 |
| 6. 対局履歴・SGF | 合法手・捕獲・パスを扱い、確定した手順をSGFに保存する。不明な手順は推測で埋めない | 未着手 |
| 7. 確認・修正 | 不確かな区間の映像確認・手順修正を行い、巻き戻しや分岐を段階的に追加する | 未着手 |
| 8. 通しの実用検証 | 実対局で精度・発熱・電池・映像保存容量を確認し、運用と公開の準備を整える | 未着手 |

次回はステップ2を先に終え、その後ステップ3の「静止画像への手動四隅指定＋交点表示」に範囲を絞ります。画像座標と論理碁盤座標は分離します。斜めから石が隠れる問題は射影変換だけでは解決できないため、ステップ4で実写検証します。

KataGo・形勢判断・撮影位置変更への追従・iOS対応は後続の検討です。上表は全MVPを一度に実装する計画ではありません。今日はステップ1の成果と現在地をGitへ保存して終了し、端末のUSB接続は不要です。

## Windowsセットアップ

Windows上に直接導入します。WSL・Docker・AWSは不要です。元の引き継ぎ資料は変更せず、ローカルに保管しています。

1. [Android Studio公式配布・導入手順](https://developer.android.com/studio/install)から安定版を導入します。2026-10-18の対象はRabbit 1 / 2026.2.1.8。GoogleのSDK規約を本人が確認・同意してください。
2. 初回起動で既存設定のインポートは不要。SDKの配置先は既定の `%LOCALAPPDATA%\Android\Sdk`。実機のみならEmulator・システムイメージは不要です。
3. Welcome画面の More Actions → SDK Manager（プロジェクトを開いた後は Tools → SDK Manager）で以下を導入します。
   - SDK Platforms → Android 16 / API 36
   - SDK Tools → Android SDK Platform-Tools
   - SDK Tools → Show Package Details → Android SDK Build-Tools 35.0.0
   - SDK Tools → Android SDK Command-line Tools（このPCでは従来CLI 19.0も併設）
4. Openからこのフォルダを開きます。New Projectで上書きしないでください。
5. **Gradle用にはJDK 21を選びます。** Rabbit 1付属のJDK 25ではGradle 8.13を実行できません。[Microsoft公式配布](https://learn.microsoft.com/en-us/java/openjdk/download)の `microsoft-jdk-21.0.12.1-windows-x64.zip` と対応するSHA-256を取得・照合し、このPCではGit管理外の `.tools\jdk21` に展開済みです。再セットアップでもZIPを同じ場所に展開するか、別途JDK 21を導入してJAVA_HOMEを設定してください。
6. Settings → Build, Execution, Deployment → Build Tools → Gradle の Gradle JDK は `.tools\jdk21\jdk-21.0.12.1+1`（このPC）を指定し、Gradleの取得元はWrapperにします。Studio自体は付属JDKで起動します。自動のAGP更新提案はこの検証時点では適用不要です。

この作業フォルダには `.gradle/config.properties` と `.idea/gradle.xml` をローカル設定として用意し、`GRADLE_LOCAL_JAVA_HOME` にJDK 21を指定済みです。いずれもGit管理外です。別PCでは上の手順でJDKを選んでください。

PowerShellでビルドする場合:

```powershell
Set-Location -LiteralPath (Join-Path $env:USERPROFILE 'git-repositories\gotsuzuri')
.\scripts\build.ps1
```

スクリプトはプロセス内のJAVA_HOMEに `.tools` のJDK 21（なければ既存のJAVA_HOME）、ANDROID_HOMEに標準SDK場所を設定します。独自SDK配置なら事前にANDROID_HOMEを設定してください。`local.properties` をStudioが作成してもGitには含みません。初回ビルドはGradleと依存関係をダウンロードするためネット接続が必要です。

このPCではWindowsの短縮名を含むTEMP経由のJava NIOローカル通信で `Unable to establish loopback connection` が発生しました。スクリプトは `.tools\tmp` を作成し、引用付きの `-Djdk.net.unixdomain.tmpdir=<絶対パス>` をJAVA_TOOL_OPTIONSへ追加して対処します。システム全体の環境変数・ファイアウォールは変更しません。Studio内でも同じエラーが出た場合、IDEのTerminalから上記スクリプトを使えます。

成果物: `app\build\outputs\apk\debug\app-debug.apk`。
Lintレポート: `app\build\reports\lint-results-debug.html`。

2026-10-19の最終debug APK: 30,078,163 bytes、SHA-256 `32d0f2bb3c95783bb7ad2183441dcfe5e5ea6bb68eadf9537cbf92608042550e`。再ビルド時にはハッシュが変わる場合があります。

## 固定した構成

| 対象 | バージョン | 状態・理由 |
| --- | --- | --- |
| 開発PC | GMKtec NucBox_K12、搭載RAM 64GiB | CIMで確認。OSから見えるメモリは55.8GiB |
| Windows | Windows 11 / build 26200、x64 | Windows側PowerShellで作業 |
| PowerShell | 7.6.7 | 実行環境で確認 |
| Git | 2.55.0.windows.5 | 実行で確認 |
| Android Studio | Rabbit 1 / 2026.2.1.8 | 導入完了。build 262.9437.185.2621.16467767 |
| Studio付属JDK | 25.0.3 | 起動確認済み。Gradle 8.13の実行には使用しない |
| ビルド用JDK | Microsoft OpenJDK 21.0.12.1+1 LTS | 公式ZIPのSHA-256照合済み、Git管理外に展開 |
| SDK Command-line Tools | 19.0 / 23.0 | 公式配布XMLとSHA-1照合済み。SDK導入はJDK 21 + 19.0で実施。23.0の新CLIは初回に通信エラー |
| SDK Platform / compileSdk / targetSdk | 36 | AGPの対応API範囲内 |
| SDK Build-Tools | 35.0.0 | AGP 8.13の既定 |
| SDK Platform-Tools | 37.0.1-15733141 | 導入・起動確認済み |
| scrcpy付属ADB | 37.0.0-14910828 | 初期調査で確認。今後はSDK側ADBを明示する |
| Android Gradle Plugin | 8.13.2 | API 36、Kotlin 2.3に対応 |
| Gradle Wrapper | 8.13 | 配布ZIPのSHA-256固定。Wrapper JARも公式ハッシュと一致 |
| Kotlin / Compose compiler plugin | 2.3.10 | 同じ版に統一。KGPの対応範囲にAGP 8.13.2、Gradle 8.13が含まれる |
| Compose BOM | 2025.08.01 | Google Mavenの公式POMで存在を確認。SDK 36向けの安定版に固定 |
| Activity Compose | 1.10.1 | 固定 |
| Lifecycle Runtime Compose | 2.9.3 | 固定 |
| Core KTX | 1.17.0 | SDK 36向け |
| CameraX | 1.5.3 | camera2 / lifecycle / viewを統一した安定版 |
| JVM bytecode | 17 | 実行用JDKと区別 |

すべての最新依存を採用する方針ではありません。API 36で検証する構成を固定し、更新は別途ビルド・実機確認します。

互換性の根拠:

- [StudioとAGPの対応表](https://developer.android.com/studio/releases)
- [AGP 8.13のGradle・JDK・SDK要件](https://developer.android.com/build/releases/agp-8-13-0-release-notes)
- [Kotlin Gradle Pluginの対応表](https://kotlinlang.org/docs/gradle-configure-project.html)
- [GradleのJava実行バージョン対応表](https://docs.gradle.org/current/userguide/compatibility.html#java_runtime)
- [Compose CompilerはKotlinと同じ版を使う](https://developer.android.com/develop/ui/compose/setup-compose-dependencies-and-compiler)
- [Compose BOM 2025.08.01公式POM](https://dl.google.com/dl/android/maven2/androidx/compose/compose-bom/2025.08.01/compose-bom-2025.08.01.pom)
- [CameraX 1.5.3リリース情報](https://developer.android.com/jetpack/androidx/releases/camera#1.5.3)

## POCOで実行

### USBで接続

1. 設定 → デバイス情報のOSバージョンを連続タップし、開発者向けオプションを有効にします。HyperOSの項目名はバージョンで異なる場合があります。
2. 追加設定 → 開発者向けオプション → USBデバッグをON。
3. データ通信対応USBケーブルで接続。端末を解除し、PCのRSA鍵確認を本人が許可します。
4. Android Studioで接続端末と `app` を選びRun。初回のカメラ許可は「アプリの使用中のみ」を選択。

ADBで確認・インストールする場合:

```powershell
$adb = Join-Path $env:LOCALAPPDATA 'Android\Sdk\platform-tools\adb.exe'
& $adb devices -l
& $adb install -r '.\app\build\outputs\apk\debug\app-debug.apk'
& $adb shell am start -n 'io.github.reotech736.gotsuzuri/.MainActivity'
```

端末が複数あるときは各ADBコマンドに `-s <対象シリアル>` を付けます。シリアルはREADMEやコミットに残しません。

- `unauthorized`: 端末を解除しRSA確認を許可。必要ならUSBを差し直す。
- 一覧が空: ケーブル・USBポート・USBデバッグ・デバイスマネージャーの順に確認。[公式の実機接続手順](https://developer.android.com/studio/run/device)、[OEM USBドライバ案内](https://developer.android.com/studio/run/oem-usb)を参照し、非公式ドライバ配布サイトから取得しないでください。
- HyperOSがインストールを拒否する場合: 端末に表示された理由を確認し、必要な場合だけ開発者向けオプションの「USB経由でインストール」を本人が操作します。アカウントの入力内容は共有不要です。
- PATH上のscrcpy付属ADBと混在させず、上記SDK側の絶対パスを使用します。

ADB経由が `INSTALL_FAILED_USER_RESTRICTED` で拒否される場合、端末で本人がAPKを確認してインストールする方法も使えます。このPCでは以下のコピーまで実施済みです。

```powershell
& $adb push '.\app\build\outputs\apk\debug\app-debug.apk' '/sdcard/Download/Gotsuzuri-debug.apk'
```

端末のファイル管理 → ダウンロード → `Gotsuzuri-debug.apk` を開き、確認画面を本人が操作します。提供元の許可を求められた場合は画面の内容を確認してください。インストール後は「碁つづり」を開きます。

### Wi-Fiで接続（USB不要）

Android 11以降のワイヤレスデバッグを使います。POCO X8 ProのAndroid 16で、USBをつながずにペアリング・ADB接続・アプリのインストール済み確認まで実施済みです。接続方式の追加確認であり、ロードマップの現在地はステップ1完了のままです。

1. PCと端末を相互通信できる同じLANへ接続します。
2. 端末の開発者向けオプション → ワイヤレスデバッグをONにします。
3. Android StudioのDevice Manager上部にあるWi-Fiアイコン → 対象端末のPairからペアリング画面を開けます。QR方式で進まない場合は「Pair using pairing code」を使います。
4. 端末の「ペア設定コードによるデバイスのペア設定」を開きます。表示中のペアリング用IP・ポートと6桁コードを使います。ワイヤレスデバッグの親画面にある接続用ポートとは別です。

Studioが端末のペア設定待ちから進まない場合は、SDK側ADBでもペアリングできます。

```powershell
$adb = Join-Path $env:LOCALAPPDATA 'Android\Sdk\platform-tools\adb.exe'
& $adb pair '<端末IP>:<ペアリング用ポート>'
# プロンプトで端末に現在表示されている一時コードを入力
& $adb connect '<端末IP>:<接続用ポート>'
& $adb -s '<端末IP>:<接続用ポート>' get-state
```

`device` が返れば接続できています。以降は同じ `-s` の指定でインストール・起動・ログ取得を行えます。Studioの上部の端末選択欄でもPOCOを選んでください。

- ON/OFFやペア設定画面の開き直しでポート・コードが変わるため、古いスクリーンショットの値を再利用しないでください。実際のIP・一時コード・コードを含むスクリーンショットはGitへ保存しません。
- `adb mdns services` で現在のサービスを調べられます。`_adb-tls-pairing._tcp` はペア設定用、`_adb-tls-connect._tcp` は通常の接続用です。
- このPCではscrcpy付属ADB 37.0.0のサーバーが稼働していました。接続端末がないことを確認し、SDK側ADBで `kill-server` → `start-server` を行って37.0.1へ統一後、現在のコード・ポートでペアリングと接続に成功しました。QR方式が停止した直接の原因は未特定です。
- ペアリングとWi-Fi接続は確認済みですが、Wi-Fi経由でのAPK再インストールは未確認です。HyperOSのインストール確認が必要な場合は本人が操作します。

[Android公式のワイヤレスADB手順](https://developer.android.com/tools/adb#connect-to-a-device-over-wi-fi)

## 写真の確認と再取得

「写真を保存」で `Pictures/Gotsuzuri/Gotsuzuri_<日時>_<乱数>.jpg` を作成します。「保存した写真を開く」、ギャラリー、またはファイル管理から開けます。端末を回転した場合の保存画像の向きも確認してください。プレビューは全体が見えるFIT_CENTERです。撮影画像とプレビューの画角が完全に同一になる保証はありません。

PCへ取得する場合（個人の撮影画像はGit管理外）:

```powershell
& $adb pull '/sdcard/Pictures/Gotsuzuri' '.\captures'
```

写真は共有ストレージのためアンインストール後も残ります。不要な写真はギャラリー等で削除してください。アプリ再起動・回転後の撮影履歴一覧はこの段階にはなく、保存済み写真はギャラリーで再取得できます。

## 検証記録（2026-10-18開始）

ビルド成功と実機動作を分けて記録します。

| 確認項目 | 結果 |
| --- | --- |
| 引き継ぎ資料・既存ファイル確認 | 完了。元アイデアメモ・AGENTS.md・既存コードなし |
| ローカルGit / リモート設定 | mainで初期化。既存Publicリポジトリを確認 |
| Studio / SDK導入 | 完了。Platform 36 revision 2、Build-Tools 35.0.0、Platform-Tools 37.0.1 |
| assembleDebug | 成功（2026-10-19）。最終アイコン修正を含むAPKを再ビルド済み |
| lintDebug | 成功、エラー0・警告11件。更新案内等（下記） |
| 実機ADB認識 | 認証済み、device状態を確認 |
| Wi-Fiデバッグ | 2026-10-19、SDK版ADB 37.0.1のコード方式でペアリング成功。USBなしでdevice状態・POCOの販売名・碁つづりのインストール済み状態を確認 |
| POCOの正式モデル・Android / HyperOS | POCO X8 Pro / 2511FPC34G、Android 16 API 36、OS3.0.307.0.WPJMIXM、arm64-v8a（ADBで確認） |
| APKインストール | 完了。ADB経由では2回とも INSTALL_FAILED_USER_RESTRICTED で拒否されたため、端末Downloadへコピーし、本人がファイル管理からインストール。versionName 0.1.0をADBでも確認 |
| 実機起動 | am startと実行プロセスで確認。起動後のアプリ限定エラーログにエラーなし |
| カメラ許可・プレビュー | 完了。本人が背面映像を確認、ADBでもCAMERA granted=trueを確認 |
| 保存・JPEG表示 | 完了。本人が保存成功表示と「保存した写真を開く」での表示を確認 |
| PCへの再取得 | 完了。Pictures/Gotsuzuriからcapturesへ1枚取得し、JPEGとして3072×4096、3,490,199 bytesで読み取り確認 |
| 権限拒否→案内→設定で許可→復帰 | 未確認 |
| 回転・ホーム復帰・連続撮影 | 未確認 |

2026-10-19: ユーザーの管理者確認・SDK規約同意・USBデバッグ／RSA鍵許可後に導入・ビルド完了。Gradle配布のSHA-256は公式64文字の値を再取得して固定・検証済みです。本人がプレビュー・撮影成功・保存画像の表示を確認し、今回の到達目標（debugビルド／実機起動／プレビュー／静止画保存）を達成しました。撮影画像はGit管理外のcapturesに取得済みで、公開しません。

Lintの残件はGradle／依存ライブラリの更新通知、Android 12以降のdataExtractionRules追加提案、Uri生成へのKTX利用提案です。現在の版を固定する方針を維持しています。`allowBackup=false` ですが、OEM間の端末移行まで一律に制御する専用ルールは未追加です。共有ストレージの写真はこのバックアップ設定の対象外です。

ソースのXML読み取り・PowerShellスクリプトの構文読み取り、秘密情報／成果物のgitignore除外、Wrapper JARの公式チェックサム一致も確認済みです。実機動作はビルド結果とは別に上表へ記録します。今日はここまでとし、未確認項目は次回のステップ2へ引き継ぎます。

実機チェックでは、権限を拒否してもクラッシュしないこと、設定で許可後に復帰できること、背面映像が見えること、連続保存・縦横それぞれのJPEGを開けること、ホームから戻って撮影できることを確認します。画質・長時間稼働・発熱・碁盤認識は後続の検証です。

## Git管理

SDK・JDK・依存キャッシュ・APK・写真・local.properties・署名鍵を除外します。元の `go-recorder-codex-handoff.md` は個人の開発環境・計画を含むため、ローカルに保管して公開対象から除外します。現在の開発手順・検証結果・次回の開始点はこのREADMEを参照してください。

リモートの公開範囲は所有者指定でPublic。コミット／push前には `git diff --cached` と `git status` で対象を確認してください。GitHubトークンや署名情報は記録しません。
