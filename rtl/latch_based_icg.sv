module latch_based_icg (
	input logic clk_in,
	input       enable, // data in
	output      clk_out // data out
);

logic enable_latch;

always_latch begin
	if (!clk_in) begin
		enable_latch <= enable;
	end
end

assign clk_out = clk_in & enable_latch;

endmodule