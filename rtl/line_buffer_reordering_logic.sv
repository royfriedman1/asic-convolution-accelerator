import accelerator_pkg::*;

module line_buffer_reordering_logic (
	// Control signals from the Control Unit
	input  logic [1:0]      horiz_offset, // Column shift (Col % 3)
	input  logic [1:0]      vert_ptr,     // Row shift (Cyclic buffer head)
	
	// Data fetched from the 9 physical banks [Row][Bank]
	input  pixel_t          bank_data[0:2][0:2], 
	
	// Final aligned 3x3 window output
	output window_t         window_out
);

	pixel_t row_aligned[0:2][0:2]; // [Physical_Row][Logical_Col]
	pixel_t win_matrix [0:2][0:2]; // [Logical_Row][Logical_Col]

	// Horizontal Realignment (Column Rotation): based on the horizontal offset the logical "Left" column is always at index [0].
	always_comb begin
		for (int r = 0; r < 3; r++) begin
			unique case (horiz_offset)
				2'd0: begin // Order: [Bank0, Bank1, Bank2]
					row_aligned[r][0] = bank_data[r][0];
					row_aligned[r][1] = bank_data[r][1];
					row_aligned[r][2] = bank_data[r][2];
				end
				2'd1: begin // Order: [Bank1, Bank2, Bank0]
					row_aligned[r][0] = bank_data[r][1];
					row_aligned[r][1] = bank_data[r][2];
					row_aligned[r][2] = bank_data[r][0];
				end
				2'd2: begin // Order: [Bank2, Bank0, Bank1]
					row_aligned[r][0] = bank_data[r][2];
					row_aligned[r][1] = bank_data[r][0];
					row_aligned[r][2] = bank_data[r][1];
				end
				default: row_aligned[r] = '{default: '0};
			endcase
		end
	end

	// Vertical Realignment (Row Rotation), rotate the rows so index [0] is always the geometric TOP.
	always_comb begin
		unique case (vert_ptr)
			2'd0: begin // Row A is Top, B is Mid, C is Bot
				win_matrix[0] = row_aligned[0]; 
				win_matrix[1] = row_aligned[1]; 
				win_matrix[2] = row_aligned[2]; 
			end
			2'd1: begin // Row B is Top, C is Mid, A is Bot
				win_matrix[0] = row_aligned[1]; 
				win_matrix[1] = row_aligned[2]; 
				win_matrix[2] = row_aligned[0]; 
			end
			2'd2: begin // Row C is Top, A is Mid, B is Bot
				win_matrix[0] = row_aligned[2]; 
				win_matrix[1] = row_aligned[0]; 
				win_matrix[2] = row_aligned[1]; 
			end
			default: win_matrix = '{default: '0};
		endcase
	end

	// Format: {Row0[0,1,2], Row1[0,1,2], Row2[0,1,2]}
	assign window_out = {
		win_matrix[0][0], win_matrix[0][1], win_matrix[0][2],
		win_matrix[1][0], win_matrix[1][1], win_matrix[1][2],
		win_matrix[2][0], win_matrix[2][1], win_matrix[2][2]
	};

endmodule