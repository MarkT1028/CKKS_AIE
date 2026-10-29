#pragma once
#include <adf.h>
void limb_mul(adf::input_buffer<int16>& left, adf::input_buffer<int16>& right, adf::output_buffer<int32>& partials);
