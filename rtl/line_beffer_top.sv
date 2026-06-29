import accelerator_pkg::*;

module line_buffer_top (
	// System Signals
	input  logic                   clk,
	input  logic                   rst_n,
	
	// Data Input Path
	input  pixel_t                 pixel_in,
	
	// Write Control Interface (From Global Control Unit)
	input  logic                   wr_en,
	input  logic [BANK_ADDR_W-1:0] wr_addr,
	input  logic [1:0]             wr_row_sel,
	input  logic [1:0]             wr_bank_sel,
	
	// Read Control Interface (From Global Control Unit)
	input  logic [BANK_ADDR_W-1:0] rd_base_addr,
	input  logic [1:0]             horiz_offset,
	input  logic [1:0]             vert_ptr,
	input  logic                   rd_valid,
	input logic                    rd_en,
	
	// Window Output Path 
	output window_t                window_out,
	output logic                   window_valid_out
);

// Internal Interconnects
logic [2:0][2:0]        bank_wr_en;
pixel_t                 data_to_banks;
logic [BANK_ADDR_W-1:0] bank_rd_addr [0:2];
pixel_t                 bank_data_out [0:2][0:2];

// Pipeline Registers (Latency Compensation)
// Memory read latency is 1 cycle. Therefore, control signals required by the
// reordering logic must be delayed by 1 cycle to maintain pipeline alignment.
logic [1:0]             horiz_offset_d1;
logic [1:0]             vert_ptr_d1;

// WRITE STEERING LOGIC (Demux / Broadcast)
line_buffer_write_steering_logic u_steering (
	.pixel_in     (pixel_in     ),
	.wr_en        (wr_en        ),
	.wr_row_sel   (wr_row_sel   ),
	.wr_bank_sel  (wr_bank_sel  ),
	.data_to_banks(data_to_banks),
	.bank_wr_en   (bank_wr_en   )
);

// READ ADDRESS LOGIC (Window Expansion)
line_buffer_read_address_logic u_addr_exp (
	.rd_base_addr(rd_base_addr),
	.horiz_offset(horiz_offset),
	.bank_rd_addr(bank_rd_addr)
);

// PHYSICAL MEMORY ARRAY (3x3 SRAM/Register Banks)
line_buffer_physical_memory_array u_mem_array (
	.clk          (clk          ),
	.rd_en     (rd_en        ),
	.data_to_banks(data_to_banks),
	.bank_wr_en   (bank_wr_en   ),
	.wr_addr      (wr_addr      ),
	.bank_rd_addr (bank_rd_addr ),
	.bank_data_out(bank_data_out)
);

// PIPELINE ALIGNMENT STAGE
always_ff @(posedge clk or negedge rst_n) begin
	if (!rst_n) begin
		horiz_offset_d1  <= '0;
		vert_ptr_d1      <= '0;
		window_valid_out <= 1'b0;
	end else begin
		horiz_offset_d1  <= horiz_offset;
		vert_ptr_d1      <= vert_ptr;
		window_valid_out <= rd_valid;
	end
end

// RE-ORDERING LOGIC (2D Barrel Shifter / Alignment MUXs)
line_buffer_reordering_logic u_reorder (
	.horiz_offset(horiz_offset_d1), // Fed with Latency compensated signal
	.vert_ptr    (vert_ptr_d1    ), // Fed with Latency compensated signal
	.bank_data   (bank_data_out  ),
	.window_out  (window_out     )
);

endmodule