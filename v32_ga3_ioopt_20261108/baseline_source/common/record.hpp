#pragma once
#include <sys/mman.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <unistd.h>
#include <cerrno>
#include <cstring>
#include <memory>
#include <array>
#include <atomic>

// Linux read-only file-backed views. MAP_PRIVATE is NOT a private heap copy.
// The verified data directory is immutable for the lifetime of this object.
namespace { namespace windowio {
inline uint64_t little(const uint8_t* p,unsigned n){uint64_t x=0;for(unsigned i=0;i<n;++i)x|=uint64_t(p[i])<<(8*i);return x;}
struct Fd {
 int value=-1;
 ~Fd(){if(value>=0)::close(value);}
 Fd()=default;Fd(const Fd&)=delete;Fd&operator=(const Fd&)=delete;
};
struct Region {
 void* address=MAP_FAILED;size_t length=0;
 ~Region(){if(address!=MAP_FAILED)::munmap(address,length);}
 Region()=default;Region(const Region&)=delete;Region&operator=(const Region&)=delete;
};
class Record {
 Fd fd;Region map;struct stat identity{};
public:
 InputCase shape;unsigned kind=0;size_t words=0;fs::path path;
 Record(const fs::path& file,unsigned wanted):path(file){
  const uint16_t one=1;require(*reinterpret_cast<const uint8_t*>(&one)==1,"mapped source requires little-endian host");
  fd.value=::open(file.c_str(),O_RDONLY|O_CLOEXEC|O_NOFOLLOW);require(fd.value>=0,"cannot open immutable record: "+file.string());
  require(::fstat(fd.value,&identity)==0&&S_ISREG(identity.st_mode)&&identity.st_size>=64&&uint64_t(identity.st_size)<64ULL*1024*1024,"mapped record type/size");
  map.length=size_t(identity.st_size);map.address=::mmap(nullptr,map.length,PROT_READ,MAP_PRIVATE,fd.value,0);require(map.address!=MAP_FAILED,"read-only mmap failed");
  const auto* p=static_cast<const uint8_t*>(map.address);require(std::memcmp(p,"CKKSMAC1",8)==0,"mapped magic");
  kind=unsigned(little(p+12,4));require(little(p+8,4)==1&&kind==wanted&&(kind==2||kind==3||kind==4),"mapped version/kind");
  shape.n=little(p+16,4);shape.l=little(p+20,4);shape.k=little(p+24,4);
  require(shape.n>=128&&shape.n<=8192&&is_power_of_two(shape.n)&&shape.l>=1&&shape.l<=16&&shape.k>=1&&shape.k<=16,"mapped shape");
  require(little(p+28,4)==(kind==2?3:2)&&little(p+32,4)==1&&little(p+36,4)==64&&little(p+40,4)==0&&little(p+44,4)==0&&little(p+56,8)==0,"mapped layout/reserved");
  words=size_t(shape.n)*shape.l*(kind==2?3:2*shape.k);require(little(p+48,8)==words&&map.length==64+24ULL*shape.l+words*8,"mapped exact length");
  for(unsigned t=0;t<shape.l;++t){auto q=p+64+24*t;Parameter a{little(q,8),little(q+8,8),little(q+16,8)};validate_parameter(a,t);shape.parameters.push_back(a);}
 }
 Record(const Record&)=delete;Record&operator=(const Record&)=delete;
 uint64_t word(size_t i)const{
  if(i>=words)throw std::runtime_error("mapped word out of bounds");
  // memcpy avoids C++17 typed-object lifetime/aliasing assumptions for mmap.
  uint64_t x;std::memcpy(&x,static_cast<const uint8_t*>(map.address)+64+24*shape.l+8*i,8);return x;
 }
 std::vector<uint64_t> read_canonical()const{
  // Bounded sequential bulk reads avoid faulting a large mmap one page at a
  // time. Only one <=32MiB operand / <=3MiB reference is copied per call.
  unchanged();std::vector<uint64_t> output(words);auto* dest=reinterpret_cast<uint8_t*>(output.data());size_t done=0,bytes=words*8;
  while(done<bytes){auto n=::pread(fd.value,dest+done,std::min<size_t>(1024*1024,bytes-done),off_t(64+24*shape.l+done));if(n<0&&errno==EINTR)continue;require(n>0,"record bulk read failed/truncated: "+path.string());done+=size_t(n);}
  const unsigned pairs=kind==2?1:shape.k,components=kind==2?3:2;
  for(unsigned pair=0;pair<pairs;++pair)for(unsigned t=0;t<shape.l;++t){const auto q=shape.parameters[t].q;const size_t begin=(size_t(pair)*shape.l+t)*shape.n*components;
   for(size_t j=0;j<size_t(shape.n)*components;++j)if(output[begin+j]>=q)throw std::runtime_error("noncanonical bulk source: "+path.string());}
  unchanged();return output;
 }
 void retire()const{
  // Only this immutable fixture file, after its final consumer; no global
  // drop_caches/sysctl. These are advisory calls, not a RAM-size guarantee.
  require(::madvise(map.address,map.length,MADV_DONTNEED)==0,"input madvise failed");
  int e=::posix_fadvise(fd.value,0,0,POSIX_FADV_DONTNEED);
  require(e==0,"input fadvise failed");
 }
 void unchanged()const{
  struct stat now{};require(::fstat(fd.value,&now)==0&&now.st_dev==identity.st_dev&&now.st_ino==identity.st_ino&&now.st_size==identity.st_size&&now.st_mtim.tv_sec==identity.st_mtim.tv_sec&&now.st_mtim.tv_nsec==identity.st_mtim.tv_nsec&&now.st_ctim.tv_sec==identity.st_ctim.tv_sec&&now.st_ctim.tv_nsec==identity.st_ctim.tv_nsec,"mapped source changed during request: "+path.string());
 }
 void canonical()const{
  const unsigned pairs=kind==2?1:shape.k,components=kind==2?3:2;
  for(unsigned pair=0;pair<pairs;++pair)for(unsigned t=0;t<shape.l;++t){const auto q=shape.parameters[t].q;const size_t begin=(size_t(pair)*shape.l+t)*shape.n*components;
   for(size_t j=0;j<size_t(shape.n)*components;++j)if(word(begin+j)>=q)throw std::runtime_error("noncanonical mapped source "+path.string()+" at "+std::to_string(begin+j));
  }
 }
};
} }
