param()
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
$projectJdk = Join-Path (Get-Location) '.tools\jdk21\jdk-21.0.12.1+1'
if (Test-Path -LiteralPath "$projectJdk\bin\java.exe") {
    $env:JAVA_HOME = $projectJdk
}
if (-not $env:JAVA_HOME -or -not (Test-Path -LiteralPath "$env:JAVA_HOME\bin\java.exe")) {
    throw 'JDK 21がありません。READMEに従ってJDKを用意しJAVA_HOMEを設定してください。'
}
# Windowsの短縮名TEMPパスでJava NIOのAF_UNIX接続が失敗する環境への対策。
# 空白のある絶対パスをJava側にも1つの引数として渡す。
$javaTmp = Join-Path (Get-Location) '.tools\tmp'
New-Item -ItemType Directory -Path $javaTmp -Force | Out-Null
$socketOption = '"-Djdk.net.unixdomain.tmpdir=' + $javaTmp + '"'
$env:JAVA_TOOL_OPTIONS = (($env:JAVA_TOOL_OPTIONS, $socketOption) | Where-Object { $_ }) -join ' '
if (-not $env:ANDROID_HOME) {
    $env:ANDROID_HOME = Join-Path $env:LOCALAPPDATA 'Android\Sdk'
}
if (-not (Test-Path -LiteralPath "$env:ANDROID_HOME\platforms\android-36\android.jar")) {
    throw 'Android SDK Platform 36がありません。READMEのSDKセットアップを実施してください。'
}
& '.\gradlew.bat' --console=plain assembleDebug lintDebug
if ($LASTEXITCODE -ne 0) { throw "Gradle failed: $LASTEXITCODE" }
