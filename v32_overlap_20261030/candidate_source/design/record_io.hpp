#pragma once
#include "ct_mac.hpp"

#include <array>
#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>
using namespace ctmac;
void check(bool ok,const std::string& why) {
    if(!ok) throw std::runtime_error(why);
}
uint64_t read_le(std::istream& f,unsigned bytes) {
    uint64_t v=0;
    for(unsigned i=0;i<bytes;++i) {
        int b=f.get(); check(b!=EOF,"truncated file");
        v|=uint64_t(static_cast<unsigned char>(b))<<(i*8);
    }
    return v;
}
void write_le(std::ostream& f,uint64_t v,unsigned bytes) {
    for(unsigned i=0;i<bytes;++i) f.put(char((v>>(8*i))&255));
    check(bool(f),"write failed");
}
struct Record {
    unsigned kind,n,l,k;
    std::vector<param_t> params;
    std::vector<word_t> words;
};
Record read_record(const std::string& path) {
    std::ifstream f(path,std::ios::binary);
    check(bool(f),"cannot open "+path);
    f.seekg(0,std::ios::end); auto file_size=f.tellg(); f.seekg(0);
    char magic[8]; f.read(magic,8);
    check(f.gcount()==8 && std::string(magic,8)=="CKKSMAC1","bad magic");
    std::array<uint32_t,10> h;
    for(auto& x:h) x=uint32_t(read_le(f,4));
    Record r; r.kind=h[1]; r.n=h[2]; r.l=h[3]; r.k=h[4];
    check(h[0]==1 && (r.kind==1 || r.kind==2) &&
          h[5]==(r.kind==1?4:3) && h[6]==1 && h[7]==64 &&
          h[8]==0 && h[9]==0,"bad header");
    check(dimensions(r.n,r.l,r.k)==OK,"dimensions unsupported by first HLS version");
    uint64_t count=read_le(f,8);
    uint64_t expected=uint64_t(r.n)*r.l*(r.kind==1?4*r.k:3);
    check(read_le(f,8)==0 && count==expected,"bad payload count");
    check(uint64_t(file_size)==64+24ULL*r.l+8*count,"file length mismatch");
    for(unsigned t=0;t<r.l;++t) {
        param_t p=0;
        for(unsigned j=0;j<3;++j) p.range(64*j+63,64*j)=read_le(f,8);
        check(valid_parameter(p),"bad RNS parameter");
        r.params.push_back(p);
    }
    for(uint64_t j=0;j<count;++j) {
        word_t v=read_le(f,8);
        unsigned t=(j/(r.n*(r.kind==1?4:3)))%r.l;
        word_t q=r.params[t].range(63,0);
        check(v<q,"noncanonical input residue");
        r.words.push_back(v);
    }
    return r;
}
void write_output(const std::string& path,const Record& in,const std::vector<word_t>& words) {
    std::ofstream f(path,std::ios::binary);
    check(bool(f),"cannot write "+path);
    f.write("CKKSMAC1",8);
    for(uint32_t v:std::array<uint32_t,10>{1,2,in.n,in.l,in.k,3,1,64,0,0})
        write_le(f,v,4);
    write_le(f,words.size(),8); write_le(f,0,8);
    for(auto p:in.params)
        for(unsigned j=0;j<3;++j) {
            word_t v=p.range(64*j+63,64*j);
            write_le(f,v.to_uint64(),8);
        }
    for(auto v:words) write_le(f,v.to_uint64(),8);
}
