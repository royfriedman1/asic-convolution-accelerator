import accelerator_pkg::*;

module processing_element (
	input  logic            clk,
	input  logic            rst_n,
	
	// From Control Unit
	input  logic            window_valid_in,
	
	// 9 Pixels from Line Buffer
	input  window_t         pixels,
	
	// From Register Bank
	input  kernel_weights_t weights,
	input  pixel_t          bias,
	input  accum_t          threshold,
	
	//outputs
	output accum_t          sum,            // Intermediate sum for Debug/Pooling
	output logic            pixel_out,      // Final Classified Bit
	output logic            pixel_valid_out // Latency-compensated Valid
);

/// --- Pipeline Stage 1 Registers ---
logic         s1_valid;
accum_t       mult_q [0:WINDOW_SIZE-1];
pixel_t s1_bias;
accum_t s1_threshold;

// --- Pipeline Stage 2 Registers ---
logic         s2_valid;
accum_t       acc_q;
accum_t s2_threshold;

// --- Pipeline Stage 3 Registers ---
logic         s3_valid;
logic         act_q;
accum_t sum_q;


// --- STAGE 1: Multiplication ---

// Power Optimization: Multipliers only toggle when valid data is present.
always_ff @(posedge clk) begin
	if (!rst_n) begin
		s1_valid <= 1'b0;	
	end else begin	
		s1_valid <= window_valid_in;
		if (window_valid_in) begin
			for (int i = 0; i < WINDOW_SIZE; i++) begin
				mult_q[i] <= pixels[i] * weights[i];
			end
			s1_bias <= bias;
			s1_threshold <= threshold;		
		end
	end
end

// --- STAGE 2 ---

// sums up all the multiplications and the bias
accum_t acc_q_res;
always_comb begin
	acc_q_res = accum_t'(s1_bias);
	for (int i =0; i< WINDOW_SIZE; i++) begin
		acc_q_res = 	acc_q_res + mult_q[i];
	end
end

always_ff @(posedge clk) begin
	if (!rst_n) begin
		s2_valid <= 1'b0;
	end else begin
		s2_valid <= s1_valid;
		if (s1_valid) begin
			acc_q <= acc_q_res;
			s2_threshold <= s1_threshold;
		end
	end
end

// --- STAGE 3: Activation Function (Thresholding) ---

always_ff @(posedge clk) begin
	if (!rst_n) begin
		s3_valid <= 1'b0;
		act_q    <= 1'b0;
	end else begin
		s3_valid <= s2_valid;
		if (s2_valid) begin
			act_q <= (acc_q > s2_threshold);
			sum_q <= acc_q;
		end
	end
end


// --- Output Assignments ---

assign sum             = sum_q;
assign pixel_out       = act_q;
assign pixel_valid_out = s3_valid;

endmodule

