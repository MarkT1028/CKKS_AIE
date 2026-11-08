#pragma once
#include "bitpack.hpp"
#include "sealed_sha256.hpp"
#include <fstream>
#include <set>

namespace { namespace windowio {
inline std::vector<uint8_t> input_header(const Record& r){
    require(r.kind==3||r.kind==4,"packed input kind");
    std::vector<uint8_t> h={'C','K','K','S','M','A','C','1'};
    auto put=[&](uint64_t v,unsigned n){for(unsigned b=0;b<n;++b)h.push_back(uint8_t(v>>(8*b)));};
    for(unsigned v:std::array<unsigned,10>{1,r.kind,r.shape.n,r.shape.l,r.shape.k,2,1,64,0,0})put(v,4);
    put(r.words,8);put(0,8);for(const auto&p:r.shape.parameters){put(p.q,8);put(p.mu_lo,8);put(p.mu_hi,8);}return h;
}
inline size_t packed_bytes(const Record& r){
    size_t n=0;for(const auto&p:r.shape.parameters)n+=compactbits::bytes(size_t(r.shape.n)*2,compactbits::width(p.q));return n*r.shape.k;
}
inline void exact_read(int fd,uint8_t* dst,size_t n,size_t offset,ReadStats* stats=nullptr){
    size_t done=0;while(done<n){auto got=::pread(fd,dst+done,std::min<size_t>(4*1024*1024,n-done),off_t(offset+done));
        if(got<0&&errno==EINTR)continue;require(got>0,"short packed input read");done+=size_t(got);if(stats)++stats->pread_calls;}
}
inline void identity_same(int fd,const struct stat& old){struct stat s{};
    require(::fstat(fd,&s)==0&&s.st_dev==old.st_dev&&s.st_ino==old.st_ino&&s.st_size==old.st_size&&s.st_mtim.tv_sec==old.st_mtim.tv_sec&&s.st_mtim.tv_nsec==old.st_mtim.tv_nsec&&s.st_ctim.tv_sec==old.st_ctim.tv_sec&&s.st_ctim.tv_nsec==old.st_ctim.tv_nsec,"packed input mutated during read");}
inline void decode_payload(const Record&r,const uint8_t* src,std::vector<uint64_t>& out){
    out.resize(r.words);size_t offset=0,index=0;const size_t count=size_t(r.shape.n)*2;
    for(unsigned pair=0;pair<r.shape.k;++pair)for(const auto&p:r.shape.parameters){
        compactbits::decode(src+offset,count,p.q,out.data()+index);
        index+=count;offset+=compactbits::bytes(count,compactbits::width(p.q));}
    require(index==r.words&&offset==packed_bytes(r),"packed decoded exact length");
}
inline std::vector<uint8_t> wrapper(const Record&r,const std::string& digest){
    require(digest.size()==64&&digest.find_first_not_of("0123456789abcdef")==std::string::npos,"packed expected digest");
    std::vector<uint8_t> h(128,0);std::memcpy(h.data(),"GA3QPK01",8);
    auto put=[&](size_t at,uint64_t v,unsigned n){for(unsigned b=0;b<n;++b)h[at+b]=uint8_t(v>>(8*b));};
    put(8,1,4);put(12,64+24*r.shape.l,4);put(16,packed_bytes(r),8);put(24,64+24*r.shape.l+r.words*8,8);
    std::memcpy(h.data()+32,digest.data(),64);auto raw=input_header(r);h.insert(h.end(),raw.begin(),raw.end());return h;
}
inline void read_packed(const fs::path& path,const Record&r,const std::string& digest,std::vector<uint64_t>& out,
                        std::vector<uint8_t>& scratch,ReadStats* stats=nullptr){
    auto tick=std::chrono::steady_clock::now();Fd fd;fd.value=::open(path.c_str(),O_RDONLY|O_CLOEXEC|O_NOFOLLOW);require(fd.value>=0,"declared packed cache entry missing/unsafe: "+path.string());
    const auto h=wrapper(r,digest);const size_t n=packed_bytes(r);struct stat old{};
    require(::fstat(fd.value,&old)==0&&S_ISREG(old.st_mode)&&old.st_size==off_t(h.size()+n),"packed exact file size");
    require(::posix_fadvise(fd.value,0,0,POSIX_FADV_SEQUENTIAL)==0,"packed sequential advice");
    std::vector<uint8_t> actual(h.size());exact_read(fd.value,actual.data(),actual.size(),0,stats);require(actual==h,"packed header/source identity mismatch");
    if(stats)stats->header_ms+=ReadStats::ms(tick);tick=std::chrono::steady_clock::now();scratch.resize(n+8);out.resize(r.words);std::fill(scratch.begin()+n,scratch.end(),0);
    if(stats)stats->allocate_ms+=ReadStats::ms(tick);tick=std::chrono::steady_clock::now();exact_read(fd.value,scratch.data(),n,h.size(),stats);
    if(stats)stats->pread_ms+=ReadStats::ms(tick);tick=std::chrono::steady_clock::now();decode_payload(r,scratch.data(),out);
    if(stats){stats->range_ms+=ReadStats::ms(tick);stats->decode_ms+=ReadStats::ms(tick);++stats->packed_records;stats->logical_bytes+=r.words*8;stats->packed_payload_bytes+=n;++stats->records;stats->bytes+=n;}
    tick=std::chrono::steady_clock::now();identity_same(fd.value,old);r.unchanged();if(stats)stats->identity_ms+=ReadStats::ms(tick);
    tick=std::chrono::steady_clock::now();require(::posix_fadvise(fd.value,0,0,POSIX_FADV_DONTNEED)==0,"packed retirement advice");if(stats)stats->retire_ms+=ReadStats::ms(tick);
}
} }
