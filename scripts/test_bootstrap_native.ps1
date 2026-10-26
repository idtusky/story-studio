# Isolated native cold-start tests; no Pester, network or software installation.
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'bootstrap.ps1') -NoRun
$originalInstaller = ${function:Install-PrivatePython}
$temporary = Join-Path ([IO.Path]::GetTempPath()) ('story-studio-native-test-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $temporary | Out-Null
$passed = 0
function Assert-True($Condition, [string]$Message) {
    if (-not $Condition) { throw $Message }
}
try {
    $plan = Get-NativePlan 'draft,asr'
    Assert-True (-not $plan.ready -and -not $plan.manual_commands_required) 'Cold plan must request Agent configuration'
    Assert-True ($plan.configuration_plan -contains 'Python 3.11 (managed)') 'Cold plan must supply Python'
    $passed++

    function Get-UsablePython { return $null }
    function Install-PrivatePython { throw 'Check must not invoke installation' }
    $Action = 'check'
    $Features = 'draft,asr'
    $result = @(Invoke-StudioBootstrap)
    Assert-True ($result[-1] -eq 1) 'No-Python check must return incomplete status'
    $report = ($result[0..($result.Count-2)] -join "`n") | ConvertFrom-Json
    Assert-True (-not $report.ready -and $report.preliminary) 'No-Python check must produce preliminary JSON'
    $passed++

    $fakePython = Join-Path $temporary 'fake-python.cmd'
    Set-Content -LiteralPath $fakePython -Encoding Ascii -Value "@echo off`r`necho {`"ready`":true}`r`nexit /b 0"
    $script:coldInstallCalled = 0
    function Install-PrivatePython {
        $script:coldInstallCalled++
        return @{ Executable = $fakePython; Prefix = @() }
    }
    $Action = 'install'
    $result = @(Invoke-StudioBootstrap)
    Assert-True ($script:coldInstallCalled -eq 1 -and $result[-1] -eq 0) 'Cold install must provision Python and launch next stage'
    $passed++

    Add-Type -AssemblyName System.IO.Compression
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archivePath = Join-Path $temporary 'unsafe.zip'
    $archive = [IO.Compression.ZipFile]::Open($archivePath, [IO.Compression.ZipArchiveMode]::Create)
    $archive.CreateEntry('../escape') | Out-Null
    $archive.Dispose()
    $rejected = $false
    try { Expand-VerifiedZip $archivePath (Join-Path $temporary 'extracted') } catch { $rejected = $true }
    Assert-True ($rejected -and -not (Test-Path -LiteralPath (Join-Path $temporary 'escape'))) 'Native extraction must reject traversal'
    $passed++

    ${function:Install-PrivatePython} = $originalInstaller
    function Get-StudioData { return $temporary }
    function Invoke-WebRequest {
        param($Uri, $OutFile, [switch]$UseBasicParsing)
        if ($OutFile) { [IO.File]::WriteAllBytes($OutFile, [byte[]]@(1,2,3)); return }
        return @{ Content = [Text.Encoding]::UTF8.GetBytes(('0' * 64)) }
    }
    function Expand-VerifiedZip { throw 'Unverified download must never reach extraction' }
    $rejected = $false
    try { Install-PrivatePython | Out-Null } catch { $rejected = $_.Exception.Message -match 'checksum mismatch' }
    Assert-True $rejected 'Native bootstrap must reject a tampered download before execution'
    $passed++

    Write-Output "$passed native bootstrap tests passed"
} finally {
    $resolved = [IO.Path]::GetFullPath($temporary)
    $base = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\') + '\'
    if (-not $resolved.StartsWith($base, [StringComparison]::OrdinalIgnoreCase)) { throw 'Unsafe test cleanup path' }
    Remove-Item -LiteralPath $resolved -Recurse -Force
}
