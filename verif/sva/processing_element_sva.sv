module proccessing_element_sva import accelerator_pkg::*; (
	input logic clk,
	input logic rst_n,
	input logic window_valid_in,
	input logic s1_valid,
	input logic s2_valid,
	input logic s3_valid,
	input accum_t mult_q [0:WINDOW_SIZE-1]
);

	// 1. Flexible Pipeline Integrity
	property p_valid_flow_to_s3;
		@(posedge clk) disable iff (!rst_n)
		window_valid_in |-> ##[1:$] s3_valid;
	endproperty
	
	assert_valid_flow: assert property (p_valid_flow_to_s3) 
		else $error("[SVA ERROR] Valid propagation failed: window_valid_in never reached s3_valid!");
	// 2. Backward Synchronization (Safety Check)
	property p_valid_sequence;
		@(posedge clk) disable iff (!rst_n)
		s2_valid |-> $past(s1_valid);
	endproperty

	assert_valid_sequence: assert property (p_valid_sequence)
		else $error("[SVA ERROR] Valid signal mismatch! s2_valid is high but s1_valid was LOW in the previous cycle!");

	// 3. Power Gating & Stability
	property p_mult_stable;
		@(posedge clk) disable iff (!rst_n)
		!window_valid_in |=> $stable(mult_q);
	endproperty

	assert_mult_stable: assert property (p_mult_stable) 
		else $error("[SVA ERROR] Multipliers toggling without valid input - Power waste detected!");

endmodule

bind processing_element proccessing_element_sva pe_sva_inst (
	.clk(clk),
	.rst_n(rst_n),
	.window_valid_in(window_valid_in),
	
	.s1_valid(s1_valid), 
	.s2_valid(s2_valid),
	.s3_valid(s3_valid),
	.mult_q(mult_q)
);