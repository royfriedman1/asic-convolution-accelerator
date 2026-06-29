`timescale 1ns/1ps

import accelerator_pkg::*;
import accelerator_tb_pkg::*;

module accelerator_tb;
// --- Power Connections for Gate Level Simulation ---
// Most TSMC 28nm netlists use these names. 
// 'force' ensures the power is distributed to all sub-modules.


	logic clk;
	logic rst_n;

	// Clock generation: 10ns period (100MHz)
	initial begin
		clk = 0;
		forever #5 clk = ~clk;
	end

	// Reset sequence: Includes an initial reset and a short glitch test
	initial begin
		rst_n = 0;
		#100 ;
		#20 rst_n = 1; 
	end

	initial begin
		$fsdbDumpfile("novas.fsdb");
		$fsdbDumpvars(0, accelerator_tb, "+all");
	end
	// Virtual interface: The physical wires connecting the Testbench to the DUT
	accelerator_if acc_if (
		.clk  (clk),
		.rst_n(rst_n)
	);

	// Device Under Test (DUT): Mapping the hardware ports to the interface signals
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
		// Wait for the reset sequence to finish before injecting stimulus
		#50;
		$display("[Top] @%0t: Reset released. Starting Verification Environment...", $time);
		
		// Build phase: Instantiate the environment and pass the interface
		env = new(acc_if);
		
		// Run phase: Execute the test (This is a blocking call that runs until completion)
		env.run(); 
		
		// Cleanup phase: Simulation ends when env.run() completes
		$display("[Top] @%0t: Simulation finished completely.", $time);
		$finish;
	end

	// Waveform dumping: Generates a VCD file for GTKWave/DVE debugging
	initial begin
		$dumpfile("dump.vcd");
		$dumpvars(0, accelerator_tb);
	end

endmodule