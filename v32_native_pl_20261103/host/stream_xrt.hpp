#pragma once
#ifndef CKKSMAC_PARSER_ONLY
namespace { namespace streaming {
struct StreamBuffers {
 xrt::bo input,output,parameters;xrt::run reader,reducer;uint64_t* mapped_input=nullptr,*mapped_output=nullptr;InputCase lane_shape;
 StreamBuffers(const xrt::device& device,Kernels& kernel,const InputCase& full):input(device,size_t(full.n)*full.l*full.k*4*8/2,kernel.reader.group_id(0)),output(device,full.output_words()*8/2,kernel.reducer.group_id(1)),parameters(device,full.l*32,kernel.reducer.group_id(2)),reader(kernel.reader),reducer(kernel.reducer){
  lane_shape.n=full.n/2;lane_shape.l=full.l;lane_shape.k=full.k;lane_shape.parameters=full.parameters;mapped_input=input.map<uint64_t*>();mapped_output=output.map<uint64_t*>();require(mapped_input&&mapped_output,"stream BO map");reader.set_arg(0,input);reader.set_arg(3,lane_shape.n);reader.set_arg(4,lane_shape.l);reader.set_arg(5,lane_shape.k);reducer.set_arg(1,output);reducer.set_arg(2,parameters);reducer.set_arg(3,lane_shape.n);reducer.set_arg(4,lane_shape.l);reducer.set_arg(5,lane_shape.k);
 }
};
class XrtStreamBackend {
 streamio::Dataset& source;xrt::graph& graph;unsigned group=0;fs::path output_dir;std::array<std::unique_ptr<Kernels>,2> kernels;std::array<std::array<std::unique_ptr<StreamBuffers>,2>,2> banks;std::vector<uint64_t> merged;Clock::time_point deadline;bool running=false;
public:
 static constexpr const char* execution_backend="XRT_AIE";
 XrtStreamBackend(const xrt::device& device,const xrt::uuid& uuid,xrt::graph& gr,streamio::Dataset& data):source(data),graph(gr),merged(data.shape.output_words()){
  for(unsigned l=0;l<2;++l)kernels[l]=std::make_unique<Kernels>(device,uuid,l);for(unsigned b=0;b<2;++b)for(unsigned l=0;l<2;++l)banks[b][l]=std::make_unique<StreamBuffers>(device,*kernels[l],source.shape);
 }
 void select_group(unsigned g,const fs::path& output){require(g<6&&!running,"stream group transition while running");group=g;output_dir=output;}
 void prepare(unsigned i,unsigned bank,boexp::Frame& frame,Clock::time_point epoch){auto& lanes=banks.at(bank);
  for(unsigned l=0;l<2;++l)frame.timed("pack_A_check_shared_B",l,epoch,[&]{source.pack(group,i,l,2,lanes[l]->mapped_input,source.input_words()/2);});
  for(unsigned l=0;l<2;++l){auto& b=*lanes[l];std::vector<uint64_t> packed;frame.timed("parameter_pack",l,epoch,[&]{packed=pack_parameters(b.lane_shape);});frame.timed("parameter_write",l,epoch,[&]{b.parameters.write(packed.data(),packed.size()*8,0);});frame.timed("input_sync",l,epoch,[&]{b.input.sync(XCL_BO_SYNC_BO_TO_DEVICE);});frame.timed("parameter_sync",l,epoch,[&]{b.parameters.sync(XCL_BO_SYNC_BO_TO_DEVICE);});frame.timed("output_poison",l,epoch,[&]{std::fill_n(b.mapped_output,b.lane_shape.output_words(),UINT64_MAX);});frame.timed("output_poison_sync",l,epoch,[&]{b.output.sync(XCL_BO_SYNC_BO_TO_DEVICE);});}
 }
 void start(unsigned,unsigned bank){require(!running,"more than one active graph");running=true;deadline=Clock::now()+std::chrono::seconds(120);auto& lanes=banks.at(bank);for(auto& b:lanes)b->reducer.start();auto frames=source.shape.frames()/2;require(frames&&frames<=INT32_MAX,"stream frame count");graph.run(int(frames));for(auto& b:lanes)b->reader.start();}
 void wait(unsigned,unsigned bank){for(auto& b:banks.at(bank))wait_for_run("reader",b->reader,deadline);for(auto& b:banks.at(bank))wait_for_run("reducer",b->reducer,deadline);graph.wait(remaining_time(deadline));}
 void complete(unsigned,unsigned,boexp::Frame& frame,Clock::time_point epoch){frame.timed("status",-1,epoch,[&]{for(auto& k:kernels){require(k->reader.read_register(0x10)==0,"stream reader status");require(k->reducer.read_register(0x10)==0,"stream reducer status");}running=false;});}
 void finish(unsigned i,unsigned bank,boexp::Frame& frame,Clock::time_point epoch){frame.timed("merge_poison",-1,epoch,[&]{std::fill(merged.begin(),merged.end(),UINT64_MAX);});for(unsigned l=0;l<2;++l){auto& b=*banks.at(bank)[l];frame.timed("output_sync",l,epoch,[&]{b.output.sync(XCL_BO_SYNC_BO_FROM_DEVICE);});frame.timed("merge",l,epoch,[&]{boexp::merge_from(source.shape,l,b.mapped_output,b.lane_shape.output_words(),merged);});}frame.timed("verify",-1,epoch,[&]{source.verify(group,i,merged);});}
 void save(unsigned i,unsigned){streamio::save_output_bulk(output_dir/("chunk_"+std::to_string(i)+"_output.bin"),source.shape,merged);}
 void cancel()noexcept{for(auto& bank:banks)for(auto& b:bank)if(b){try{b->reader.abort();}catch(...){}try{b->reducer.abort();}catch(...){}}try{graph.reset();}catch(...){}running=false;}
};
} }
#endif
