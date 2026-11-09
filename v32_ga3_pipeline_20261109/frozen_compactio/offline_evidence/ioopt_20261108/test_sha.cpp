#include "sealed_sha256.hpp"
#include "picosha2.h"
#include <iostream>
#include <random>

int main(){
    sealedsha::Engine engine;std::mt19937_64 random(0x56C0FFEE);
    for(size_t size:{size_t(0),size_t(1),size_t(55),size_t(56),size_t(63),size_t(64),size_t(65),size_t(448),size_t(184),size_t(3*1024*1024)}){
        std::vector<uint8_t> bytes(size);for(auto& x:bytes)x=uint8_t(random());
        const auto expected=picosha2::hash256_hex_string(bytes);
        for(size_t split:{size_t(0),size/2,size}){
            const auto* data=bytes.empty()?nullptr:bytes.data();
            const auto* second=data?data+split:nullptr;
            if(engine.hex(data,split,second,size-split)!=expected)throw std::runtime_error("EVP independent PicoSHA2 mismatch");
        }
    }
    std::cout<<"PASS_EVP_SHA256_INDEPENDENT_BOUNDARIES_AND_3MIB "<<engine.description()<<'\n';
}
