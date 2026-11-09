#pragma once
#include <cstdlib>
#include <cstring>
#include <stdexcept>
#include <cstddef>

namespace iotuning {
inline bool prefetch(){
    static const bool v=[](){const auto* p=std::getenv("V32_GA3_PREFETCH");
        if(!p||std::strcmp(p,"0")==0)return false;
        if(std::strcmp(p,"1")==0)return true;
        throw std::runtime_error("invalid V32_GA3_PREFETCH");}();return v;
}
inline size_t read_bytes(){
    static const size_t v=[](){const auto* p=std::getenv("V32_GA3_READ_MIB");
        if(!p||std::strcmp(p,"4")==0)return size_t(4*1024*1024);
        if(std::strcmp(p,"1")==0)return size_t(1024*1024);
        if(std::strcmp(p,"16")==0)return size_t(16*1024*1024);
        throw std::runtime_error("read size must be 1,4,16 MiB");}();return v;
}
}
