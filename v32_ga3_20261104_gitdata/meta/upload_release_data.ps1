param([string]$AssetDirectory='', [switch]$Upload, [switch]$Publish)
$ErrorActionPreference='Stop'
if ($Upload -and $Publish) {throw 'Upload the draft first; publish only after reviewing its completed assets.'}
$ga3Manifest=Get-Content -Raw -LiteralPath (Join-Path $PSScriptRoot 'RELEASE_TRANSFER_MANIFEST.json') | ConvertFrom-Json
$ga3Repo=$ga3Manifest.release_repository;$ga3Tag=$ga3Manifest.release_tag
function Get-Ga3Sha([string]$Path) {
 $ga3Stream=[IO.File]::OpenRead($Path);$ga3Hash=[Security.Cryptography.SHA256]::Create()
 try {return [BitConverter]::ToString($ga3Hash.ComputeHash($ga3Stream)).Replace('-','').ToLowerInvariant()} finally {$ga3Stream.Dispose();$ga3Hash.Dispose()}
}
function Invoke-Ga3Gh {
 $ga3Answer=& gh @args
 if ($LASTEXITCODE -ne 0) {throw 'GitHub CLI command failed; no asset is overwritten or deleted. Review output and retry.'}
 return $ga3Answer
}
function Get-Ga3Release {
 for($ga3Page=1; $ga3Page -le 100; $ga3Page++) {
  $ga3List=@(((Invoke-Ga3Gh api "repos/$ga3Repo/releases?per_page=100&page=$ga3Page") -join "`n") | ConvertFrom-Json)
  $ga3Found=@($ga3List | Where-Object {$_.tag_name -eq $ga3Tag})
  if ($ga3Found.Count -eq 1) {return $ga3Found[0]}
  if ($ga3Found.Count -gt 1) {throw 'Unexpected duplicate release tags'}
  if ($ga3List.Count -lt 100) {return $null}
 }
 throw 'Release pagination limit reached; no release created.'
}
function Test-Ga3Asset($Asset,$Part) {
 if (!$Asset -or $Asset.state -ne 'uploaded' -or [long]$Asset.size -ne [long]$Part.bytes -or $Asset.digest -ne "sha256:$($Part.sha256)") {throw "Release asset missing or not SHA256 verified: $($Part.path). Draft is retained; no replacement is attempted."}
}
if (!$Upload -and !$Publish) {
 Write-Output "PLAN_ONLY repository=$ga3Repo tag=$ga3Tag assets=$($ga3Manifest.parts.Count) bytes=$($ga3Manifest.archive_bytes)"
 Write-Output "ARCHIVE_SHA256=$($ga3Manifest.archive_sha256)"
 Write-Output 'No GitHub request, upload or publication performed. Use -Upload for a draft, then separately -Publish after review.'
 return
}
if (!(Get-Command gh -ErrorAction SilentlyContinue)) {throw 'GitHub CLI is not installed. Use the GitHub release web page with the supplied assets, or install the official GitHub CLI and run gh auth login. No installation performed.'}
if ($ga3Repo -ne 'MarkT1028/CKKS_AIE' -or $ga3Tag -notmatch '^ga3-full-20261104-[0-9a-f]{12}$') {throw 'Unexpected destination repository or tag'}
$ga3Release=Get-Ga3Release
if (!$ga3Release) {
 if ($Publish) {throw 'No prepared draft exists; upload and review first.'}
 $ga3RepoRoot=Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
 $ga3Head=& git -C $ga3RepoRoot rev-parse HEAD
 if ($LASTEXITCODE -ne 0 -or $ga3Head -notmatch '^[0-9a-f]{40}$') {throw 'Expected an existing Git checkout'}
 $ga3Remote=& git -C $ga3RepoRoot ls-remote origin refs/heads/main
 if ($LASTEXITCODE -ne 0 -or !$ga3Remote -or ($ga3Remote -split '\s+')[0] -ne $ga3Head) {throw 'Commit and push the code/metadata first; local HEAD must match origin/main.'}
 Invoke-Ga3Gh release create $ga3Tag --repo $ga3Repo --target $ga3Head --draft --prerelease --title 'Complete real g_a.3 comparison data' --notes-file (Join-Path $PSScriptRoot 'RELEASE_NOTES.md') | Out-Null
 $ga3Release=Get-Ga3Release
}
if (!$ga3Release -or !$ga3Release.body.Contains($ga3Manifest.archive_sha256)) {throw 'Existing release does not match this exact immutable dataset'}
foreach($ga3Part in $ga3Manifest.parts) {
 if ($ga3Part.path -notmatch '^release_data/ga3_full_[0-9]{3}\.part$' -or [long]$ga3Part.bytes -gt 1GB) {throw 'Unexpected asset layout'}
 $ga3Name=[IO.Path]::GetFileName($ga3Part.path)
 $ga3Assets=@(((Invoke-Ga3Gh api "repos/$ga3Repo/releases/$($ga3Release.id)/assets?per_page=100") -join "`n") | ConvertFrom-Json)
 $ga3Matches=@($ga3Assets | Where-Object {$_.name -eq $ga3Name})
 if ($ga3Matches.Count -gt 1) {throw 'Duplicate asset name; no upload attempted'}
 if ($ga3Matches.Count -eq 1) {Test-Ga3Asset $ga3Matches[0] $ga3Part;Write-Output "ALREADY_VERIFIED_RELEASE_ASSET=$ga3Name";continue}
 if (!$Upload -or !$ga3Release.draft) {throw 'Required asset missing. Only this matching draft can be uploaded.'}
 if (!$AssetDirectory) {throw 'Specify the local release_assets folder with -AssetDirectory'}
 $ga3File=Join-Path $AssetDirectory $ga3Name
 if ((Get-Item -LiteralPath $ga3File).Length -ne $ga3Part.bytes -or (Get-Ga3Sha $ga3File) -ne $ga3Part.sha256) {throw "Local asset missing or corrupt: $ga3Name"}
 Invoke-Ga3Gh release upload $ga3Tag $ga3File --repo $ga3Repo | Out-Null
 $ga3Assets=@(((Invoke-Ga3Gh api "repos/$ga3Repo/releases/$($ga3Release.id)/assets?per_page=100") -join "`n") | ConvertFrom-Json)
 $ga3Actual=@($ga3Assets | Where-Object {$_.name -eq $ga3Name});if($ga3Actual.Count -ne 1) {throw 'Uploaded asset metadata not found; retain draft and retry'}
 Test-Ga3Asset $ga3Actual[0] $ga3Part;Write-Output "VERIFIED_RELEASE_ASSET=$ga3Name"
}
if ($Publish) {
 if ($ga3Release.draft) {Invoke-Ga3Gh release edit $ga3Tag --repo $ga3Repo --draft=false | Out-Null}
 Write-Output "PUBLISHED_RELEASE=https://github.com/$ga3Repo/releases/tag/$ga3Tag"
} else {Write-Output "READY_TO_REVIEW_DRAFT=https://github.com/$ga3Repo/releases/tag/$ga3Tag";Write-Output 'All required assets match SHA256. Review the draft, then run this script separately with -Publish.'}
