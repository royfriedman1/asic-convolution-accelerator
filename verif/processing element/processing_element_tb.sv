import accelerator_pkg::*;
import tb_pkg::*;

module tb_top;

logic clk;
logic rst_n;

initial begin
	clk = 0;
	forever #5 clk = ~clk;
end

initial begin
	rst_n = 0;
	#20 rst_n = 1; 
	#5 rst_n = 0;
	#20 rst_n = 1; 
end

// 2. Interface Instance: The "wiring harness" connecting TB to RTL
processing_element_if pe_if (
	.clk  (clk  ),
	.rst_n(rst_n)
);

// 3. DUT Instantiation: The physical ASIC component under test
processing_element dut (
	.clk            (pe_if.clk            ),
	.rst_n          (pe_if.rst_n          ),
	.window_valid_in(pe_if.window_valid_in),
	.pixels         (pe_if.pixels         ),
	.weights        (pe_if.weights        ),
	.bias           (pe_if.bias           ),
	.threshold      (pe_if.threshold      ),
	
	.sum            (pe_if.sum            ),
	.pixel_out      (pe_if.pixel_out      ),
	.pixel_valid_out(pe_if.pixel_valid_out)
);

// 4. Testbench Environment handle
processing_element_env env;

initial begin
	@(posedge rst_n);
	$display("[Top] @%t: Reset released. Starting Verification Environment:", $time);
	
	env = new(pe_if);
	
	env.run();
	
	#1000000;
	
	env.scb.report();
	
	$display("[Top] @%t: Simulation finished", $time);
	$finish;
end

endmodule