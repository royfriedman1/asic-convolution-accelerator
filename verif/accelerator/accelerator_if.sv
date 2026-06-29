interface accelerator_if (
	input logic clk,
	input logic rst_n
);

import accelerator_pkg::*;

// --- Bus Signals ---
logic [PIXEL_W-1:0] input_bus;
logic               pixel_valid_in;
logic               cfg_wr_en;
logic               pixel_out;
logic               pixel_valid_out;

initial begin
	input_bus      = '0;
	pixel_valid_in = 1'b0;
	cfg_wr_en      = 1'b0;
end

// Clocking Blocks

// driver
clocking drv_cb @(posedge clk);
	default input #1ns output #1ns;
	output input_bus, pixel_valid_in, cfg_wr_en;
	input  pixel_out, pixel_valid_out;
endclocking

// Monitor
clocking mon_cb @(posedge clk);
	default input #1ns output #1ns;
	input input_bus, pixel_valid_in, cfg_wr_en, pixel_out, pixel_valid_out;
endclocking

// Modports:

modport dut_mp (
	input  clk,
	       rst_n,
	       input_bus,
	       pixel_valid_in,
	       cfg_wr_en,
	output pixel_out,
	       pixel_valid_out
);

modport mon_mp (
	clocking mon_cb,
	input    rst_n
);

modport drv_mp (
	clocking drv_cb,
	input    rst_n
);

task manual_reset();
	force rst_n = 1'b0; 
	repeat(10) @(posedge clk);
	force rst_n = 1'b1;
	release rst_n; 
endtask

endinterface