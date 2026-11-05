param([string]$Destination='', [string]$SourceDirectory='', [switch]$DownloadOnly)
$ErrorActionPreference='Stop'
$ga3PartsRoot=[IO.Path]::GetFullPath((Split-Path $PSScriptRoot -Parent))
$ga3ManifestPath=Join-Path $PSScriptRoot 'RELEASE_TRANSFER_MANIFEST.json'
$ga3Manifest=Get-Content -Raw -LiteralPath $ga3ManifestPath | ConvertFrom-Json
function Get-Ga3Sha([string]$Path) {
 $ga3Stream=[IO.File]::OpenRead($Path);$ga3Hash=[Security.Cryptography.SHA256]::Create()
 try {return [BitConverter]::ToString($ga3Hash.ComputeHash($ga3Stream)).Replace('-','').ToLowerInvariant()} finally {$ga3Stream.Dispose();$ga3Hash.Dispose()}
}
$ga3Index=0
foreach($ga3Part in $ga3Manifest.parts) {
 if ($ga3Part.path -notmatch '^release_data/ga3_full_[0-9]{3}\.part$' -or [long]$ga3Part.bytes -gt 1GB) {throw 'Unexpected release asset layout'}
 $ga3Path=[IO.Path]::GetFullPath((Join-Path $ga3PartsRoot $ga3Part.path))
 if (!$ga3Path.StartsWith($ga3PartsRoot+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) {throw 'Unsafe download path'}
 [IO.Directory]::CreateDirectory((Split-Path $ga3Path -Parent)) | Out-Null
 $ga3Index++
 if (Test-Path -LiteralPath $ga3Path) {
  $ga3Size=(Get-Item -LiteralPath $ga3Path).Length
  if ($ga3Size -eq $ga3Part.bytes -and (Get-Ga3Sha $ga3Path) -eq $ga3Part.sha256) {Write-Output "ALREADY_VERIFIED $ga3Index/$($ga3Manifest.parts.Count)";continue}
  if ($ga3Size -ge $ga3Part.bytes) {throw "Existing corrupt asset retained: $ga3Path. Use a new download directory or remove only this file after review."}
 } else {$ga3Size=0}
 Write-Output "DOWNLOAD_ASSET $ga3Index/$($ga3Manifest.parts.Count) $($ga3Part.path)"
 if ($SourceDirectory) {
  $ga3Input=[IO.File]::OpenRead((Join-Path $SourceDirectory ([IO.Path]::GetFileName($ga3Part.path))))
  try {
   [void]$ga3Input.Seek($ga3Size,[IO.SeekOrigin]::Begin)
   $ga3Out=[IO.File]::Open($ga3Path,[IO.FileMode]::Append,[IO.FileAccess]::Write,[IO.FileShare]::None)
   try {$ga3Input.CopyTo($ga3Out,1048576)} finally {$ga3Out.Dispose()}
  } finally {$ga3Input.Dispose()}
 } else {
  $ga3Url="https://github.com/$($ga3Manifest.release_repository)/releases/download/$($ga3Manifest.release_tag)/$([IO.Path]::GetFileName($ga3Part.path))"
  & curl.exe --fail --location --retry 3 --continue-at - --output $ga3Path $ga3Url
  if ($LASTEXITCODE -ne 0) {throw 'Download failed. Release may still be a draft/unpublished. Partial asset retained for resume.'}
 }
 if ((Get-Item -LiteralPath $ga3Path).Length -ne $ga3Part.bytes -or (Get-Ga3Sha $ga3Path) -ne $ga3Part.sha256) {throw "Downloaded asset hash mismatch; retained for review: $ga3Path"}
}
Write-Output 'PASS_ALL_RELEASE_ASSETS'
if (!$DownloadOnly) {& (Join-Path $PSScriptRoot 'restore_data.ps1') -Destination $Destination -ManifestPath $ga3ManifestPath}
