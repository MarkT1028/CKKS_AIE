#include "limb_mul.hpp"
#include <aie_api/aie.hpp>
// One frame: 4 limbs x 64 positions per input; 16 x 64 exact products out.
// AIE API source; not the HLS software model. Not yet compiled on this host.
void limb_mul(adf::input_buffer<int16>& left, adf::input_buffer<int16>& right,
              adf::output_buffer<int32>& partials) {
    const int16* a=left.data();
    const int16* b=right.data();
    int32* out=partials.data();
    for(unsigned r=0;r<4;++r)
        for(unsigned s=0;s<4;++s)
            for(unsigned j=0;j<64;j+=32) {
                auto av=aie::load_v<32>(a+r*64+j);
                auto bv=aie::load_v<32>(b+s*64+j);
                auto product=aie::mul(av,bv);
                // 0..32767 inputs -> 0..1073676289, exact in signed int32.
                aie::store_v(out+(r*4+s)*64+j,product.to_vector<int32>(0));
            }
}
