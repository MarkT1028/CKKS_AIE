#define CKKSMAC_PARSER_ONLY
#define FULL_HS4_BACKEND_ONLY
#include <variants/v32_native_pl_2_pipe/host/bo_host.cpp>
#undef FULL_HS4_BACKEND_ONLY
#include "../common/sealed_sha256.hpp"
#include "../common/source.hpp"
#include <common/stream_output.hpp>
#include "mock_xrt.hpp"
#include "../host/backend.hpp"

using finishopt::Window;
static std::vector<uint64_t> gold(const Window& w,unsigned group){
    const auto& s=w.shape;const auto& a=*w.weights[group];const auto& b=w.baby;std::vector<uint64_t> out(s.output_words());
    for(unsigned t=0;t<s.l;++t)for(unsigned j=0;j<s.n;++j){
        U128 z[3]{};for(unsigned k=0;k<s.k;++k){size_t i=((size_t(k)*s.l+t)*s.n+j)*2;
            z[0]+=U128(a[i])*b[i];z[1]+=U128(a[i])*b[i+1]+U128(a[i+1])*b[i];z[2]+=U128(a[i+1])*b[i+1];}
        for(unsigned c=0;c<3;++c)out[(size_t(t)*s.n+j)*3+c]=uint64_t(z[c]%s.parameters[t].q);
    }return out;
}
static void fill(Window& w,unsigned block,unsigned ct,unsigned l,const sealedsha::Engine& reference,const Window* share=nullptr){
    require(!w.active,"test refuses active context overwrite");w.shape.n=128;w.shape.l=l;w.shape.k=16;w.shape.parameters.clear();
    for(unsigned t=0;t<l;++t){const uint64_t q=(1ULL<<51)-129-t*2;const U128 mu=(~U128(0))/q;w.shape.parameters.push_back({q,uint64_t(mu),uint64_t(mu>>64)});}
    w.tower=block*16;w.coefficient=0;w.ct=ct;w.baby_key=std::to_string(block)+":b:"+std::to_string(ct);size_t size=size_t(w.shape.n)*l*w.shape.k*2;
    w.baby.resize(size);for(size_t j=0;j<size;++j)w.baby[j]=(1ULL<<50)+(j+ct*19+block*11)%193;
    for(unsigned g=0;g<4;++g){
        w.weight_keys[g]=std::to_string(block)+":a:"+std::to_string(g);
        if(share)w.weights[g]=share->weights[g];
        else{auto p=std::make_shared<std::vector<uint64_t>>(size);for(size_t j=0;j<size;++j)(*p)[j]=(1ULL<<50)+(j+g*13+block*7)%181;w.weights[g]=p;}
        w.expected[g]=sealedsha::output_digest(reference,w.shape,gold(w,g));
    }
}
int main(int argc,char**argv){try{
    require(argc==2,"test needs unique output root");const fs::path root=argv[1];require(!fs::exists(root),"test output root already exists");fs::create_directories(root);
    finishsha::Engine engine;sealedsha::Engine reference;unsigned scenarios=0;
    for(const auto& profile:{std::string("merge1"),std::string("direct1"),std::string("direct2")})for(bool ascending:{false,true}){
        Window a,b;fill(a,0,0,16,reference);fill(b,0,1,16,reference,&a);InputCase maximum=a.shape;
        finishopt::Backend backend({}, {},maximum,engine);boexp::Worker worker;
        const bool batched=profile=="direct2";const auto base=root/(profile+(ascending?"_asc":"_desc"));
        auto one=[&](std::vector<Window*> windows,unsigned new_weights,const fs::path& output,bool save){
            for(auto* w:windows)w->begin();backend.configure(windows,ascending,profile!="merge1",output,true);
            const auto replay=boexp::run_finish_overlap(backend,windows.size()*4,worker,save);
            require(replay.frames.size()==windows.size()*4,"task coverage");uint64_t copies=0;
            for(unsigned s=0;s<windows.size();++s){
                auto& w=*windows[s];w.end();size_t bytes=w.baby.size()*8;const unsigned count=1+(s==0?new_weights:0);
                require(backend.copied_bytes(s)==count*bytes&&backend.synced_bytes(s)==count*bytes&&backend.cache_hits(s)==8-count,"per-window BO copy/sync/hit ledger");copies+=backend.copied_bytes(s);
                if(save)for(unsigned g=0;g<4;++g){
                    const auto path=output/("r"+std::to_string(w.tower)+"_c0_o"+std::to_string(w.ct))/("group_"+std::to_string(g))/"chunk_0_output.bin";
                    windowio::Record record(path,2);require(record.read_canonical()==gold(w,g),"streamed export canonical bytes differ");
                    std::ifstream hash(path.string()+".sha256");std::string digest;std::getline(hash,digest);require(digest==w.expected[g],"export digest differs");
                }
            }return copies;
        };
        if(batched)one({&a,&b},4,base/"first",true);
        else{one({&a},4,base/"first_a",true);one({&b},0,base/"first_b",true);}
        fill(a,0,2,16,reference);fill(b,0,3,16,reference,&a);
        if(batched)one({&a,&b},0,base/"next",false);else{one({&a},0,base/"next_a",false);one({&b},0,base/"next_b",false);}
        fill(a,1,14,5,reference);fill(b,1,15,5,reference,&a);
        if(batched)one({&a,&b},4,base/"short",true);else{one({&a},4,base/"short_a",true);one({&b},0,base/"short_b",true);}
        require(backend.hashed_outputs()==24,"all independent outputs verified");worker.close();++scenarios;
    }
    for(bool corrupt_input:{false,true}){
        Window a;fill(a,0,0,16,reference);finishopt::Backend backend({}, {},a.shape,engine);boexp::Worker worker;a.begin();backend.configure({&a},false,true,root/"unused",false);
        xrt::corrupt_input_sync=corrupt_input;xrt::corrupt_output=!corrupt_input;bool rejected=false;
        try{boexp::run_finish_overlap(backend,4,worker,false);}catch(const std::exception&){rejected=true;}
        xrt::corrupt_input_sync=xrt::corrupt_output=false;require(rejected,"corrupt input/output falsely verified");
    }
    {
        Window a,b;fill(a,0,0,16,reference);fill(b,1,1,16,reference);finishopt::Backend backend({}, {},a.shape,engine);a.begin();b.begin();bool rejected=false;
        try{backend.configure({&a,&b},false,true,root/"unused",false);}catch(...){rejected=true;}require(rejected,"cross-block batch accepted");
    }
    std::cout<<"PASS_FINISH_BACKEND profiles_orders="<<scenarios<<" separate_host_device async_readers first_uploads cross_window_reuse L16_to_L5 full_SHA streamed_export corruption_rejection=1 software_only=1\n";return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
