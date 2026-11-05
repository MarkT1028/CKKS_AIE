param([string]$Destination='', [string]$ManifestPath='')
$ErrorActionPreference='Stop'
function Get-Ga3Sha([string]$Path) {
 $ga3Stream=[IO.File]::OpenRead($Path);$ga3Hash=[Security.Cryptography.SHA256]::Create()
 try {return [BitConverter]::ToString($ga3Hash.ComputeHash($ga3Stream)).Replace('-','').ToLowerInvariant()} finally {$ga3Stream.Dispose();$ga3Hash.Dispose()}
}
$ga3PartsRoot=[IO.Path]::GetFullPath((Split-Path $PSScriptRoot -Parent))
$ga3Repo=Split-Path $ga3PartsRoot -Parent
if (!$ManifestPath) {$ManifestPath=Join-Path $PSScriptRoot 'TRANSFER_MANIFEST.json'}
$ga3Manifest=Get-Content -Raw -LiteralPath $ManifestPath | ConvertFrom-Json
if (!$Destination) {$Destination=Join-Path (Split-Path $ga3Repo -Parent) $ga3Manifest.archive_name}
$Destination=[IO.Path]::GetFullPath($Destination)
if (Test-Path -LiteralPath $Destination) {
 if ((Get-Ga3Sha $Destination) -eq $ga3Manifest.archive_sha256) {Write-Output "PASS_RESTORED_ORIGINAL_ARCHIVE=$Destination"; exit 0}
 throw 'Destination already exists with a different hash; preserve it and choose a new Destination.'
}
$ga3Index=0
foreach($ga3Part in $ga3Manifest.parts) {
 $ga3Path=[IO.Path]::GetFullPath((Join-Path $ga3PartsRoot $ga3Part.path))
 if (!$ga3Path.StartsWith($ga3PartsRoot+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) {throw 'Unsafe part path'}
 if ((Get-Item -LiteralPath $ga3Path).Length -ne $ga3Part.bytes -or (Get-Ga3Sha $ga3Path) -ne $ga3Part.sha256) {throw "Part missing/corrupt: $ga3Path"}
 $ga3Index++;Write-Output "CHECK_PART $ga3Index/$($ga3Manifest.parts.Count)"
}
$ga3Out=[IO.File]::Open($Destination,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
try {foreach($ga3Part in $ga3Manifest.parts) {
 $ga3In=[IO.File]::OpenRead((Join-Path $ga3PartsRoot $ga3Part.path))
 try {$ga3In.CopyTo($ga3Out,1048576)} finally {$ga3In.Dispose()}
 Write-Output "JOIN_PART $($ga3Part.path)"
}} finally {$ga3Out.Dispose()}
if ((Get-Item -LiteralPath $Destination).Length -ne $ga3Manifest.archive_bytes -or (Get-Ga3Sha $Destination) -ne $ga3Manifest.archive_sha256) {throw 'Joined archive verification failed; retain the file for diagnosis.'}
Write-Output "PASS_RESTORED_ORIGINAL_ARCHIVE=$Destination"
Write-Output "SHA256=$($ga3Manifest.archive_sha256)"
