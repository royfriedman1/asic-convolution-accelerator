import accelerator_pkg::*;

module line_buffer_physical_memory_array (
	input  logic                   clk,
	
	input logic                    rd_en,
	
	// Write Path (From Write Steering Logic)
	input  pixel_t                 data_to_banks,           // Broadcasted pixel data
	input  logic [2:0][2:0]        bank_wr_en,              // 3x3 One-hot write enable matrix [Row][Bank]
	input  logic [BANK_ADDR_W-1:0] wr_addr,                 // Common write address for all banks
	
	// Read Path (From Read Address Logic)
	input  logic [BANK_ADDR_W-1:0] bank_rd_addr  [0:2],     // 3 parallel addresses for Banks 0, 1, 2
	
	// Output (To Re-ordering Logic)
	output pixel_t                 bank_data_out [0:2][0:2] // Matrix of read data [Row][Bank]
);

// 3x3 Bank Matrix
generate
	for (genvar r = 0; r < 3; r++) begin : row_gen
		for (genvar b = 0; b < 3; b++) begin : bank_gen
			
			logic bank_clk_en;
			assign bank_clk_en = bank_wr_en[r][b] | rd_en;
			
			logic bank_gated_clk;
			
			latch_based_icg u_bank_icg (
				.clk_in (clk           ),
				.enable (bank_clk_en   ),
				.clk_out(bank_gated_clk)
			);
			
			// Instantiate the single bank wrapper
			line_buffer_memory_bank_wrapper #(.ADDR_WIDTH(BANK_ADDR_W), .DATA_WIDTH(PIXEL_WIDTH)) u_bank (
				.clk     (bank_gated_clk     ),
				.wr_en   (bank_wr_en[r][b]   ), // Only the target bank receives a high wr_en based on the steering logic.
				.wr_addr (wr_addr            ),
				.data_in (data_to_banks      ),
				.rd_addr (bank_rd_addr[b]    ), // All rows (r) in the same column (b) share the same read address
				
				.data_out(bank_data_out[r][b])
			);
			
		end
	end
endgenerate

endmodule