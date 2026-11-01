#pragma once
#include <future>
namespace { namespace streaming {
class SoftwareStreamBackend {
 struct Buff {std::array<std::vector<uint64_t>,2> input,output;std::future<void> done;};
 streamio::Dataset& source;std::array<Buff,2> banks;std::vector<uint64_t> merged;unsigned group=0;bool running=false;fs::path output_dir;std::string fault;
 void fail(const char* stage,unsigned i){if(group==3&&i==1&&fault==stage)throw std::runtime_error(std::string("SYNTHETIC_FAULT_")+stage);}
public:
 static constexpr const char* execution_backend="SOFTWARE_MODEL_NOT_BOARD";
 explicit SoftwareStreamBackend(streamio::Dataset& s):source(s),merged(s.shape.output_words()){for(auto& b:banks)for(unsigned l=0;l<2;++l){b.input[l].resize(s.input_words()/2);b.output[l].resize(s.shape.output_words()/2);}const auto* f=std::getenv("STREAM_TEST_FAULT");if(f)fault=f;}
 void select_group(unsigned g,const fs::path& output){require(g<6&&!running,"model group transition");group=g;output_dir=output;}
 void prepare(unsigned i,unsigned bank,boexp::Frame& frame,Clock::time_point epoch){fail("prepare",i);auto& b=banks.at(bank);for(unsigned l=0;l<2;++l)frame.timed("pack_A_check_shared_B",l,epoch,[&]{source.pack(group,i,l,2,b.input[l].data(),b.input[l].size());});for(unsigned l=0;l<2;++l){for(const char* name:{"parameter_pack","parameter_write","input_sync","parameter_sync"})frame.timed(name,l,epoch,[]{});frame.timed("output_poison",l,epoch,[&]{std::fill(b.output[l].begin(),b.output[l].end(),UINT64_MAX);});frame.timed("output_poison_sync",l,epoch,[]{});}}
 void start(unsigned i,unsigned bank){fail("start",i);require(!running,"model concurrent graph");running=true;auto& b=banks.at(bank);b.done=std::async(std::launch::async,[&]{const auto n=source.shape.n/2;for(unsigned l=0;l<2;++l)for(unsigned t=0;t<source.shape.l;++t){auto q=source.shape.parameters[t].q;for(unsigned j=0;j<n;++j){U128 s0=0,s1=0,s2=0;for(unsigned pair=0;pair<source.shape.k;++pair){auto k=((size_t(pair)*source.shape.l+t)*n+j)*4;const auto* x=b.input[l].data()+k;s0+=U128(x[0])*x[2];s1+=U128(x[0])*x[3]+U128(x[1])*x[2];s2+=U128(x[1])*x[3];}auto k=(size_t(t)*n+j)*3;b.output[l][k]=uint64_t(s0%q);b.output[l][k+1]=uint64_t(s1%q);b.output[l][k+2]=uint64_t(s2%q);}}});}
 void wait(unsigned i,unsigned bank){fail("wait",i);banks.at(bank).done.get();}
 void complete(unsigned i,unsigned,boexp::Frame& frame,Clock::time_point epoch){frame.timed("status",-1,epoch,[&]{fail("status",i);running=false;});}
 void finish(unsigned i,unsigned bank,boexp::Frame& frame,Clock::time_point epoch){fail("finish",i);frame.timed("merge_poison",-1,epoch,[&]{std::fill(merged.begin(),merged.end(),UINT64_MAX);});for(unsigned l=0;l<2;++l){frame.timed("output_sync",l,epoch,[]{});frame.timed("merge",l,epoch,[&]{auto& v=banks.at(bank).output[l];boexp::merge_from(source.shape,l,v.data(),v.size(),merged);});}frame.timed("verify",-1,epoch,[&]{fail("verify",i);source.verify(group,i,merged);});}
 void save(unsigned i,unsigned){fail("save",i);streamio::save_output_bulk(output_dir/("chunk_"+std::to_string(i)+"_output.bin"),source.shape,merged);}
 void cancel()noexcept{for(auto& b:banks)if(b.done.valid()){try{b.done.get();}catch(...){}}running=false;}
};
} }
