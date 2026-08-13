param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^(?:\d{1,3}\.){3}\d{1,3}$')]
    [string]$LaptopLanAddress,

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^(?:\d{1,3}\.){3}\d{1,3}$')]
    [string]$LaptopTailscaleAddress,

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^(?:\d{1,3}\.){3}\d{1,3}$')]
    [string]$MachineBLanAddress,

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^(?:\d{1,3}\.){3}\d{1,3}$')]
    [string]$MachineBTailscaleAddress,

    [string]$LogPath = (Join-Path $env:TEMP 'arma-cti-wsl-firewall.log')
)

$ErrorActionPreference = 'Stop'
trap {
    @(
        'status=1'
        ($_ | Out-String)
    ) | Set-Content -LiteralPath $LogPath -Encoding UTF8
    exit 1
}
$windowsRuleName = 'ArmaCTI-WSL-SSH-22-Host'
$hyperVRuleName = 'ArmaCTI-WSL-SSH-22-HyperV'
$wslCreatorId = '{40E0AC32-46A5-438A-A0B2-2B479E8F2E90}'
$allowedSources = @($MachineBLanAddress, $MachineBTailscaleAddress)

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
$isAdministrator = $principal.IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator
)

if (-not $isAdministrator) {
    $arguments = @(
        '-NoProfile',
        '-ExecutionPolicy', 'Bypass',
        '-File', ('"{0}"' -f $PSCommandPath),
        '-LaptopLanAddress', $LaptopLanAddress,
        '-LaptopTailscaleAddress', $LaptopTailscaleAddress,
        '-MachineBLanAddress', $MachineBLanAddress,
        '-MachineBTailscaleAddress', $MachineBTailscaleAddress,
        '-LogPath', ('"{0}"' -f $LogPath)
    )
    Remove-Item -LiteralPath $LogPath -Force -ErrorAction SilentlyContinue
    $elevated = Start-Process `
        -FilePath 'powershell.exe' `
        -Verb RunAs `
        -ArgumentList $arguments `
        -Wait `
        -PassThru
    if (Test-Path -LiteralPath $LogPath) {
        Get-Content -LiteralPath $LogPath | Write-Host
    }
    else {
        Write-Host 'status=1'
        Write-Host 'The elevated firewall process produced no diagnostic log.'
    }
    exit $elevated.ExitCode
}

if (-not (Get-Command New-NetFirewallHyperVRule -ErrorAction SilentlyContinue)) {
    throw 'Hyper-V firewall cmdlets are unavailable; Windows 11 22H2 or newer is required.'
}

# Replace only this script's named rules. Re-running produces the same bounded
# policy and never changes the independent Windows OpenSSH rule on port 2222.
Get-NetFirewallRule -Name $windowsRuleName -ErrorAction SilentlyContinue |
    Remove-NetFirewallRule
New-NetFirewallRule `
    -Name $windowsRuleName `
    -DisplayName 'Arma CTI WSL SSH 22 from Machine B' `
    -Direction Inbound `
    -Action Allow `
    -Enabled True `
    -Profile Any `
    -Protocol TCP `
    -LocalAddress $LaptopLanAddress `
    -LocalPort 22 `
    -RemoteAddress $allowedSources | Out-Null

Get-NetFirewallHyperVRule -Name $hyperVRuleName -ErrorAction SilentlyContinue |
    Remove-NetFirewallHyperVRule
New-NetFirewallHyperVRule `
    -Name $hyperVRuleName `
    -DisplayName 'Arma CTI WSL SSH 22 from Machine B' `
    -Direction Inbound `
    -Action Allow `
    -VMCreatorId $wslCreatorId `
    -Protocol TCP `
    -LocalPorts 22 `
    -RemoteAddresses $allowedSources | Out-Null

# Mirrored networking does not always bind WSL services to the Windows LAN
# address. Prove a WSL-side target before binding only that LAN address; Windows
# OpenSSH remains independently bound to port 2222.
function Test-TcpPort {
    param([string]$Address)
    $client = [Net.Sockets.TcpClient]::new()
    try {
        $pending = $client.BeginConnect($Address, 22, $null, $null)
        if (-not $pending.AsyncWaitHandle.WaitOne(3000) -or -not $client.Connected) {
            return $false
        }
        $client.EndConnect($pending)
        return $true
    }
    catch {
        return $false
    }
    finally {
        $client.Dispose()
    }
}

$proxyCandidates = @('127.0.0.1', $LaptopTailscaleAddress)
$wslAddresses = & wsl.exe -e sh -lc 'hostname -I' 2>$null
foreach ($candidate in ($wslAddresses -split '\s+')) {
    if ($candidate -match '^(?:\d{1,3}\.){3}\d{1,3}$' -and
        $candidate -ne $LaptopLanAddress -and
        $candidate -notin $proxyCandidates) {
        $proxyCandidates += $candidate
    }
}
$proxyTarget = $proxyCandidates | Where-Object { Test-TcpPort -Address $_ } |
    Select-Object -First 1
if (-not $proxyTarget) {
    throw "WSL sshd is unreachable from Windows on port 22; tried $($proxyCandidates -join ', ')."
}

netsh interface portproxy delete v4tov4 `
    listenaddress=$LaptopLanAddress listenport=22 | Out-Null
netsh interface portproxy add v4tov4 `
    listenaddress=$LaptopLanAddress listenport=22 `
    connectaddress=$proxyTarget connectport=22 | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Could not bind the WSL LAN port proxy on ${LaptopLanAddress}:22."
}

Write-Host 'Configured WSL SSH port 22 for these Machine B sources:'
$allowedSources | ForEach-Object { Write-Host "  $_" }
Write-Host 'Windows OpenSSH port 2222 was not changed.'
@(
    'status=0'
    "lan_proxy=${LaptopLanAddress}:22->${proxyTarget}:22"
    "allowed_sources=$($allowedSources -join ',')"
    'windows_ssh_2222=unchanged'
) | Set-Content -LiteralPath $LogPath -Encoding UTF8
