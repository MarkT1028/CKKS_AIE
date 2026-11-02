#pragma once
#include <future>
namespace { namespace windowed {
class SoftwareWindowBackend {
 struct Bank {std::array<std::vector<uint64_t>,2> input,output;std::array<unsigned,2> baby{{UINT32_MAX,UINT32_MAX}};std::future<void> done;};
 windowio::Dataset& source;std::array<Bank,2> banks;std::vector<uint64_t> merged;std::vector<Task> jobs;fs::path output;bool running=false,release=false;std::string fault;
 void fail(const char* stage,unsigned i){const auto j=jobs.at(i);if(j.group==3&&j.chunk==1&&fault==stage)throw std::runtime_error(std::string("SYNTHETIC_FAULT_")+stage);}
public:
 static constexpr const char* execution_backend="SOFTWARE_MODEL_NOT_BOARD";static constexpr unsigned aie_tiles=0;
 explicit SoftwareWindowBackend(windowio::Dataset& s):source(s),merged(s.shape.output_words()){for(auto& b:banks)for(unsigned l=0;l<2;++l){b.input[l].resize(s.input_words()/2);b.output[l].resize(s.shape.output_words()/2);}if(auto x=std::getenv("WINDOW_TEST_FAULT"))fault=x;}
 void configure(const std::vector<Task>& t,const fs::path& p,bool bounded){require(!running,"model configure active");jobs=t;output=p;release=bounded;for(auto& b:banks)b.baby={{UINT32_MAX,UINT32_MAX}};}
 void prepare(unsigned i,unsigned bank,boexp::Frame& f,Clock::time_point epoch){fail("prepare",i);const auto t=jobs.at(i);auto& b=banks.at(bank);f.timed("baby_cache_load",-1,epoch,[&]{source.cache_baby(t.chunk);});for(unsigned l=0;l<2;++l){f.timed("weight_pack_baby_if_needed",l,epoch,[&]{source.pack_cached(t.group,t.chunk,l,2,b.input[l].data(),b.input[l].size(),b.baby[l]!=t.chunk);});b.baby[l]=t.chunk;}for(unsigned l=0;l<2;++l){for(auto name:{"parameter_pack","parameter_write","input_sync","parameter_sync"})f.timed(name,l,epoch,[]{});f.timed("output_poison",l,epoch,[&]{std::fill(b.output[l].begin(),b.output[l].end(),UINT64_MAX);});f.timed("output_poison_sync",l,epoch,[]{});}}
 void start(unsigned i,unsigned bank){fail("start",i);require(!running,"model concurrent execution");running=true;auto& b=banks.at(bank);b.done=std::async(std::launch::async,[&]{const unsigned n=source.shape.n/2;for(unsigned l=0;l<2;++l)for(unsigned t=0;t<source.shape.l;++t){auto q=source.shape.parameters[t].q;for(unsigned j=0;j<n;++j){U128 x=0,y=0,z=0;for(unsigned p=0;p<source.shape.k;++p){auto k=((size_t(p)*source.shape.l+t)*n+j)*4;auto a=b.input[l].data()+k;x+=U128(a[0])*a[2];y+=U128(a[0])*a[3]+U128(a[1])*a[2];z+=U128(a[1])*a[3];}auto k=(size_t(t)*n+j)*3;b.output[l][k]=uint64_t(x%q);b.output[l][k+1]=uint64_t(y%q);b.output[l][k+2]=uint64_t(z%q);}}});}
 void wait(unsigned i,unsigned bank){fail("wait",i);banks.at(bank).done.get();}
 void complete(unsigned i,unsigned,boexp::Frame& f,Clock::time_point e){f.timed("status",-1,e,[&]{fail("status",i);running=false;});}
 void finish(unsigned i,unsigned bank,boexp::Frame& f,Clock::time_point e){fail("finish",i);auto t=jobs.at(i);f.timed("merge_poison",-1,e,[&]{std::fill(merged.begin(),merged.end(),UINT64_MAX);});for(unsigned l=0;l<2;++l){f.timed("output_sync",l,e,[]{});f.timed("merge",l,e,[&]{auto& out=banks[bank].output[l];boexp::merge_from(source.shape,l,out.data(),out.size(),merged);});}f.timed("verify",-1,e,[&]{fail("verify",i);source.verify(t.group,t.chunk,merged);});f.timed("input_retire",-1,e,[&]{fail("retire",i);source.retire_job(t.group,t.chunk,release);});}
 void save(unsigned i,unsigned){fail("save",i);auto t=jobs.at(i);streamio::save_output_bulk(output/("group_"+std::to_string(t.group))/("chunk_"+std::to_string(t.chunk)+"_output.bin"),source.shape,merged);}
 void cancel()noexcept{for(auto& b:banks)if(b.done.valid()){try{b.done.get();}catch(...){}}running=false;}
};
} }
