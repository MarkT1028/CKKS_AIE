#pragma once
#include <array>
#include <cstdint>
#include <iomanip>
#include <sstream>
#include <string>
#include <vector>

namespace ga0 {
constexpr unsigned Ring=131072, Towers=57, OutputCount=16, Groups=4, K=16;
constexpr unsigned N=8192, L=4, Blocks=(Towers+L-1)/L;
constexpr unsigned Tiles=Groups*Blocks*(Ring/N)*OutputCount;
constexpr uint64_t Words=uint64_t(Groups)*OutputCount*Ring*Towers*3;
constexpr unsigned tower_count(unsigned block) { return block+1==Blocks ? Towers-block*L : L; }
inline unsigned id(unsigned g,unsigned r,unsigned c,unsigned o) {
    return ((g*Blocks+r)*(Ring/N)+c)*OutputCount+o+1;
}
inline std::string name(char kind,unsigned a,unsigned b,unsigned c=0) {
    std::ostringstream out;
    out << "data/" << kind << '_' << std::setfill('0') << std::setw(2) << a
        << '_' << std::setw(2) << b << '_' << std::setw(2) << c << ".bin";
    return out.str();
}

class Transform {
    using Wide=unsigned __int128;
    uint64_t q;
    std::vector<uint64_t> roots, precon;
public:
    Transform(uint64_t modulus,uint64_t root) : q(modulus),roots(Ring),precon(Ring) {
        uint64_t power=1;
        unsigned rev=0;
        for(unsigned i=0;i<Ring;++i) {
            roots[rev]=power;
            precon[rev]=uint64_t((Wide(power)<<64)/q);
            power=uint64_t(Wide(power)*root%q);
            unsigned bit=Ring/2;
            while(bit && (rev&bit)){rev^=bit;bit>>=1;}
            rev^=bit;
        }
    }
    void forward(const int64_t* values,uint64_t* out) const {
        for(unsigned j=0;j<Ring;++j) {
            const int64_t residue=values[j]%int64_t(q);
            out[j]=residue<0 ? uint64_t(residue+int64_t(q)) : uint64_t(residue);
        }
        for(unsigned m=1,t=Ring/2;m<Ring;m*=2,t/=2) {
            for(unsigned i=0;i<m;++i) {
                const uint64_t w=roots[m+i], s=precon[m+i];
                for(unsigned j=2*i*t;j<(2*i+1)*t;++j) {
                    const uint64_t a=out[j], b=out[j+t];
                    uint64_t p=b*w-uint64_t((Wide(b)*s)>>64)*q;
                    if(p>=q)p-=q;
                    const uint64_t x=a+p;
                    out[j]=x>=q ? x-q : x;
                    out[j+t]=a>=p ? a-p : a+q-p;
                }
            }
        }
    }
};
}
