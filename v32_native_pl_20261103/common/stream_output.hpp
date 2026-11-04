#pragma once
#include <cerrno>
namespace { namespace streamio {
inline void output_write(int fd,const void* data,size_t bytes){const auto* p=static_cast<const uint8_t*>(data);while(bytes){auto n=::write(fd,p,bytes);if(n<0&&errno==EINTR)continue;if(n<=0)throw std::runtime_error("bulk output write failed");p+=n;bytes-=size_t(n);}}
inline void save_output_bulk(const fs::path& path,const InputCase& shape,const std::vector<uint64_t>& words){
 require(words.size()==shape.output_words(),"bulk output length");Fd fd;fd.value=::open(path.c_str(),O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC,0600);require(fd.value>=0,"output exists or cannot create: "+path.string());std::vector<uint8_t> header;header.insert(header.end(),{'C','K','K','S','M','A','C','1'});
 auto put=[&](uint64_t x,unsigned n){for(unsigned j=0;j<n;++j)header.push_back(uint8_t(x>>(8*j)));};for(unsigned x:std::array<unsigned,10>{1,2,shape.n,shape.l,shape.k,3,1,64,0,0})put(x,4);put(words.size(),8);put(0,8);for(const auto& p:shape.parameters){put(p.q,8);put(p.mu_lo,8);put(p.mu_hi,8);}output_write(fd.value,header.data(),header.size());output_write(fd.value,words.data(),words.size()*8);int n=::close(fd.value);fd.value=-1;require(n==0,"output close failed");
} }
}
