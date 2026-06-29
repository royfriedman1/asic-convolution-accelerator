interface processing_element_if (
	input logic clk,
	input logic rst_n
);

import accelerator_pkg::*;

// input wires
logic            window_valid_in;
window_t         pixels;
kernel_weights_t weights;
pixel_t          bias;
accum_t          threshold;

//output wires
accum_t          sum;
logic            pixel_out;
logic            pixel_valid_out;

//clocking block
clocking cb @(posedge clk);
	default input #1ns output #1ns;
	output window_valid_in, pixels, weights, bias, threshold;
	input  sum, pixel_out, pixel_valid_out;
endclocking

// Modports
modport DRV (
	clocking cb,
	input    clk,
	         rst_n
);
modport MON (
	clocking cb,
	input    window_valid_in,
	         pixels,
	         weights,
	         bias,
	         threshold,
	         clk,
	         rst_n
);

endinterface