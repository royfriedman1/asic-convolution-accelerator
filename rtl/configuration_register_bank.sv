import accelerator_pkg::*;

module configuration_register_bank (
	input  logic            clk,
	                        rst_n,
	input  logic            cfg_wr_en,
	input  logic [3:0]      cfg_addr,
	input  config_t         input_bus,
	
	output kernel_weights_t weights_out,
	output weight_t         bias_out,
	output accum_t          threshold_out
);

logic [23:0] thresh_reg;


// Configuration Write Logic
always_ff @(posedge clk or negedge rst_n) begin
	if (!rst_n) begin
		weights_out <= '0;
		bias_out    <= '0;
		thresh_reg  <= '0;
	end
	else if (cfg_wr_en) begin
		unique case (1'b1)
			(cfg_addr < ADDR_BIAS): weights_out[8 - cfg_addr] <= input_bus;				// Write individual kernel weights
			
			(cfg_addr == ADDR_BIAS): bias_out <= input_bus; 			// Write bias value
		
			(cfg_addr >= ADDR_THRESH_BASE): begin 			// Write threshold value
				case (cfg_addr - ADDR_THRESH_BASE)
					2'd0: thresh_reg[7:0]   <= input_bus;
					2'd1: thresh_reg[15:8]  <= input_bus;
					2'd2: thresh_reg[23:16] <= input_bus;
					default: begin
						
					end
				endcase
			end
			
			default: begin
			
			end
			
		endcase
	end
end

// Output Mapping
assign threshold_out = accum_t'(thresh_reg[ACCUM_W-1:0]);


endmodule