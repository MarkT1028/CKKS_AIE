param([Parameter(Mandatory=$true)][int]$Batch)
$ErrorActionPreference='Stop'
function Get-Ga3Sha([string]$Path) {
 $ga3Stream=[IO.File]::OpenRead($Path);$ga3Hash=[Security.Cryptography.SHA256]::Create()
 try {return [BitConverter]::ToString($ga3Hash.ComputeHash($ga3Stream)).Replace('-','').ToLowerInvariant()} finally {$ga3Stream.Dispose();$ga3Hash.Dispose()}
}
$ga3PartsRoot=Split-Path $PSScriptRoot -Parent
$ga3Repo=Split-Path $ga3PartsRoot -Parent
$ga3Name=Split-Path $ga3PartsRoot -Leaf
$ga3Manifest=Get-Content -Raw -LiteralPath (Join-Path $PSScriptRoot 'TRANSFER_MANIFEST.json') | ConvertFrom-Json
if ($Batch -lt 1 -or $Batch -gt $ga3Manifest.batches) {throw 'Invalid batch number'}
function Invoke-Ga3Git { & git -C $ga3Repo @args; if($LASTEXITCODE -ne 0) {throw "git failed: $args"} }
$ga3Branch=& git -C $ga3Repo branch --show-current
if ($LASTEXITCODE -ne 0 -or $ga3Branch -ne 'main') {throw 'Expected existing main branch; no checkout performed.'}
$ga3Staged=& git -C $ga3Repo diff --cached --name-only
if ($LASTEXITCODE -ne 0 -or $ga3Staged) {throw 'Other staged changes exist. Commit/review them separately before pushing data batches.'}
$ga3Parts=@($ga3Manifest.parts | Where-Object {$_.path -like "batch_$Batch/*"})
if (!$ga3Parts.Count) {throw 'Batch is empty'}
foreach($ga3Part in $ga3Parts) {
 $ga3Path=Join-Path $ga3PartsRoot $ga3Part.path
 if ((Get-Item -LiteralPath $ga3Path).Length -ne $ga3Part.bytes -or (Get-Ga3Sha $ga3Path) -ne $ga3Part.sha256) {throw "Part missing/corrupt: $ga3Path"}
}
$ga3Paths=@($ga3Parts | ForEach-Object {"$ga3Name/$($_.path)"})
# Batches are ignored by default to keep an accidental `git add .` small.
# Force-add only this manifest-verified batch after the staged-change guard.
Invoke-Ga3Git add -f -- @ga3Paths
& git -C $ga3Repo diff --cached --quiet
if ($LASTEXITCODE -eq 1) {Invoke-Ga3Git commit -m "Add real g_a.3 data batch $Batch/$($ga3Manifest.batches)"}
elseif ($LASTEXITCODE -ne 0) {throw 'Cannot inspect staged batch'}
Invoke-Ga3Git push origin main
Write-Output "PASS_PUSHED_BATCH=$Batch/$($ga3Manifest.batches)"
