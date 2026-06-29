import accelerator_pkg::*;

module accelerator_top (
	input  logic               clk,
	input  logic               rst_n,
	
	input  logic [PIXEL_W-1:0] input_bus,
	
	input  logic               pixel_valid_in, // High when input_bus holds valid image pixel
	input  logic               cfg_wr_en,      // High when input_bus holds configuration data
	
	output logic               pixel_out,      
	output logic               pixel_valid_out 
);


// Control to Memory Array routing
logic [BANK_ADDR_W-1:0] wr_addr;
logic [BANK_ADDR_W-1:0] rd_base_addr;
logic [1:0]             wr_bank_sel;
logic [1:0]             wr_row_sel;
logic [1:0]             horiz_offset;
logic [1:0]             vert_ptr;
logic                   wr_en;
logic                   window_valid;

// Control to Configuration Bank routing
logic [CFG_ADDR_W-1:0]  cfg_addr;

// Line Buffer to PE Data routing
window_t                window_out;
logic                   window_valid_out;

// Configuration to PE Data routing
kernel_weights_t        weights_out;
weight_t                bias_out;
accum_t                 threshold_out;


// INSTANTIATIONS
// CONTROL UNIT
wire rd_en;
control_unit u_control_unit (
	.clk         (clk           ),
	.rst_n       (rst_n         ),
	.cfg_wr_en   (cfg_wr_en     ),
	.pixel_valid (pixel_valid_in),
	.cfg_addr    (cfg_addr      ),
	.wr_addr     (wr_addr       ),
	.rd_base_addr(rd_base_addr  ),
	.wr_bank_sel (wr_bank_sel   ),
	.horiz_offset(horiz_offset  ),
	.wr_row_sel  (wr_row_sel    ),
	.vert_ptr    (vert_ptr      ),
	.wr_en       (wr_en         ),
	.window_valid(window_valid  ),
	.rd_en(rd_en)
);

// LINE BUFFER
line_buffer_top u_line_buffer (
	.clk             (clk             ),
	.rst_n           (rst_n           ),
	.pixel_in        (input_bus       ), // Shared data bus
	.wr_en           (wr_en           ),
	.wr_addr         (wr_addr         ),
	.wr_row_sel      (wr_row_sel      ),
	.wr_bank_sel     (wr_bank_sel     ),
	.rd_base_addr    (rd_base_addr    ),
	.horiz_offset    (horiz_offset    ),
	.vert_ptr        (vert_ptr        ),
	.rd_valid        (window_valid    ),
	.window_out      (window_out      ), // Extracted 3x3 window
	.window_valid_out(window_valid_out),
	.rd_en(rd_en)
);

// CONFIGURATION BANK
configuration_register_bank u_configuration_register_bank (
	.clk          (clk          ),
	.cfg_wr_en    (cfg_wr_en    ),
	.cfg_addr     (cfg_addr     ),
	.input_bus    (input_bus    ), // Shared data bus
	.weights_out  (weights_out  ),
	.bias_out     (bias_out     ),
	.threshold_out(threshold_out),
	.rst_n(rst_n)
);

// PROCESSING ELEMENT
processing_element u_processing_element (
	.clk            (clk             ),
	.rst_n          (rst_n           ),
	.window_valid_in(window_valid_out), // Sync flag from Line Buffer
	.pixels         (window_out      ), // 3x3 Window Data
	.weights        (weights_out     ), // Kernel Weights
	.bias           (bias_out        ), // Network Bias
	.threshold      (threshold_out   ), // Activation Threshold
	.pixel_out      (pixel_out       ), // Final calculated pixel
	.pixel_valid_out(pixel_valid_out ),
	.sum            (                )
);

endmodule