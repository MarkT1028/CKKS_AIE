"""Read-only admission: CmaFree is a snapshot, not an allocation guarantee."""
MIN_AVAILABLE_KIB=1800*1024
MIN_CMA_TOTAL_KIB=160*1024
CMA_FREE_NOTICE_KIB=160*1024

def assess(meminfo,page_size=4096):
 fields={}
 for line in meminfo.splitlines():
  parts=line.split()
  if parts and parts[0] in ('MemAvailable:','CmaTotal:','CmaFree:'):
   if len(parts)!=3 or parts[2]!='kB':raise ValueError('invalid memory field '+parts[0])
   fields[parts[0]]=int(parts[1])
 if set(fields)!={'MemAvailable:','CmaTotal:','CmaFree:'}:raise ValueError('missing memory admission fields')
 if fields['MemAvailable:']<MIN_AVAILABLE_KIB:raise ValueError('insufficient MemAvailable:')
 if fields['CmaTotal:']<MIN_CMA_TOTAL_KIB:raise ValueError('insufficient CmaTotal:')
 if not 0<=fields['CmaFree:']<=fields['CmaTotal:']:raise ValueError('invalid CmaFree:')
 if page_size<4096 or page_size&(page_size-1):raise ValueError('invalid page size')
 align=lambda n:(n+page_size-1)//page_size*page_size
 # Exactly2 banks x2 lanes; per lane:28MiB input,1.3125MiB output,448B parameters.
 bo_page_payload=4*(align(4096*14*16*4*8)+align(4096*14*3*8)+align(14*32))
 return dict(status='PASS_MEMORY_SNAPSHOT_ADMISSION_ACTUAL_XRT_BO_PENDING',MemAvailable_kib=fields['MemAvailable:'],CmaTotal_kib=fields['CmaTotal:'],CmaFree_kib=fields['CmaFree:'],CmaFree_below_old_threshold=fields['CmaFree:']<CMA_FREE_NOTICE_KIB,estimated_page_rounded_BO_bytes=bo_page_payload,estimate_excludes_runtime_driver_overhead=True,actual_BO_allocation='PENDING_XRT_SETUP',cache_or_CMA_reclaim_cause='NOT_DIAGNOSED_FROM_SNAPSHOT',cache_or_sysctl_mutated=False,scope='CmaFree is diagnostic only. Keep system available-memory and reserved-CMA-total guards. Existing real XRT BO constructors must succeed before any graph execution; allocation failure remains fatal and is retained.')
