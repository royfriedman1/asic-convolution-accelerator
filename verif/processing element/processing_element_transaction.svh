`ifndef PROCESSING_ELEMENT_TRANSACTION_SVH
`define PROCESSING_ELEMENT_TRANSACTION_SVH

import accelerator_pkg::*;

class processing_element_transaction;
	
	// Randomizable Input Data (from txt file)
	rand window_t          pixels;
	rand kernel_weights_t weights;
	rand pixel_t          bias;
	rand accum_t          threshold;
	bit                   valid;
	
	// expected output Storage (from txt file)
	accum_t               expected_sum;
	logic                 expected_pixel_out;
	
	// actual output from dut storage
	accum_t               actual_sum;
	logic                 actual_pixel_out;
	
	// Helper Functions
	function void display(string name = "PE_TR");
		$display("[%s] @%t: Valid=%b, Bias=%d, Thresh=%d, Sum=%d, Out=%b",
				name, $time, valid, bias, threshold, actual_sum, actual_pixel_out);
	endfunction
	
endclass

`endif