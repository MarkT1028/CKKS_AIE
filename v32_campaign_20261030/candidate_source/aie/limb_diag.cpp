#include <adf.h>
#include <aie_api/aie.hpp>
template<unsigned D> static inline void diagonal(const int16* a,const int16* b,uint32* out) {
    for(unsigned j=0;j<64;j+=32) chess_prepare_for_pipelining chess_loop_range(2,2) {
        aie::accum<acc64,32> s=aie::zeros<acc64,32>();
        if(D>=0 && D-0<4) {
            auto av=aie::load_v<32>(a+0*64+j);
            auto bv=aie::load_v<32>(b+(D-0)*64+j);
            s=aie::mac(s,av,bv);
        }
        if(D>=1 && D-1<4) {
            auto av=aie::load_v<32>(a+1*64+j);
            auto bv=aie::load_v<32>(b+(D-1)*64+j);
            s=aie::mac(s,av,bv);
        }
        if(D>=2 && D-2<4) {
            auto av=aie::load_v<32>(a+2*64+j);
            auto bv=aie::load_v<32>(b+(D-2)*64+j);
            s=aie::mac(s,av,bv);
        }
        if(D>=3 && D-3<4) {
            auto av=aie::load_v<32>(a+3*64+j);
            auto bv=aie::load_v<32>(b+(D-3)*64+j);
            s=aie::mac(s,av,bv);
        }
        aie::store_v(out+D*64+j,s.to_vector<uint32>(0));
    }
}
void limb_diag(adf::input_buffer<int16>& left,adf::input_buffer<int16>& right,adf::output_buffer<uint32>& output) {
    const int16* a=left.data();const int16* b=right.data();uint32* out=output.data();
    diagonal<0>(a,b,out);
    diagonal<1>(a,b,out);
    diagonal<2>(a,b,out);
    diagonal<3>(a,b,out);
    diagonal<4>(a,b,out);
    diagonal<5>(a,b,out);
    diagonal<6>(a,b,out);
}
