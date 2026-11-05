param([int]$StartBatch=1)
$ErrorActionPreference='Stop'
$ga3Manifest=Get-Content -Raw -LiteralPath (Join-Path $PSScriptRoot 'TRANSFER_MANIFEST.json') | ConvertFrom-Json
if ($StartBatch -lt 1 -or $StartBatch -gt $ga3Manifest.batches) {throw 'Invalid StartBatch'}
for ($ga3Batch=$StartBatch; $ga3Batch -le $ga3Manifest.batches; $ga3Batch++) {
 & (Join-Path $PSScriptRoot 'push_batch.ps1') -Batch $ga3Batch
 if ($LASTEXITCODE -ne 0) {throw "Stopped at batch $ga3Batch. Review output before resuming."}
}
