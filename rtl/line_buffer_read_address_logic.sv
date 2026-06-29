import accelerator_pkg::*;

module line_buffer_read_address_logic (
	input  logic [BANK_ADDR_W-1:0] rd_base_addr,      // Base address (col / 3)
	input  logic [1:0]             horiz_offset,      // Window start position (col % 3)
	
	output logic [BANK_ADDR_W-1:0] bank_rd_addr [0:2] // Independent read addresses for Banks 0, 1, 2
);

// Resource Sharing
logic [BANK_ADDR_W-1:0] rd_base_addr_next;
assign rd_base_addr_next = rd_base_addr + 1'b1;

// Address Expansion Logic: Maps the base address to the 3 physical banks.
always_comb begin
	bank_rd_addr[0] = rd_base_addr;
	bank_rd_addr[1] = rd_base_addr;
	bank_rd_addr[2] = rd_base_addr;
	
	unique case (horiz_offset)
		
		// 1. Window starts at Bank 0 (Col 0, 3, 6...)
		// Physical Window: [Bank0@N, Bank1@N, Bank2@N]
		2'd0: begin
			/* No overrides needed */
		end
		
		// 2. Window starts at Bank 1 (e.g., Col 1, 4, 7...)
		// Physical Window: [Bank1@N, Bank2@N, Bank0@N+1] 
		2'd1: begin
			bank_rd_addr[0] = rd_base_addr_next; // Bank 0 wraps around to the next line to fetch the 3rd pixel.
		end
		
		// 3. Window starts at Bank 2 (e.g., Col 2, 5, 8...)
		// Physical Window: [Bank2@N, Bank0@N+1, Bank1@N+1]
		2'd2: begin
			// Banks 0 and 1 wrap around to the next line to fetch the 2nd and 3rd pixels.
			bank_rd_addr[0] = rd_base_addr_next; 
			bank_rd_addr[1] = rd_base_addr_next;
		end
		
		default: begin
			/* default assignments */
		end
	endcase
end

endmodule