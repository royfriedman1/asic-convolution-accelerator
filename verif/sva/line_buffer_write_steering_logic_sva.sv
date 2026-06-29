import accelerator_pkg::*;

module line_buffer_write_steering_logic_sva (
	input logic clk,
	input logic rst_n,
	input logic wr_en,
	input logic [2:0][2:0] bank_wr_en
);

	// Assert: No Overlap Write
	property p_no_overlap_write;
		@(posedge clk) disable iff (!rst_n)
		wr_en |-> ($countones(bank_wr_en) == 1);
	endproperty

	assert_no_overlap: assert property (p_no_overlap_write)
		else $error("[SVA ERROR] Multiple MEM banks selected simultaneously");

	// Assert: No Write When Disabled
	property p_no_write_when_disabled;
		@(posedge clk) disable iff (!rst_n)
		!wr_en |-> ($countones(bank_wr_en) == 0);
	endproperty

	assert_safe_idle: assert property (p_no_write_when_disabled)
		else $error("[SVA ERROR] A bank is enabled while global wr_en is low");

endmodule

bind line_buffer_top line_buffer_write_steering_logic_sva sva_steering_inst (
	.clk        (clk),
	.rst_n      (rst_n),
	.wr_en      (wr_en),
	.bank_wr_en (bank_wr_en)
);