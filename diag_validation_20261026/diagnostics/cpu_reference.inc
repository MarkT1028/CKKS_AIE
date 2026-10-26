// Raw CKKS MAC reference: the historical U128 accumulation + one modulus per sum.
// 1 or 2 persistent compute threads. Not an OpenFHE or an optimal-CPU claim.
#include "parser/variant_config.hpp"
#define CKKSMAC_PARSER_ONLY
#define main legacy_parser_main
#include "parser/timed_base.hpp"
#undef main
#include <algorithm>
#include <cmath>
#include <condition_variable>
#include <mutex>
#include <random>
#include <thread>
#include <sched.h>
#include <pthread.h>
#include <unistd.h>
#include <sys/syscall.h>
#include <cstring>

namespace {
#include "parser/expected_reader.hpp"
using Clock=std::chrono::steady_clock;
double elapsed(Clock::time_point a,Clock::time_point b){return std::chrono::duration<double,std::milli>(b-a).count();}
double med(std::vector<double> a){std::sort(a.begin(),a.end());require(!a.empty(),"no measured samples");auto n=a.size();return n%2?a[n/2]:(a[n/2-1]+a[n/2])/2;}
double p95(std::vector<double> a){std::sort(a.begin(),a.end());return a[size_t(std::ceil(a.size()*.95))-1];}
unsigned count(const char* s,unsigned maximum){std::string t(s);require(!t.empty()&&t.find_first_not_of("0123456789")==std::string::npos,"invalid count");auto n=std::stoul(t);require(n<=maximum,"count exceeds limit");return unsigned(n);}
void compare(const std::vector<uint64_t>& out,const std::vector<uint64_t>& expected){
 require(out.size()==expected.size(),"output size mismatch");
 for(size_t i=0;i<out.size();++i)if(out[i]!=expected[i])throw std::runtime_error("CPU mismatch at word "+std::to_string(i));
}
void save_output(const fs::path& path,const InputCase& in,const std::vector<uint64_t>& out){
 require(!fs::exists(path),"output file exists");require(out.size()==in.output_words(),"saved output length mismatch");
 std::ofstream f(path,std::ios::binary);require(bool(f),"cannot create CPU output");f.write("CKKSMAC1",8);
 auto put=[&](uint64_t value,unsigned bytes){for(unsigned j=0;j<bytes;++j)f.put(char((value>>(8*j))&255));};
 for(uint32_t v:std::array<uint32_t,10>{1,2,in.n,in.l,in.k,3,1,64,0,0})put(v,4);
 put(out.size(),8);put(0,8);for(const auto& p:in.parameters){put(p.q,8);put(p.mu_lo,8);put(p.mu_hi,8);}
 for(auto value:out){put(value,8);}
 f.close();require(bool(f),"CPU output write failed");
}
void compute_range(const InputCase& in,std::vector<uint64_t>& out,unsigned begin,unsigned end){
 for(unsigned t=0;t<in.l;++t){const uint64_t q=in.parameters[t].q;
  for(unsigned j=begin;j<end;++j){U128 s0=0,s1=0,s2=0;
   for(unsigned pair=0;pair<in.k;++pair){const size_t b=((size_t(pair)*in.l+t)*in.n+j)*4;
    const auto a0=in.words[b],a1=in.words[b+1],b0=in.words[b+2],b1=in.words[b+3];
    s0+=U128(a0)*b0;s1+=U128(a0)*b1+U128(a1)*b0;s2+=U128(a1)*b1;
   }
   // q < 2^60 and K <= 16: even s1 < 2^125, so U128 does not overflow.
   size_t b=(size_t(t)*in.n+j)*3;out[b]=uint64_t(s0%q);out[b+1]=uint64_t(s1%q);out[b+2]=uint64_t(s2%q);
  }
 }
}

std::vector<int> allowed_cpus(){
 cpu_set_t set;CPU_ZERO(&set);require(sched_getaffinity(0,sizeof(set),&set)==0,"get affinity failed");
 std::vector<int> cpus;for(int c=0;c<CPU_SETSIZE;++c)if(CPU_ISSET(c,&set))cpus.push_back(c);return cpus;
}
void pin_cpu(int cpu){
 require(cpu>=0&&cpu<CPU_SETSIZE,"CPU outside CPU_SETSIZE");cpu_set_t set;CPU_ZERO(&set);CPU_SET(cpu,&set);
 int rc=pthread_setaffinity_np(pthread_self(),sizeof(set),&set);
 require(rc==0,std::string("pthread_setaffinity_np: ")+std::strerror(rc));
 require(allowed_cpus()==std::vector<int>{cpu},"worker affinity verification failed");
}
std::vector<int> parse_cpus(const std::string& text){
 std::vector<int> result;std::istringstream in(text);std::string word;
 require(!text.empty()&&text.back()!=',',"invalid CPU list");
 while(std::getline(in,word,',')){
  require(!word.empty()&&word.find_first_not_of("0123456789")==std::string::npos,"invalid CPU list");
  auto cpu=std::stoul(word);require(cpu<CPU_SETSIZE,"CPU outside CPU_SETSIZE");
  require(std::find(result.begin(),result.end(),int(cpu))==result.end(),"duplicate CPU");result.push_back(int(cpu));
 }return result;
}
class ComputePool {
 const InputCase& in;std::vector<uint64_t>& out;unsigned threads;bool pinned;std::vector<int> targets;
 std::mutex mutex;std::condition_variable ready,finished;
 std::vector<std::thread> workers;unsigned generation=0,done=0,initialized=0;bool stop=false;std::string init_error;
 void initialize(unsigned lane){
  if(pinned)pin_cpu(targets.at(lane));
  affinity[lane]=allowed_cpus();tids[lane]=long(syscall(SYS_gettid));
 }
 void worker(unsigned lane){
  std::string error;try{initialize(lane);}catch(const std::exception& e){error=e.what();}
  {std::lock_guard<std::mutex> lock(mutex);if(!error.empty())init_error=error;++initialized;finished.notify_one();}
  if(!error.empty())return;
  unsigned observed=0;
  for(;;){std::unique_lock<std::mutex> lock(mutex);ready.wait(lock,[&]{return stop||generation!=observed;});
   if(stop)return;
   observed=generation;lock.unlock();
   cpu_begin[lane]=sched_getcpu();compute_range(in,out,in.n*lane/threads,in.n*(lane+1)/threads);cpu_end[lane]=sched_getcpu();
   lock.lock();++done;if(done==threads)finished.notify_one();
  }
 }
 void shutdown(){
  {std::lock_guard<std::mutex> lock(mutex);stop=true;}ready.notify_all();
  for(auto& w:workers)if(w.joinable())w.join();
 }
public:
 std::array<int,2> cpu_begin{{-1,-1}},cpu_end{{-1,-1}};
 std::array<long,2> tids{{-1,-1}};std::array<std::vector<int>,2> affinity;
 ComputePool(const InputCase& input,std::vector<uint64_t>& output,unsigned n,bool do_pin=false,std::vector<int> cpus={}):
  in(input),out(output),threads(n),pinned(do_pin),targets(std::move(cpus)){
  require(n==1||n==2,"compute thread count must be 1 or 2");
  if(pinned){require(targets.size()==n,"need one distinct CPU per compute thread");auto available=allowed_cpus();
   for(int c:targets)require(std::find(available.begin(),available.end(),c)!=available.end(),"requested CPU not allowed");}
  if(n==1){initialize(0);return;}
  try{
   for(unsigned lane=0;lane<n;++lane)workers.emplace_back([this,lane]{worker(lane);});
   std::unique_lock<std::mutex> lock(mutex);finished.wait(lock,[&]{return initialized==threads;});
   auto error=init_error;lock.unlock();require(error.empty(),error);
  }catch(...){shutdown();throw;}
 }
 void run(){
  if(threads==1){cpu_begin[0]=sched_getcpu();compute_range(in,out,0,in.n);cpu_end[0]=sched_getcpu();}
  else {std::unique_lock<std::mutex> lock(mutex);done=0;++generation;ready.notify_all();finished.wait(lock,[&]{return done==threads;});}
  for(unsigned lane=0;lane<threads;++lane){require(cpu_begin[lane]>=0&&cpu_end[lane]>=0,"sched_getcpu failed");
   if(pinned)require(cpu_begin[lane]==targets[lane]&&cpu_end[lane]==targets[lane],"pinned worker ran on unexpected CPU");}
 }
 ~ComputePool(){shutdown();}
 void save_affinity(const fs::path& path,const std::string& mode){
  std::ofstream f(path);f<<"{\"mode\":\""<<mode<<"\",\"compute_threads\":"<<threads<<",\"workers\":[";
  for(unsigned i=0;i<threads;++i){if(i)f<<',';f<<"{\"lane\":"<<i<<",\"tid\":"<<tids[i]<<",\"allowed_cpus\":[";
   for(size_t j=0;j<affinity[i].size();++j){if(j)f<<',';f<<affinity[i][j];}
   f<<"],\"target_cpu\":"<<(pinned?targets[i]:-1)<<'}';}
  f<<"]}\n";f.close();require(bool(f),"affinity record write failed");
 }
};
std::vector<uint64_t> independent_reference(const InputCase& in){
 std::vector<uint64_t> out(in.output_words());
 for(unsigned t=0;t<in.l;++t)for(unsigned j=0;j<in.n;++j)for(unsigned pair=0;pair<in.k;++pair){
  auto q=in.parameters[t].q;size_t b=((size_t(pair)*in.l+t)*in.n+j)*4,o=(size_t(t)*in.n+j)*3;
  const auto a0=in.words[b],a1=in.words[b+1],b0=in.words[b+2],b1=in.words[b+3];
  out[o]=uint64_t((U128(out[o])+U128(a0)*b0%q)%q);
  out[o+1]=uint64_t((U128(out[o+1])+U128(a0)*b1%q+U128(a1)*b0%q)%q);
  out[o+2]=uint64_t((U128(out[o+2])+U128(a1)*b1%q)%q);
 }
 return out;
}
void selftest(){
 std::mt19937_64 rng(20261023);unsigned tests=0;
 for(unsigned k:{1u,3u,16u})for(unsigned pattern=0;pattern<3;++pattern){
  InputCase in;in.n=128;in.l=3;in.k=k;
  for(uint64_t q:{(uint64_t(1)<<48)+1,(uint64_t(1)<<59)-1,(uint64_t(1)<<60)-1}){Parameter p;p.q=q;in.parameters.push_back(p);}
  in.words.resize(size_t(in.n)*in.l*in.k*4);
  for(unsigned pair=0;pair<k;++pair)for(unsigned t=0;t<in.l;++t)for(unsigned j=0;j<in.n;++j)for(unsigned c=0;c<4;++c){
   auto q=in.parameters[t].q;in.words[((size_t(pair)*in.l+t)*in.n+j)*4+c]=pattern==0?0:pattern==1?q-1:rng()%q;
  }
  auto expected=independent_reference(in);
  for(unsigned n:{1u,2u}){std::vector<uint64_t> output(expected.size(),UINT64_MAX);ComputePool pool(in,output,n);
   for(unsigned rep=0;rep<5;++rep){std::fill(output.begin(),output.end(),UINT64_MAX);pool.run();compare(output,expected);}++tests;
  }
 }
 std::vector<uint64_t> a{1,2,3},b=a;b[1]^=1;bool caught=false;try{compare(a,b);}catch(...){caught=true;}require(caught,"fault injection was not detected");
 auto cpus=allowed_cpus();
 if(cpus.size()>=2){InputCase small;small.n=128;small.l=1;small.k=16;Parameter p;p.q=(uint64_t(1)<<60)-1;small.parameters.push_back(p);
  small.words.assign(size_t(small.n)*small.k*4,p.q-1);auto ref=independent_reference(small);
  for(unsigned n:{1u,2u}){std::exception_ptr error;std::thread isolated([&]{try{std::vector<uint64_t> out(ref.size());std::vector<int> target(cpus.begin(),cpus.begin()+n);ComputePool pool(small,out,n,true,target);for(int r=0;r<5;++r){pool.run();compare(out,ref);}}catch(...){error=std::current_exception();}});isolated.join();if(error)std::rethrow_exception(error);++tests;}}
 std::cout<<"PASS CPU_SELFTEST configurations="<<tests<<" repetitions_each=5 edge_zero_max_random=1 corruption_detected=1\n";
}
}
