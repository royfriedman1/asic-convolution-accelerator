`ifndef PROCESSING_ELEMENT_COVERAGE_SVH
`define PROCESSING_ELEMENT_COVERAGE_SVH

class processing_element_coverage;

	processing_element_transaction tr;

	covergroup pe_cg;
		option.per_instance = 1;

		// Coverpoints

		// Pixel 0 OR 1
		cp_pixel_out: coverpoint tr.actual_pixel_out {
			bins out_0 = {0};
			bins out_1 = {1};
		}

		// Multiplications Sums
		cp_sum: coverpoint tr.actual_sum {
			bins sum_zero = {0};
			bins sum_low  = {[1 : 'h0FFFF]};
			bins sum_high = {['h10000 : 'hFFFFF]};
		}

		// Threshold
		cp_threshold: coverpoint tr.threshold {
			bins thresh_zero = {0};
			bins thresh_mid  = {[1 : 'hEFFFF]};
			bins thresh_max  = {'hFFFFF};
		}

		// Cross Coverage

		cr_sum_vs_out: cross cp_sum, cp_pixel_out {
			
			ignore_bins impossible_zero_sum_with_out_1 = 
				binsof(cp_sum.sum_zero) && binsof(cp_pixel_out.out_1);
		}

	endgroup

	function new();
		pe_cg = new();
	endfunction

	function void sample(processing_element_transaction t);
		this.tr = t;
		pe_cg.sample();
	endfunction

endclass

`endif