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
struct Grid {unsigned full_n=0,n=0,l=0,k=0,chunks=0;};
inline Grid grid(const fs::path& root,unsigned group){
 auto base=root/("group_"+std::to_string(group));std::ifstream f(base/"shape.json");require(bool(f)&&fs::file_size(base/"shape.json")<=16384,"mapped group shape missing/oversized");std::string s((std::istreambuf_iterator<char>(f)),{});
 Grid g{shape_uint(s,"N"),shape_uint(s,"chunk_N"),shape_uint(s,"L"),shape_uint(s,"K"),shape_uint(s,"chunks")};
 require(shape_uint(s,"group")==group&&g.n>=128&&g.n<=8192&&is_power_of_two(g.n)&&g.full_n>=g.n&&g.full_n<=131072&&is_power_of_two(g.full_n)&&g.full_n%g.n==0&&g.chunks==g.full_n/g.n&&g.chunks<=16&&g.l>=1&&g.l<=16&&g.k>=1&&g.k<=16,"mapped grid");
 std::ifstream manifest(base/"chunks.tsv");std::string line;require(bool(std::getline(manifest,line))&&line=="id\ttower_start\tcoefficient_start\tN\tL\tK","mapped TSV header");
 for(unsigned i=0;i<g.chunks;++i){require(bool(std::getline(manifest,line)),"mapped missing chunk row");std::ostringstream want;want<<"chunk_"<<i<<'\t'<<0<<'\t'<<i*g.n<<'\t'<<g.n<<'\t'<<g.l<<'\t'<<g.k;require(line==want.str(),"mapped chunk coverage/order");}require(!std::getline(manifest,line),"mapped extra chunk row");return g;
}
class Dataset {
 std::vector<std::unique_ptr<Record>> babies;
 std::array<std::vector<std::unique_ptr<Record>>,6> weights,gold;
 bool active=false;
 std::vector<uint64_t> baby_cache;
 unsigned cache_chunk=UINT32_MAX;
 std::vector<unsigned> retired;
 std::vector<bool> validated_babies;
 std::array<std::vector<bool>,6> retired_jobs;
public:
 unsigned baby_loads=0,baby_BO_fills=0;uint64_t retired_records=0;
private:
 static void matching(const InputCase& a,const InputCase& b){require(same_parameters(a,b),"mapped shape/moduli differ");}
public:
 Grid dimensions;InputCase shape;
 explicit Dataset(const fs::path& root,bool with_golden=true):dimensions(grid(root,0)){
  require(with_golden,"verified fixture Dataset requires full golden; live requests use the explicit separate interface");
  for(unsigned i=0;i<dimensions.chunks;++i){babies.push_back(std::make_unique<Record>(root/"shared"/("chunk_"+std::to_string(i)+"_baby.bin"),4));if(i)matching(babies.front()->shape,babies.back()->shape);}
  const auto& a=babies.front()->shape;require(a.n==dimensions.n&&a.l==dimensions.l&&a.k==dimensions.k,"mapped source grid/header differs");shape.n=a.n;shape.l=a.l;shape.k=a.k;shape.parameters=a.parameters;
  for(unsigned g=0;g<6;++g){const auto h=grid(root,g);require(h.full_n==dimensions.full_n&&h.n==dimensions.n&&h.l==dimensions.l&&h.k==dimensions.k&&h.chunks==dimensions.chunks,"mapped groups have different grids");
   for(unsigned i=0;i<dimensions.chunks;++i){const auto stem="chunk_"+std::to_string(i);auto base=root/("group_"+std::to_string(g))/"chunks";weights[g].push_back(std::make_unique<Record>(base/(stem+"_weight.bin"),3));gold[g].push_back(std::make_unique<Record>(base/(stem+"_expected.bin"),2));matching(shape,weights[g].back()->shape);matching(shape,gold[g].back()->shape);}
  }
 }
 void unchanged()const{for(const auto& x:babies)x->unchanged();for(unsigned g=0;g<6;++g){for(const auto& x:weights[g])x->unchanged();for(const auto& x:gold[g])x->unchanged();}}
 void begin_request(){require(!active,"mapped request already active");unchanged();active=true;cache_chunk=UINT32_MAX;baby_loads=0;baby_BO_fills=0;retired_records=0;retired.assign(dimensions.chunks,0);validated_babies.assign(dimensions.chunks,false);for(auto& v:retired_jobs)v.assign(dimensions.chunks,false);}
 bool cache_baby(unsigned chunk){
  require(active&&chunk<dimensions.chunks,"baby cache state/index");if(cache_chunk==chunk)return false;
  const auto& b=*babies[chunk];b.unchanged();baby_cache.resize(b.words);
  const bool checking=!validated_babies[chunk];
  for(unsigned pair=0;pair<shape.k;++pair)for(unsigned t=0;t<shape.l;++t){const auto q=shape.parameters[t].q;const size_t begin=(size_t(pair)*shape.l+t)*shape.n*2;for(size_t j=0;j<size_t(shape.n)*2;++j){auto value=b.word(begin+j);if(checking&&value>=q)throw std::runtime_error("noncanonical window baby");baby_cache[begin+j]=value;}}
  validated_babies[chunk]=true;
  cache_chunk=chunk;++baby_loads;return true;
 }
 size_t cache_bytes()const{return baby_cache.size()*sizeof(uint64_t);}
 void pack_cached(unsigned g,unsigned chunk,unsigned lane,unsigned lanes,uint64_t* dest,size_t count,bool fill_baby){
  require(active&&g<6&&chunk<dimensions.chunks&&cache_chunk==chunk&&(lanes==1||lanes==2)&&lane<lanes&&dest&&count==input_words()/lanes,"cached pack state/arguments");
  const auto& A=*weights[g][chunk];const auto& B=*babies[chunk];A.unchanged();B.unchanged();const auto n=shape.n/lanes;
  for(unsigned pair=0;pair<shape.k;++pair)for(unsigned t=0;t<shape.l;++t){const auto q=shape.parameters[t].q;const auto src=(size_t(pair)*shape.l+t)*shape.n*2+size_t(lane)*n*2;const auto dst=(size_t(pair)*shape.l+t)*n*4;
   for(unsigned j=0;j<n;++j){auto a0=A.word(src+2*j),a1=A.word(src+2*j+1);if(a0>=q||a1>=q)throw std::runtime_error("noncanonical cached weight");dest[dst+4*j]=a0;dest[dst+4*j+1]=a1;if(fill_baby){dest[dst+4*j+2]=baby_cache[src+2*j];dest[dst+4*j+3]=baby_cache[src+2*j+1];}}
  }if(fill_baby)++baby_BO_fills;
 }
 void retire_job(unsigned g,unsigned chunk,bool bounded){
  require(active&&g<6&&chunk<dimensions.chunks&&!retired_jobs[g][chunk],"duplicate or invalid retired job");
  retired_jobs[g][chunk]=true;if(bounded){weights[g][chunk]->retire();gold[g][chunk]->retire();retired_records+=2;}
  if(++retired[chunk]==6&&bounded){babies[chunk]->retire();++retired_records;}
 }
 void complete_coverage()const{require(retired.size()==dimensions.chunks&&std::all_of(retired.begin(),retired.end(),[](unsigned v){return v==6;})&&std::all_of(validated_babies.begin(),validated_babies.end(),[](bool v){return v;}),"incomplete six-group window or baby validation coverage");}

 void end_request(){require(active,"mapped request not active");unchanged();active=false;}
 void cancel_request()noexcept{active=false;}
 size_t input_words()const{return size_t(shape.n)*shape.l*shape.k*4;}
 uint64_t verified_words()const{return uint64_t(6)*dimensions.chunks*shape.output_words();}
 void pack(unsigned g,unsigned chunk,unsigned lane,unsigned lanes,uint64_t* dest,size_t count)const{
  require(active&&g<6&&chunk<dimensions.chunks&&(lanes==1||lanes==2)&&lane<lanes&&dest&&count==input_words()/lanes,"mapped pack arguments/state");
  const auto& A=*weights[g][chunk];const auto& B=*babies[chunk];A.unchanged();B.unchanged();const auto n=shape.n/lanes;
  for(unsigned pair=0;pair<shape.k;++pair)for(unsigned t=0;t<shape.l;++t){const auto q=shape.parameters[t].q;const auto src=(size_t(pair)*shape.l+t)*shape.n*2+size_t(lane)*n*2;const auto dst=(size_t(pair)*shape.l+t)*n*4;
   for(unsigned j=0;j<n;++j){auto a0=A.word(src+2*j),a1=A.word(src+2*j+1);if(a0>=q||a1>=q)throw std::runtime_error("noncanonical mapped weight group="+std::to_string(g)+" chunk="+std::to_string(chunk));dest[dst+4*j]=a0;dest[dst+4*j+1]=a1;dest[dst+4*j+2]=B.word(src+2*j);dest[dst+4*j+3]=B.word(src+2*j+1);}
  }
 }
 void verify(unsigned g,unsigned chunk,const std::vector<uint64_t>& output)const{
  require(active&&g<6&&chunk<dimensions.chunks&&output.size()==shape.output_words(),"mapped verify arguments/state");const auto& ref=*gold[g][chunk];ref.unchanged();
  for(unsigned t=0;t<shape.l;++t){auto q=shape.parameters[t].q;const size_t base=size_t(t)*shape.n*3;for(size_t j=0;j<size_t(shape.n)*3;++j){auto expected=ref.word(base+j);if(expected>=q||output[base+j]>=q||output[base+j]!=expected)throw std::runtime_error("mapped full output mismatch group="+std::to_string(g)+" chunk="+std::to_string(chunk)+" word="+std::to_string(base+j));}}
 }
 std::vector<uint64_t> expected(unsigned g,unsigned chunk)const{require(g<6&&chunk<dimensions.chunks,"mapped expected index");std::vector<uint64_t> out(shape.output_words());for(size_t i=0;i<out.size();++i)out[i]=gold[g][chunk]->word(i);return out;}
};
} }
