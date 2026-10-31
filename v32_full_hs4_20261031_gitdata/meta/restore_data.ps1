param([string]$OutputPath = '', [switch]$CheckOnly)
$ErrorActionPreference = 'Stop'
$transferRoot = Split-Path -Parent $PSScriptRoot
$manifest = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'TRANSFER_MANIFEST.json') -Raw | ConvertFrom-Json
$pinnedSha = '1942e4fab7b7d8737c45d7a9791ad0ca2a68e1aae44cf03472a62f8287a00a90'
if ($manifest.schema -ne 'full_hs4_git_transport_v1' -or $manifest.archive_sha256 -ne $pinnedSha -or $manifest.parts.Count -ne 61) { throw 'Wrong transfer manifest.' }
$seen = @{}; [long]$sum = 0
for ($i = 0; $i -lt $manifest.parts.Count; $i++) {
    $part = $manifest.parts[$i]
    $expectedName = 'batch_{0}/part_{1:D3}.part' -f ([int][math]::Floor($i / 16) + 1), $i
    if ($part.name -ne $expectedName -or $seen.ContainsKey($part.name)) { throw 'Missing, duplicate or reordered part.' }
    $seen[$part.name] = $true
    $file = Join-Path $transferRoot $part.name
    $item = Get-Item -LiteralPath $file
    if ($item.Length -ne $part.bytes -or ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint)) { throw "Wrong part: $file" }
    if ((Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant() -ne $part.sha256) { throw "Part SHA mismatch: $file" }
    $sum += $item.Length
    Write-Host ('CHECK_PART {0}/{1}' -f ($i + 1), $manifest.parts.Count)
}
if ($sum -ne $manifest.archive_bytes -or $sum -ne 3036730296) { throw 'Wrong total archive size.' }
if ($CheckOnly) { Write-Host 'PASS_ALL_61_PARTS_NO_OUTPUT_WRITTEN'; return }
if (-not $OutputPath) {
    $repo = Split-Path -Parent $transferRoot
    $OutputPath = Join-Path (Split-Path -Parent $repo) $manifest.archive_name
}
$OutputPath = [System.IO.Path]::GetFullPath($OutputPath)
if (Test-Path -LiteralPath $OutputPath) {
    if ((Get-FileHash -LiteralPath $OutputPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $pinnedSha) { throw 'Output exists with different contents; preserve it and choose a new -OutputPath.' }
    Write-Host "PASS_EXISTING_ORIGINAL_ARCHIVE=$OutputPath"; return
}
$partial = $OutputPath + '.partial'
$stream = [System.IO.File]::Open($partial, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write, [System.IO.FileShare]::None)
try {
    foreach ($part in $manifest.parts) {
        $partStream = [System.IO.File]::OpenRead((Join-Path $transferRoot $part.name))
        try { $partStream.CopyTo($stream, 1048576) } finally { $partStream.Dispose() }
        Write-Host ('JOIN_PART ' + $part.name)
    }
    $stream.Flush()
} finally { $stream.Dispose() }
if ((Get-FileHash -LiteralPath $partial -Algorithm SHA256).Hash.ToLowerInvariant() -ne $pinnedSha) { throw 'Joined archive SHA mismatch; partial file retained.' }
[System.IO.File]::Move($partial, $OutputPath)
Write-Host "PASS_RESTORED_ORIGINAL_ARCHIVE=$OutputPath"
Write-Host "SHA256=$pinnedSha"
