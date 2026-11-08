param([Parameter(Mandatory=$true)][string]$TemplateDirectory,[Parameter(Mandatory=$true)][string]$OutputDirectory)
$ErrorActionPreference='Stop'
[IO.Directory]::CreateDirectory($OutputDirectory) | Out-Null
$ga3Meta=Join-Path $OutputDirectory 'repo/v32_ga3_20261104_gitdata/meta'
$ga3Assets=Join-Path $OutputDirectory 'assets'
[IO.Directory]::CreateDirectory($ga3Meta) | Out-Null
[IO.Directory]::CreateDirectory($ga3Assets) | Out-Null
Copy-Item -LiteralPath (Join-Path $TemplateDirectory 'upload_release_data.ps1') -Destination $ga3Meta
$ga3Part=[byte[]](0,1,2,3,5,8,13,21)
$ga3Digest=[BitConverter]::ToString(([Security.Cryptography.SHA256]::Create()).ComputeHash($ga3Part)).Replace('-','').ToLowerInvariant()
[IO.File]::WriteAllBytes((Join-Path $ga3Assets 'ga3_full_001.part'),$ga3Part)
$ga3ArchiveHash=('a'*64)
$ga3Manifest=@{release_repository='MarkT1028/CKKS_AIE';release_tag='ga3-full-20261104-f9d28c8e22ae';archive_sha256=$ga3ArchiveHash;archive_bytes=8;parts=@(@{path='release_data/ga3_full_001.part';bytes=8;sha256=$ga3Digest})}
[IO.File]::WriteAllText((Join-Path $ga3Meta 'RELEASE_TRANSFER_MANIFEST.json'),($ga3Manifest | ConvertTo-Json -Depth 8),[Text.UTF8Encoding]::new($false))
[IO.File]::WriteAllText((Join-Path $ga3Meta 'RELEASE_NOTES.md'),$ga3ArchiveHash)
$global:ga3MockRelease=$null
$global:ga3MockAssets=@()
$global:ga3MockCalls=[Collections.Generic.List[string]]::new()
$global:ga3MockPublished=0
$global:ga3MockUploads=0
function global:git {
 $global:LASTEXITCODE=0
 if ($args -contains 'rev-parse') {return ('b'*40)}
 if ($args -contains 'ls-remote') {return (('b'*40)+"`trefs/heads/main")}
 throw 'Unexpected git mock command'
}
function global:gh {
 $global:LASTEXITCODE=0
 $global:ga3MockCalls.Add(($args -join ' '))
 if (($args -join ' ') -match 'clobber|delete') {throw 'Destructive command is forbidden'}
 if ($args[0] -eq 'api') {
  if ($args[1] -like '*/assets?*') {return (ConvertTo-Json -InputObject @($global:ga3MockAssets) -Depth 8)}
  if ($args[1] -like '*/releases?*') {
   if ($null -eq $global:ga3MockRelease) {return '[]'}
   return (ConvertTo-Json -InputObject @($global:ga3MockRelease) -Depth 8)
  }
 }
 if ($args[0] -eq 'release' -and $args[1] -eq 'create') {
  if (!($args -contains '--draft') -or !($args -contains '--target')) {throw 'Draft and exact target are required'}
  $global:ga3MockRelease=[pscustomobject]@{id=123;tag_name=$ga3Manifest.release_tag;body=$ga3ArchiveHash;draft=$true}
  return 'mock draft created'
 }
 if ($args[0] -eq 'release' -and $args[1] -eq 'upload') {
  $global:ga3MockUploads++
  $global:ga3MockAssets=@([pscustomobject]@{name='ga3_full_001.part';size=8;state='uploaded';digest="sha256:$ga3Digest"})
  return 'mock asset uploaded'
 }
 if ($args[0] -eq 'release' -and $args[1] -eq 'edit') {
  if (!($args -contains '--draft=false')) {throw 'Unexpected edit'}
  $global:ga3MockPublished++;$global:ga3MockRelease.draft=$false
  return 'mock publication'
 }
 throw ('Unexpected gh mock command '+($args -join ' '))
}
function Need-Ga3($Condition,[string]$Message) {if (!$Condition) {throw $Message}}
function Reject-Ga3([scriptblock]$Operation,[string]$Message) {
 $ga3Rejected=$false
 try {& $Operation | Out-Null} catch {$ga3Rejected=$true}
 Need-Ga3 $ga3Rejected $Message
}
$ga3Script=Join-Path $ga3Meta 'upload_release_data.ps1'
& $ga3Script | Out-Null
Need-Ga3 ($global:ga3MockCalls.Count -eq 0) 'Default plan contacted the API'
& $ga3Script -AssetDirectory $ga3Assets -Upload | Out-Null
Need-Ga3 ($global:ga3MockUploads -eq 1 -and $global:ga3MockRelease.draft -and $global:ga3MockPublished -eq 0) 'Upload did not retain draft'
& $ga3Script -AssetDirectory $ga3Assets -Upload | Out-Null
Need-Ga3 ($global:ga3MockUploads -eq 1) 'Repeated upload replaced an existing asset'
$global:ga3MockAssets[0].digest='sha256:wrong'
Reject-Ga3 {& $ga3Script -Publish} 'Corrupt remote asset should reject publication'
Need-Ga3 ($global:ga3MockPublished -eq 0) 'Published with mismatched digest'
$global:ga3MockAssets=@()
Reject-Ga3 {& $ga3Script -Publish} 'Missing asset should reject publication'
$global:ga3MockRelease.body='unrelated archive'
Reject-Ga3 {& $ga3Script -Upload -AssetDirectory $ga3Assets} 'Unrelated release accepted'
$global:ga3MockRelease.body=$ga3ArchiveHash
& $ga3Script -Upload -AssetDirectory $ga3Assets | Out-Null
& $ga3Script -Publish | Out-Null
Need-Ga3 ($global:ga3MockPublished -eq 1 -and !$global:ga3MockRelease.draft) 'Verified publication path did not finish'
Reject-Ga3 {& $ga3Script -Upload -Publish} 'Upload/publish must remain separate commands'
$ga3Result=@{status='PASS_GA3_RELEASE_UPLOADER_MOCK_ONLY';network_contacted=$false;actual_release_created=$false;checks=@('default_zero_API_calls','exact_commit_draft_creation','uploaded_digest_and_size_verified','repeat_skips_identical_asset','bad_digest_blocks_publish','missing_asset_blocks_publish','unrelated_release_rejected','publish_only_after_verified_assets','no_clobber_or_delete');mock_calls=@($global:ga3MockCalls)}
[IO.File]::WriteAllText((Join-Path $OutputDirectory 'result.json'),($ga3Result | ConvertTo-Json -Depth 8),[Text.UTF8Encoding]::new($false))
Write-Output $ga3Result.status
