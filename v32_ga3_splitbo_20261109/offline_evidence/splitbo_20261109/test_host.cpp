// Directly exercises the deployed backend with separate host/device BO images.
// This is a software contract test, never board performance evidence.
#include <cstring>
#include <filesystem>
#include <fstream>
#include <map>
#include <memory>
#include <iostream>
#include <atomic>
#include "../../board_packages/v32_ga3_splitbo_20261109/common/finish_overlap.hpp"
namespace fs=std::filesystem;using Clock=boexp::Clock;
static void require(bool x,const char*s){if(!x)throw std::runtime_error(s);}
struct Param{uint64_t q;};
struct InputCase{unsigned n=128,l=16,k=16;std::vector<Param> parameters;size_t output_words()const{return size_t(n)*l*3;}};
std::vector<uint64_t> pack_parameters(const InputCase&s){std::vector<uint64_t> p(s.l*4);for(unsigned t=0;t<s.l;++t)p[t*4]=s.parameters[t].q;return p;}
namespace xrt {
static bool corrupt_input_sync=false;
struct device{};struct uuid{};struct graph{};
struct Storage{std::vector<uint64_t> host,dev;Storage(size_t n):host(n/8),dev(n/8){}};
class bo{public:enum class flags{cacheable};std::shared_ptr<Storage> s;
 bo(const device&,size_t n,flags,unsigned):s(std::make_shared<Storage>(n)){require(n%8==0,"alignment");}
 bo(const device&d,size_t n,unsigned g):bo(d,n,flags::cacheable,g){}
 template<class T>T map(){return reinterpret_cast<T>(s->host.data());}
 void write(const void*p,size_t n,size_t off){require(n+off<=s->host.size()*8,"write range");std::memcpy((char*)s->host.data()+off,p,n);}
 void sync(int dir,size_t n,size_t off){require(n+off<=s->host.size()*8,"sync range");auto&dst=dir==0?s->dev:s->host;auto&src=dir==0?s->host:s->dev;std::memcpy((char*)dst.data()+off,(char*)src.data()+off,n);if(corrupt_input_sync&&dir==0&&n>100000)dst[0]^=1;}
};
struct kernel{bool reader;unsigned lane;unsigned group_id(unsigned)const{return 0;}unsigned read_register(unsigned)const{return 0;}};
struct run;static run* reducers[2];
struct run{kernel k;std::map<unsigned,bo> bos;std::map<unsigned,unsigned> scalars;
 run(const kernel&v):k(v){}void set_arg(unsigned i,const bo&b){bos.insert_or_assign(i,b);}void set_arg(unsigned i,unsigned v){scalars[i]=v;}
 void start(){if(!k.reader){reducers[k.lane]=this;return;}auto*r=reducers[k.lane];require(r,"reducer launched first");
  unsigned n=scalars.at(3),l=scalars.at(4),count=scalars.at(5),lane=scalars.at(6);require(lane==k.lane,"lane argument");
  auto&a=bos.at(0).s->dev;auto&b=bos.at(1).s->dev;auto&o=r->bos.at(1).s->dev;auto&p=r->bos.at(2).s->dev;
  require(r->scalars.at(3)==n&&r->scalars.at(4)==l&&r->scalars.at(5)==count,"runtime shape match");
  for(unsigned t=0;t<l;++t)for(unsigned j=0;j<n;++j){unsigned __int128 sums[3]={};for(unsigned z=0;z<count;++z){size_t at=((size_t(z)*l+t)*(2*n)+lane*n+j)*2;require(at+1<a.size()&&at+1<b.size(),"canonical reader bounds");sums[0]+=(unsigned __int128)a[at]*b[at];sums[1]+=(unsigned __int128)a[at]*b[at+1]+(unsigned __int128)a[at+1]*b[at];sums[2]+=(unsigned __int128)a[at+1]*b[at+1];}for(unsigned c=0;c<3;++c)o[(size_t(t)*n+j)*3+c]=uint64_t(sums[c]%p[t*4]);}
 }void abort(){}
};
}
constexpr int XCL_BO_SYNC_BO_TO_DEVICE=0,XCL_BO_SYNC_BO_FROM_DEVICE=1;
struct Kernels{xrt::kernel reader,reducer;Kernels(const xrt::device&,const xrt::uuid&,unsigned l):reader{true,l},reducer{false,l}{}};
void wait_for_run(const char*,xrt::run&,Clock::time_point){}
namespace windowio {
struct Dataset{InputCase shape;std::array<std::vector<uint64_t>,4>a;std::vector<uint64_t>b;std::string block,babykey;bool active=false;unsigned mask=0,lanes[4]={};
 Dataset(){admit(0,0,16);}
 void admit(unsigned blk,unsigned ct,unsigned l){require(!active,"admit active");shape.l=l;shape.parameters.assign(l,{(1ULL<<51)-129});block=std::to_string(blk);babykey=block+":"+std::to_string(ct);size_t size=size_t(shape.n)*l*shape.k*2;for(unsigned g=0;g<4;++g){a[g].resize(size);for(size_t i=0;i<size;++i)a[g][i]=shape.parameters[0].q-1-(i+7*g+11*blk)%89;}b.resize(size);for(size_t i=0;i<size;++i)b[i]=shape.parameters[0].q-1-(i+13*ct+5*blk)%97;}
 size_t input_words()const{return size_t(shape.n)*shape.l*shape.k*4;}
 void begin_request(){require(!active,"begin active");active=true;mask=0;std::fill_n(lanes,4,0);}
 void end_request(){require(mask==15,"all four verified");active=false;}
 void cache_baby(unsigned c){require(active&&c==0,"source active");}
 std::string split_baby_key()const{return babykey;}std::string split_weight_key(unsigned g)const{return block+":"+std::to_string(g);}
 const std::vector<uint64_t>&split_baby_words()const{return b;}const std::vector<uint64_t>&split_weight_words(unsigned g)const{return a[g];}
 void merge_verify_lane(unsigned g,unsigned lane,const uint64_t*out,size_t words,std::vector<uint64_t>&merged){require(active&&!(lanes[g]&(1<<lane))&&words==shape.output_words()/2,"merge ownership");unsigned n=shape.n/2;
  for(unsigned t=0;t<shape.l;++t)for(unsigned j=0;j<n;++j){unsigned __int128 sums[3]={};for(unsigned z=0;z<shape.k;++z){size_t i=((size_t(z)*shape.l+t)*shape.n+lane*n+j)*2;sums[0]+=(unsigned __int128)a[g][i]*b[i];sums[1]+=(unsigned __int128)a[g][i]*b[i+1]+(unsigned __int128)a[g][i+1]*b[i];sums[2]+=(unsigned __int128)a[g][i+1]*b[i+1];}for(unsigned c=0;c<3;++c){size_t i=(size_t(t)*n+j)*3+c;require(out[i]==uint64_t(sums[c]%shape.parameters[t].q),"host/device canonical mismatch or stale reuse");merged[(size_t(t)*shape.n+lane*n+j)*3+c]=out[i];}}
  lanes[g]|=1<<lane;
 }
 void retire_job(unsigned g,unsigned chunk,bool){require(active&&chunk==0&&lanes[g]==3&&!(mask&(1<<g)),"retire verified");mask|=1<<g;}
 bool actual_sample=false;std::string verified_digest(unsigned)const{return "test";}
};
}
namespace streamio{void save_verified_digest(const fs::path&,const std::string&){}void save_output_bulk(const fs::path&,const InputCase&,const std::vector<uint64_t>&){}}
namespace {namespace windowed{struct Task{unsigned group,chunk;};}}
#include "../../board_packages/v32_ga3_splitbo_20261109/host/split_xrt.hpp"
int main(){try{for(bool refresh:{false,true}){
 setenv("V32_GA3_SPLIT_REFRESH",refresh?"1":"0",1);windowio::Dataset src;windowed::XrtWindowBackend backend({}, {},src,nullptr);boexp::Worker worker;
 auto one=[&](unsigned expected_records){backend.configure({{3,0},{2,0},{1,0},{0,0}},"unused",false);src.begin_request();auto replay=boexp::run_finish_overlap(backend,4,worker,false);src.end_request();size_t bytes=src.input_words()/2*8;
  require(backend.copied_bytes()==expected_records*bytes&&backend.synced_bytes()==expected_records*bytes,"copy/sync cache accounting");require(backend.input_cache_hits()==8-expected_records,"hit accounting");require(replay.frames.size()==4,"replay frames");};
 one(5);one(refresh?5:0);src.admit(0,1,16);one(refresh?5:1);src.admit(1,15,5);one(5);one(refresh?5:0);worker.close();
 std::cout<<"PASS_SPLIT_BACKEND refresh="<<refresh<<" first_use warm_reuse ct_change L16_to_L5 canonical_sync_and_merge=1\n";
}
 setenv("V32_GA3_SPLIT_REFRESH","0",1);windowio::Dataset src;windowed::XrtWindowBackend backend({}, {},src,nullptr);boexp::Worker worker;backend.configure({{0,0},{1,0},{2,0},{3,0}},"unused",false);src.begin_request();xrt::corrupt_input_sync=true;bool rejected=false;
 try{boexp::run_finish_overlap(backend,4,worker,false);}catch(const std::exception&){rejected=true;}
 require(rejected,"corrupt BO sync silently accepted");std::cout<<"PASS_CORRUPTED_DEVICE_INPUT_REJECTED software_contract_only=1\n";
 return 0;}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
