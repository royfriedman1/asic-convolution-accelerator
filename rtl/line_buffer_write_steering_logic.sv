import accelerator_pkg::*;

module line_buffer_write_steering_logic (
	// Inputs from Control Unit
	input  pixel_t          pixel_in,
	input  logic            wr_en,
	input  logic [1:0]      wr_row_sel,
	input  logic [1:0]      wr_bank_sel,
	
	// Outputs to the Memory Banks
	output pixel_t          data_to_banks,
	output logic [2:0][2:0] bank_wr_en // One-hot write enable matrix [Row][Bank]
);

// Broadcast 
assign data_to_banks = pixel_in;

// Combinational Decoder
always_comb begin
	bank_wr_en = '0; 
	if (wr_en) begin
		unique case (wr_row_sel)
			2'd0: begin // Row A [0][X]
				unique case (wr_bank_sel)
					2'd0: bank_wr_en[0][0] = 1'b1;
					2'd1: bank_wr_en[0][1] = 1'b1;
					2'd2: bank_wr_en[0][2] = 1'b1;
					default: bank_wr_en[0] = '0;
				endcase
			end
			2'd1: begin // Row B [1][X]
				unique case (wr_bank_sel)
					2'd0: bank_wr_en[1][0] = 1'b1;
					2'd1: bank_wr_en[1][1] = 1'b1;
					2'd2: bank_wr_en[1][2] = 1'b1;
					default: bank_wr_en[1] = '0;
				endcase
			end
			2'd2: begin // Row C [2][X]
				unique case (wr_bank_sel)
					2'd0: bank_wr_en[2][0] = 1'b1;
					2'd1: bank_wr_en[2][1] = 1'b1;
					2'd2: bank_wr_en[2][2] = 1'b1;
					default: bank_wr_en[2] = '0;
				endcase
			end
			default: bank_wr_en = '0;
		endcase
	end
end


endmodule