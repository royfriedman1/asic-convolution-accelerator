import accelerator_pkg::*;
import accelerator_tb_pkg::*;

module accelerator_tb;

	logic clk;
	logic rst_n;

	// Clock generation: 10ns period (100MHz)
	initial begin
		clk = 0;
		forever #5 clk = ~clk;
	end


	initial begin
		rst_n = 0;
		#100 ;
		#20 rst_n = 1; 
	end

	initial begin
		$fsdbDumpfile("novas.fsdb");
		$fsdbDumpvars(0, accelerator_tb, "+all");
	end

	accelerator_if acc_if (
		.clk  (clk),
		.rst_n(rst_n)
	);

	accelerator_top dut (
		.clk            (clk),
		.rst_n          (rst_n),
		.input_bus      (acc_if.input_bus),      
		.pixel_valid_in (acc_if.pixel_valid_in), 
		.cfg_wr_en      (acc_if.cfg_wr_en),      
		.pixel_out      (acc_if.pixel_out),      
		.pixel_valid_out(acc_if.pixel_valid_out) 
	);

	// Verification environment handle
	accelerator_env env;

	initial begin
		wait(acc_if.rst_n === 1'b1);
		# 20
		$display("[Top] @%0t: Reset released. Starting Verification Environment:", $time);
		
		env = new(acc_if);
		
		env.run(); 
		
		$display("[Top] @%0t: Simulation finished completely.", $time);
		$finish;
	end

	initial begin
		$dumpfile("dump.vcd");
		$dumpvars(0, accelerator_tb);
	end

endmodule