#pragma once
#ifndef CKKSMAC_PARSER_ONLY
namespace { namespace windowed {
class XrtWindowBackend {
 struct ReadBuffer {
  xrt::bo bo;uint64_t* words;std::string key;
  ReadBuffer(const xrt::device& d,size_t bytes,unsigned group):bo(d,bytes,xrt::bo::flags::cacheable,group),words(bo.map<uint64_t*>()){require(words,"split input BO map");}
 };
 struct Buffer {
  xrt::bo output,parameters;xrt::run reader,reducer;uint64_t* out;InputCase shape;
  Buffer(const xrt::device& d,Kernels& k,const InputCase& full):output(d,full.output_words()*8/2,xrt::bo::flags::cacheable,k.reducer.group_id(1)),parameters(d,full.l*32,k.reducer.group_id(2)),reader(k.reader),reducer(k.reducer),out(output.map<uint64_t*>()){
   require(out,"split output BO map");shape.n=full.n/2;shape.l=full.l;shape.k=full.k;shape.parameters=full.parameters;
   reducer.set_arg(1,output);reducer.set_arg(2,parameters);
  }
 };
 windowio::Dataset& source;std::array<std::unique_ptr<Kernels>,2> kernels;
 std::array<std::unique_ptr<ReadBuffer>,4> weights;std::unique_ptr<ReadBuffer> baby;
 std::array<std::array<std::unique_ptr<Buffer>,2>,2> banks;
 std::vector<uint64_t> merged;std::vector<Task> jobs;fs::path output;
 bool running=false,release=false,refresh=false;Clock::time_point deadline;
 uint64_t copy_bytes=0,sync_bytes=0,cache_hits=0;
 void upload(ReadBuffer& b,const std::string& key,const std::vector<uint64_t>& words,const char* copy_stage,const char* sync_stage,boexp::Frame& f,Clock::time_point epoch){
  require(!key.empty()&&words.size()==source.input_words()/2,"split canonical input shape");
  if(b.key==key){++cache_hits;return;}
  const size_t bytes=words.size()*sizeof(uint64_t);
  f.timed(copy_stage,-1,epoch,[&]{std::memcpy(b.words,words.data(),bytes);});copy_bytes+=bytes;
  f.timed(sync_stage,-1,epoch,[&]{b.bo.sync(XCL_BO_SYNC_BO_TO_DEVICE,bytes,0);});sync_bytes+=bytes;
  b.key=key; // Publish only after both copy and sync succeeded.
 }
public:
 static constexpr const char* execution_backend="XRT_PURE_PL";static constexpr unsigned aie_tiles=0;
 XrtWindowBackend(const xrt::device& d,const xrt::uuid& uuid,windowio::Dataset& s,xrt::graph* graph):source(s),merged(s.shape.output_words()){
  require(!graph,"split pure PL must not construct graph");
  const char* mode=std::getenv("V32_GA3_SPLIT_REFRESH");require(!mode||std::string(mode)=="0"||std::string(mode)=="1","split refresh must be 0 or 1");refresh=mode&&std::string(mode)=="1";
  for(unsigned l=0;l<2;++l)kernels[l]=std::make_unique<Kernels>(d,uuid,l);
  const unsigned wa=kernels[0]->reader.group_id(0),bb=kernels[0]->reader.group_id(1);
  require(wa==kernels[1]->reader.group_id(0)&&bb==kernels[1]->reader.group_id(1),"split lanes require identical input memory groups");
  const size_t bytes=source.input_words()/2*sizeof(uint64_t);
  for(auto& w:weights)w=std::make_unique<ReadBuffer>(d,bytes,wa);
  baby=std::make_unique<ReadBuffer>(d,bytes,bb);
  for(auto& bank:banks)for(unsigned l=0;l<2;++l)bank[l]=std::make_unique<Buffer>(d,*kernels[l],source.shape);
 }
 void configure(const std::vector<Task>& t,const fs::path& out,bool bounded){
  require(!running,"split configure while running");jobs=t;output=out;release=bounded;merged.resize(source.shape.output_words());
  for(auto& bank:banks)for(unsigned l=0;l<2;++l){auto& b=*bank[l];b.shape.n=source.shape.n/2;b.shape.l=source.shape.l;b.shape.k=source.shape.k;b.shape.parameters=source.shape.parameters;
   b.reader.set_arg(1,baby->bo);b.reader.set_arg(3,b.shape.n);b.reader.set_arg(4,b.shape.l);b.reader.set_arg(5,b.shape.k);b.reader.set_arg(6,l);
   b.reducer.set_arg(3,b.shape.n);b.reducer.set_arg(4,b.shape.l);b.reducer.set_arg(5,b.shape.k);
  }
 }
 void prepare(unsigned i,unsigned bank,boexp::Frame& f,Clock::time_point epoch){
  const auto job=jobs.at(i);
  if(i==0){copy_bytes=sync_bytes=cache_hits=0;if(refresh){baby->key.clear();for(auto& w:weights)w->key.clear();}}
  // One prepare worker; shared input BOs are read-only after first upload.
  // Distinct group weight BOs are never overwritten while another CU reads them.
  source.cache_baby(job.chunk);
  upload(*baby,source.split_baby_key(),source.split_baby_words(),"baby_copy","baby_sync",f,epoch);
  upload(*weights[job.group],source.split_weight_key(job.group),source.split_weight_words(job.group),"weight_copy","weight_sync",f,epoch);
  for(unsigned l=0;l<2;++l){auto& b=*banks[bank][l];b.reader.set_arg(0,weights[job.group]->bo);std::vector<uint64_t> params;
   f.timed("parameter_pack",l,epoch,[&]{params=pack_parameters(b.shape);});
   f.timed("parameter_write",l,epoch,[&]{b.parameters.write(params.data(),params.size()*8,0);});
   f.timed("parameter_sync",l,epoch,[&]{b.parameters.sync(XCL_BO_SYNC_BO_TO_DEVICE,b.shape.l*32,0);});
   f.timed("output_poison",l,epoch,[&]{std::fill_n(b.out,b.shape.output_words(),UINT64_MAX);});
   f.timed("output_poison_sync",l,epoch,[&]{b.output.sync(XCL_BO_SYNC_BO_TO_DEVICE,b.shape.output_words()*8,0);});
  }
 }
 void start(unsigned,unsigned bank){require(!running,"split simultaneous CU invocation");running=true;deadline=Clock::now()+std::chrono::seconds(120);
  for(auto& b:banks[bank])b->reducer.start();for(auto& b:banks[bank])b->reader.start();
 }
 void wait(unsigned,unsigned bank){for(auto& b:banks[bank])wait_for_run("split reader",b->reader,deadline);for(auto& b:banks[bank])wait_for_run("split reducer",b->reducer,deadline);}
 void complete(unsigned,unsigned,boexp::Frame& f,Clock::time_point epoch){f.timed("status",-1,epoch,[&]{for(auto& k:kernels){require(k->reader.read_register(0x10)==0,"split reader status");require(k->reducer.read_register(0x10)==0,"split reducer status");}running=false;});}
 void finish(unsigned i,unsigned bank,boexp::Frame& f,Clock::time_point epoch){auto job=jobs.at(i);for(unsigned l=0;l<2;++l){auto& b=*banks[bank][l];
  f.timed("output_sync",l,epoch,[&]{b.output.sync(XCL_BO_SYNC_BO_FROM_DEVICE,b.shape.output_words()*8,0);});
  f.timed("merge_verify",l,epoch,[&]{source.merge_verify_lane(job.group,l,b.out,b.shape.output_words(),merged);});
 }f.timed("input_retire",-1,epoch,[&]{source.retire_job(job.group,job.chunk,release);});}
 void save(unsigned i,unsigned){auto t=jobs.at(i);auto path=output/("group_"+std::to_string(t.group))/("chunk_"+std::to_string(t.chunk)+"_output.bin");streamio::save_verified_digest(path,source.verified_digest(t.group));if(source.actual_sample)streamio::save_output_bulk(path,source.shape,merged);}
 uint64_t copied_bytes()const{return copy_bytes;}uint64_t synced_bytes()const{return sync_bytes;}uint64_t input_cache_hits()const{return cache_hits;}
 void cancel()noexcept{for(auto& bank:banks)for(auto& b:bank)if(b){try{b->reader.abort();}catch(...){}try{b->reducer.abort();}catch(...){}}running=false;}
};
} }
#endif
