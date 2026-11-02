#pragma once
#ifndef CKKSMAC_PARSER_ONLY
namespace { namespace windowed {
class XrtWindowBackend {
 struct Buffer {xrt::bo input,output,parameters;xrt::run reader,reducer;std::unique_ptr<xrt::run> multiply;uint64_t* in;uint64_t* out;InputCase shape;unsigned baby=UINT32_MAX;
  Buffer(const xrt::device& d,Kernels& k,const InputCase& full,xrt::kernel* mul):input(d,size_t(full.n)*full.l*full.k*4*8/2,k.reader.group_id(0)),output(d,full.output_words()*8/2,k.reducer.group_id(1)),parameters(d,full.l*32,k.reducer.group_id(2)),reader(k.reader),reducer(k.reducer){
   shape.n=full.n/2;shape.l=full.l;shape.k=full.k;shape.parameters=full.parameters;in=input.map<uint64_t*>();out=output.map<uint64_t*>();require(in&&out,"window BO map");reader.set_arg(0,input);reader.set_arg(3,shape.n);reader.set_arg(4,shape.l);reader.set_arg(5,shape.k);reducer.set_arg(1,output);reducer.set_arg(2,parameters);reducer.set_arg(3,shape.n);reducer.set_arg(4,shape.l);reducer.set_arg(5,shape.k);
   if(mul){multiply=std::make_unique<xrt::run>(*mul);multiply->set_arg(3,shape.n);multiply->set_arg(4,shape.l);multiply->set_arg(5,shape.k);}
  }
 };
 windowio::Dataset& source;xrt::graph* graph;std::array<std::unique_ptr<Kernels>,2> kernels;std::array<std::unique_ptr<xrt::kernel>,2> multiply_kernels;std::array<std::array<std::unique_ptr<Buffer>,2>,2> banks;
 std::vector<uint64_t> merged;std::vector<Task> jobs;fs::path output;bool running=false,release=false;Clock::time_point deadline;
public:
#ifdef WINDOW_PURE_PL
 static constexpr const char* execution_backend="XRT_PURE_PL";static constexpr unsigned aie_tiles=0;
#else
 static constexpr const char* execution_backend="XRT_AIE";static constexpr unsigned aie_tiles=2;
#endif
 XrtWindowBackend(const xrt::device& d,const xrt::uuid& uuid,windowio::Dataset& s,xrt::graph* gr):source(s),graph(gr),merged(s.shape.output_words()){
#ifdef WINDOW_PURE_PL
  require(graph==nullptr,"pure PL must not create AIE graph");
#else
  require(graph!=nullptr,"AIE graph required");
#endif
  for(unsigned l=0;l<2;++l){kernels[l]=std::make_unique<Kernels>(d,uuid,l);
#ifdef WINDOW_PURE_PL
   multiply_kernels[l]=std::make_unique<xrt::kernel>(d,uuid,"ct_limb_diag:{ct_limb_diag_"+std::to_string(l+1)+"}",xrt::kernel::cu_access_mode::exclusive);
#endif
  }
  for(auto& bank:banks)for(unsigned l=0;l<2;++l)bank[l]=std::make_unique<Buffer>(d,*kernels[l],source.shape,multiply_kernels[l].get());
 }
 void configure(const std::vector<Task>& t,const fs::path& out,bool bounded){require(!running,"window configure while active");jobs=t;output=out;release=bounded;for(auto& bank:banks)for(auto& lane:bank)lane->baby=UINT32_MAX;}
 void prepare(unsigned i,unsigned bank,boexp::Frame& f,Clock::time_point epoch){const auto job=jobs.at(i);f.timed("baby_cache_load",-1,epoch,[&]{source.cache_baby(job.chunk);});
  for(unsigned l=0;l<2;++l){auto& b=*banks.at(bank)[l];bool fill=b.baby!=job.chunk;f.timed("weight_pack_baby_if_needed",l,epoch,[&]{source.pack_cached(job.group,job.chunk,l,2,b.in,source.input_words()/2,fill);});b.baby=job.chunk;}
  for(unsigned l=0;l<2;++l){auto& b=*banks[bank][l];std::vector<uint64_t> params;f.timed("parameter_pack",l,epoch,[&]{params=pack_parameters(b.shape);});f.timed("parameter_write",l,epoch,[&]{b.parameters.write(params.data(),params.size()*8,0);});f.timed("input_sync",l,epoch,[&]{b.input.sync(XCL_BO_SYNC_BO_TO_DEVICE);});f.timed("parameter_sync",l,epoch,[&]{b.parameters.sync(XCL_BO_SYNC_BO_TO_DEVICE);});f.timed("output_poison",l,epoch,[&]{std::fill_n(b.out,b.shape.output_words(),UINT64_MAX);});f.timed("output_poison_sync",l,epoch,[&]{b.output.sync(XCL_BO_SYNC_BO_TO_DEVICE);});}
 }
 void start(unsigned,unsigned bank){require(!running,"more than one active graph/CU invocation");running=true;deadline=Clock::now()+std::chrono::seconds(120);auto& lanes=banks.at(bank);for(auto& b:lanes)b->reducer.start();
#ifdef WINDOW_PURE_PL
  for(auto& b:lanes)b->multiply->start();
#else
  const auto frames=source.shape.frames()/2;require(frames&&frames<=INT32_MAX,"window graph frames");graph->run(int(frames));
#endif
  for(auto& b:lanes)b->reader.start();
 }
 void wait(unsigned,unsigned bank){for(auto& b:banks[bank])wait_for_run("reader",b->reader,deadline);for(auto& b:banks[bank])wait_for_run("reducer",b->reducer,deadline);
#ifdef WINDOW_PURE_PL
  for(auto& b:banks[bank])wait_for_run("PL_diagonal",*b->multiply,deadline);
#else
  graph->wait(remaining_time(deadline));
#endif
 }
 void complete(unsigned,unsigned,boexp::Frame& f,Clock::time_point epoch){f.timed("status",-1,epoch,[&]{for(unsigned l=0;l<2;++l){require(kernels[l]->reader.read_register(0x10)==0,"reader status");require(kernels[l]->reducer.read_register(0x10)==0,"reducer status");
#ifdef WINDOW_PURE_PL
   require(multiply_kernels[l]->read_register(0x10)==0,"PL diagonal status");
#endif
  }running=false;});}
 void finish(unsigned i,unsigned bank,boexp::Frame& f,Clock::time_point epoch){const auto job=jobs.at(i);f.timed("merge_poison",-1,epoch,[&]{std::fill(merged.begin(),merged.end(),UINT64_MAX);});for(unsigned l=0;l<2;++l){auto& b=*banks[bank][l];f.timed("output_sync",l,epoch,[&]{b.output.sync(XCL_BO_SYNC_BO_FROM_DEVICE);});f.timed("merge",l,epoch,[&]{boexp::merge_from(source.shape,l,b.out,b.shape.output_words(),merged);});}f.timed("verify",-1,epoch,[&]{source.verify(job.group,job.chunk,merged);});f.timed("input_retire",-1,epoch,[&]{source.retire_job(job.group,job.chunk,release);});}
 void save(unsigned i,unsigned){auto t=jobs.at(i);streamio::save_output_bulk(output/("group_"+std::to_string(t.group))/("chunk_"+std::to_string(t.chunk)+"_output.bin"),source.shape,merged);}
 void cancel()noexcept{for(auto& bank:banks)for(auto& b:bank)if(b){try{b->reader.abort();}catch(...){}try{b->reducer.abort();}catch(...){}if(b->multiply){try{b->multiply->abort();}catch(...){}}}
#ifndef WINDOW_PURE_PL
  if(graph){try{graph->reset();}catch(...){}}
#endif
  running=false;}
};
} }
#endif
