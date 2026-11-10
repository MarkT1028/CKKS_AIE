#pragma once
#include <dlfcn.h>
#include <array>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <stdexcept>
#include <string>
#include <vector>

// OpenSSL's documented opaque EVP API, loaded from the board's existing
// userspace library. No extra headers, package installation or kernel API.
// SHA profile is explicitly unsupported if this API is unavailable.
struct evp_md_ctx_st;
struct evp_md_st;
struct engine_st;
namespace finishsha {
class Engine {
    void* library=nullptr;
    using Context=::evp_md_ctx_st;
    using Digest=::evp_md_st;
    Context* (*context_new)()=nullptr;
    void (*context_free)(Context*)=nullptr;
    const Digest* (*sha256)()=nullptr;
    int (*initialize)(Context*,const Digest*,::engine_st*)=nullptr;
    int (*update)(Context*,const void*,size_t)=nullptr;
    int (*finish)(Context*,unsigned char*,unsigned int*)=nullptr;
    const char* (*version)(int)=nullptr;
    template<class Function> Function symbol(const char* name){
        void* address=::dlsym(library,name);
        if(!address)throw std::runtime_error(std::string("OpenSSL EVP symbol unavailable: ")+name);
        return reinterpret_cast<Function>(address);
    }
public:
    std::string library_name;
    Engine(){
        if(std::getenv("V32_GA3_DISABLE_CRYPTO"))throw std::runtime_error("SHA256 candidate explicitly disabled");
        for(const char* name:{"libcrypto.so.3","libcrypto.so.1.1"}){
            library=::dlopen(name,RTLD_NOW|RTLD_LOCAL);
            if(library){library_name=name;break;}
        }
        if(!library)throw std::runtime_error("SHA256 candidate unsupported: existing libcrypto.so.3/1.1 not found");
        try{
            context_new=symbol<decltype(context_new)>("EVP_MD_CTX_new");
            context_free=symbol<decltype(context_free)>("EVP_MD_CTX_free");
            sha256=symbol<decltype(sha256)>("EVP_sha256");
            initialize=symbol<decltype(initialize)>("EVP_DigestInit_ex");
            update=symbol<decltype(update)>("EVP_DigestUpdate");
            finish=symbol<decltype(finish)>("EVP_DigestFinal_ex");
            version=symbol<decltype(version)>("OpenSSL_version");
            if(hex(nullptr,0,nullptr,0)!="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855")
                throw std::runtime_error("OpenSSL SHA256 empty self-test failed");
            if(hex("a",1,"bc",2)!="ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")
                throw std::runtime_error("OpenSSL SHA256 incremental self-test failed");
        }catch(...){::dlclose(library);library=nullptr;throw;}
    }
    ~Engine(){if(library)::dlclose(library);}
    Engine(const Engine&)=delete;Engine& operator=(const Engine&)=delete;
    std::string description()const{return std::string(version(0))+" via "+library_name;}
    template<class Feed> std::string segments(const void* header,size_t header_bytes,Feed feed)const{
        Context* context=context_new();
        if(!context)throw std::runtime_error("EVP context allocation failed");
        std::array<unsigned char,32> output{};unsigned int length=0;
        bool ok=false;
        try{
            if(initialize(context,sha256(),nullptr)!=1)throw std::runtime_error("SHA init failed");
            auto add=[&](const void* data,size_t bytes){
                if(bytes&&(!data||update(context,data,bytes)!=1))throw std::runtime_error("SHA update failed");
            };
            add(header,header_bytes);feed(add);ok=finish(context,output.data(),&length)==1;
        }catch(...){context_free(context);throw;}
        context_free(context);
        if(!ok||length!=32)throw std::runtime_error("OpenSSL complete SHA256 failed");
        constexpr char digits[]="0123456789abcdef";std::string text(64,'0');
        for(size_t i=0;i<32;++i){text[2*i]=digits[output[i]>>4];text[2*i+1]=digits[output[i]&15];}
        return text;
    }
    std::string hex(const void* header,size_t header_bytes,const void* payload,size_t payload_bytes)const{
        return segments(header,header_bytes,[&](auto add){add(payload,payload_bytes);});
    }
};
template<class Input> std::vector<uint8_t> canonical_header(const Input& shape,size_t words){
    if(shape.parameters.size()!=shape.l||words!=size_t(shape.n)*shape.l*3)
        throw std::runtime_error("SHA256 canonical shape mismatch");
    std::vector<uint8_t> header={'C','K','K','S','M','A','C','1'};
    auto put=[&](uint64_t value,unsigned count){for(unsigned i=0;i<count;++i)header.push_back(uint8_t(value>>(8*i)));};
    for(unsigned value:std::array<unsigned,10>{1,2,shape.n,shape.l,shape.k,3,1,64,0,0})put(value,4);
    put(words,8);put(0,8);
    for(const auto& p:shape.parameters){put(p.q,8);put(p.mu_lo,8);put(p.mu_hi,8);}
    return header;
}
template<class Input> std::string output_digest(const Engine& engine,const Input& shape,const std::vector<uint64_t>& words){
    const auto header=canonical_header(shape,words.size());
    return engine.hex(header.data(),header.size(),words.data(),words.size()*sizeof(uint64_t));
}
// EXACT same canonical bytes: header, then each tower's left half followed by
// its right half. Never hash the whole left lane then the whole right lane.
template<class Input> std::string split_output_digest(const Engine& engine,const Input& shape,
        const uint64_t* left,const uint64_t* right,size_t lane_words){
    if(shape.n%2||!left||!right||lane_words!=size_t(shape.n/2)*shape.l*3)
        throw std::runtime_error("split SHA shape/pointer mismatch");
    const auto header=canonical_header(shape,shape.output_words());
    const size_t tower_words=size_t(shape.n/2)*3;
    return engine.segments(header.data(),header.size(),[&](auto add){
        for(unsigned t=0;t<shape.l;++t){
            add(left+t*tower_words,tower_words*8);
            add(right+t*tower_words,tower_words*8);
        }
    });
}
}
