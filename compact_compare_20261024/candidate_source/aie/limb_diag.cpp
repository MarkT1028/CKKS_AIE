#include <adf.h>
#include <aie_api/aie.hpp>
// Seven exact convolution diagonals replace sixteen separate limb products.
// Maximum diagonal is 4*32767^2 = 4,294,705,156: uint32, NOT signed int32.
void limb_diag(adf::input_buffer<int16>& left,adf::input_buffer<int16>& right,
               adf::output_buffer<uint32>& diagonals) {
    const int16* a=left.data();const int16* b=right.data();uint32* out=diagonals.data();
    for(unsigned d=0;d<7;++d) {
        for(unsigned j=0;j<64;j+=32) {
            aie::accum<acc64,32> sum=aie::zeros<acc64,32>();
            for(unsigned r=0;r<4;++r) {
                if(d>=r && d-r<4) {
                    auto av=aie::load_v<32>(a+r*64+j);
                    auto bv=aie::load_v<32>(b+(d-r)*64+j);
                    sum=aie::mac(sum,av,bv);
                }
            }
            aie::store_v(out+d*64+j,sum.to_vector<uint32>(0));
        }
    }
}
