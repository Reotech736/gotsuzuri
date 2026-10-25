param(
    [Parameter(Mandatory = $true)][string]$DataDirectory,
    [string]$PythonExecutable
)

$ErrorActionPreference = 'Stop'
$repoPath = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '../..')).Path
$dataPath = (Resolve-Path -LiteralPath $DataDirectory).Path
$capturesPath = [System.IO.Path]::GetFullPath((Join-Path $repoPath 'captures'))
if (-not $dataPath.StartsWith($capturesPath + [System.IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'データはこのリポジトリのcaptures配下を指定してください。'
}
$annotationsPath = Join-Path $dataPath 'annotations.json'
$annotations = Get-Content -Raw -LiteralPath $annotationsPath | ConvertFrom-Json
$readyPath = Join-Path $dataPath 'server-url.txt'
if (Test-Path -LiteralPath $readyPath) {
    $previousUrl = (Get-Content -Raw -LiteralPath $readyPath).Trim()
    if ($previousUrl -match '^http://127\.0\.0\.1:\d+/$') {
        try {
            $running = Invoke-RestMethod -Uri ($previousUrl + 'api/data') -TimeoutSec 2
            if ($running.data.datasetId -eq $annotations.datasetId -and $running.data.sourceSha256 -eq $annotations.sourceSha256) {
                Write-Output $previousUrl
                return
            }
        } catch { }
    }
}
if (-not $PythonExecutable) {
    $bundledPython = Join-Path $env:USERPROFILE '.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
    if (Test-Path -LiteralPath $bundledPython) { $PythonExecutable = $bundledPython }
    else { $PythonExecutable = (Get-Command python -ErrorAction Stop).Source }
}
& $PythonExecutable -c 'from PIL import Image' 2>$null
if ($LASTEXITCODE -ne 0) { throw 'Pillowを使えるPythonを-PythonExecutableで指定してください。requirements.txtを参照してください。' }
$scriptPath = Join-Path $PSScriptRoot 'server.py'
$serverArgs = @('"' + $scriptPath + '"', 'serve', '--data', '"' + $dataPath + '"', '--ready-file', '"' + $readyPath + '"')
$process = Start-Process -FilePath $PythonExecutable -ArgumentList $serverArgs -WorkingDirectory $repoPath -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $dataPath 'server-out.log') -RedirectStandardError (Join-Path $dataPath 'server-error.log') -PassThru
$process.Id | Set-Content -LiteralPath (Join-Path $dataPath 'server-pid.txt')
for ($attempt = 0; $attempt -lt 50; $attempt++) {
    if ($process.HasExited) { throw '起動できませんでした。データフォルダのserver-error.logを確認してください。' }
    if (Test-Path -LiteralPath $readyPath) {
        $url = (Get-Content -Raw -LiteralPath $readyPath).Trim()
        if ($url -match '^http://127\.0\.0\.1:\d+/$') {
            try {
                $running = Invoke-RestMethod -Uri ($url + 'api/data') -TimeoutSec 1
                if ($running.data.datasetId -eq $annotations.datasetId -and $running.data.sourceSha256 -eq $annotations.sourceSha256) {
                    Write-Output $url
                    return
                }
            } catch { }
        }
    }
    Start-Sleep -Milliseconds 100
}
throw '起動の確認がタイムアウトしました。server-error.logを確認してください。'
