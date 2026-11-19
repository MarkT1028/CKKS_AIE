param(
    [Parameter(Mandatory=$true)][string]$BindIPv4,
    [Parameter(Mandatory=$true)][string]$BoardIPv4,
    [ValidateRange(1,65535)][int]$Port = 8407,
    [string]$Ga0Root, [string]$Ga3Root, [string]$Ga6Root, [string]$Ga9Root,
    [string]$Ga3CacheRoot
)

$ErrorActionPreference = 'Stop'
$activeRoots = @{}
foreach ($layer in 'ga0','ga3','ga6','ga9','ga3cache') {
    $directory = Get-Variable -Name ($layer + 'Root') -ValueOnly
    if ($directory) {
        $location = Get-Item -LiteralPath $directory
        if (!$location.PSIsContainer) { throw "Expected a data directory for $layer" }
        $activeRoots[$layer] = $location.FullName
    }
}
if ($activeRoots.Count -eq 0) { throw 'Specify at least one GA dataset root' }

Add-Type -Path (Join-Path $PSScriptRoot 'Sender.cs')
$key = [V32GaSender]::NewKey()
Write-Host "V32_GA_INPUT_IP=$BindIPv4"
Write-Host "V32_GA_INPUT_PORT=$Port"
Write-Host "V32_GA_INPUT_KEY=$key"
[V32GaSender]::Run($BindIPv4, $BoardIPv4, $Port, $key, $activeRoots)
