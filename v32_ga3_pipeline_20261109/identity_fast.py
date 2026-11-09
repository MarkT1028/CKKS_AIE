"""Fresh identities with pinned directory FDs; no cached file stat results."""
import os,stat
from pathlib import Path,PurePosixPath

def fields(s):return [s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns]

def snapshot(root,names):
    """names maps result key -> safe relative POSIX path, all checked afresh.

    One no-follow stat per regular file replaces repeated pathlib resolution.
    Parent directories are opened component by component without symlinks and
    their namespace bindings are checked again before returning the snapshot.
    """
    root=Path(root)
    flags=os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC
    descriptors={};bindings={};out={}
    try:
        descriptors[()]=os.open(root,flags)
        for key,name in names.items():
            rel=PurePosixPath(name)
            if rel.is_absolute() or not rel.parts or '..' in rel.parts or any(x in name for x in ('\\',':','\x00')):
                raise ValueError('unsafe manifest/cache path '+name)
            parts=rel.parts
            for i in range(1,len(parts)):
                parent=parts[:i]
                if parent not in descriptors:
                    fd=os.open(parts[i-1],flags,dir_fd=descriptors[parent[:-1]])
                    descriptors[parent]=fd;bindings[parent]=os.fstat(fd)
            s=os.stat(parts[-1],dir_fd=descriptors[parts[:-1]],follow_symlinks=False)
            if not stat.S_ISREG(s.st_mode):raise ValueError('missing/unsafe regular file '+name)
            out[key]=fields(s)
        for parts,old in bindings.items():
            now=os.stat(parts[-1],dir_fd=descriptors[parts[:-1]],follow_symlinks=False)
            if not stat.S_ISDIR(now.st_mode) or (old.st_dev,old.st_ino)!=(now.st_dev,now.st_ino):
                raise ValueError('source directory binding changed')
        pinned=os.fstat(descriptors[()]);named=os.stat(root,follow_symlinks=False)
        if not stat.S_ISDIR(named.st_mode) or (pinned.st_dev,pinned.st_ino)!=(named.st_dev,named.st_ino):
            raise ValueError('source root binding changed')
        return out
    finally:
        for fd in reversed(list(descriptors.values())):os.close(fd)

def data_snapshot(root):
    names={}
    for line in (Path(root)/'SHA256SUMS_DATA').read_text('ascii').splitlines():
        digest,name=line.split('  ',1)
        if len(digest)!=64 or any(x not in '0123456789abcdef' for x in digest) or name in names:
            raise ValueError('invalid/duplicate sealed manifest')
        names[name]=name
    if not names:raise ValueError('empty sealed manifest')
    return snapshot(root,names)
