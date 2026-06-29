import accelerator_pkg::*;

module configuration_register_bank_tb;

// --- Signal Declarations ---
logic        clk;
logic        rst_n;
logic        cfg_wr_en;
logic [3:0]  cfg_addr;
config_t     input_bus;

// Outputs from DUT
kernel_weights_t weights_out;
weight_t         bias_out;
accum_t          threshold_out;

// --- Clock Generation ---
initial begin
	clk = 0;
	forever #5 clk = ~clk;
end

// --- Waveform Dumping ---
initial begin
	$fsdbDumpfile("top.fsdb");
	$fsdbDumpvars(0, configuration_register_bank_tb);
	$fsdbDumpvars("+all");
end

// --- DUT Instantiation ---
configuration_register_bank dut (
	.clk          (clk          ),
	.rst_n        (rst_n        ),
	.cfg_wr_en    (cfg_wr_en    ),
	.cfg_addr     (cfg_addr     ),
	.input_bus    (input_bus    ),
	.weights_out  (weights_out  ),
	.bias_out     (bias_out     ),
	.threshold_out(threshold_out)
);

// --- Main Test Sequence ---
initial begin
	$display(" STARTING VERIFICATION: CONFIGURATION BANK");
	
	initialize_signals();
	
	test_weight_and_bias_write();
	test_multi_cycle_threshold();
	test_write_disable_protection();
	
	$display("VERIFICATION PASSED");
	$finish;
end

// VERIFICATION TASKS

// Task: Initialize Signals safely
task initialize_signals();
	cfg_wr_en = 0;
	cfg_addr  = 4'h0;
	input_bus = 8'h00;
	rst_n     = 0;
	
	repeat(5) @(posedge clk);
	rst_n = 1;
	repeat(2) @(posedge clk);
endtask

// Task: Verify writing of 9 weights and 1 bias
task test_weight_and_bias_write();
	$display("[TEST] Weights & Bias Write...");
	
	@(negedge clk);
	cfg_wr_en = 1;
	
	// Write Weights
	for (int i = 0; i < WINDOW_SIZE; i++) begin
		cfg_addr  = i[3:0];
		input_bus = config_t'(8'hA0 + i);
		@(negedge clk);
	end
	
	// Write Bias
	cfg_addr  = ADDR_BIAS;
	input_bus = 8'h55;
	@(negedge clk);
	
	cfg_wr_en = 0;
	@(posedge clk); #1;
	
	// Check Weights
	for (int i = 0; i < WINDOW_SIZE; i++) begin
		// Note: The DUT stores weights in reverse order (8-i)
		assert(weights_out[8-i] === (8'hA0 + i))
		else $error("FAIL: Weight[%0d] mismatch!", i);
	end
	
	// Check Bias
	assert(bias_out === 8'h55)
	else $error("FAIL: Bias mismatch!");
	
	$display("[PASS] Weights & Bias Write");
endtask

// Task: Verify 3-cycle threshold loading
task test_multi_cycle_threshold();
	$display("[TEST] Multi-cycle Threshold...");
	
	@(negedge clk);
	cfg_wr_en = 1;
	
	// Write LSB (Bytes 0)
	cfg_addr  = ADDR_THRESH_BASE;
	input_bus = 8'hDE;
	@(negedge clk);
	
	// Write Mid (Byte 1)
	cfg_addr  = ADDR_THRESH_BASE + 1;
	input_bus = 8'hBC;
	@(negedge clk);
	
	// Write MSB (Byte 2)
	cfg_addr  = ADDR_THRESH_BASE + 2;
	input_bus = 8'h0A;
	@(negedge clk);
	
	cfg_wr_en = 0;
	@(posedge clk); #1;
	
	assert(threshold_out === 20'hABCDE)
	else $error("FAIL: Threshold mismatch!");
	
	$display("[PASS] Multi-cycle Threshold");
endtask

// Task: Ensure no writes occur when Enable is Low
task test_write_disable_protection();
	automatic weight_t prev_bias = bias_out;
	$display("[TEST] Write Disable Protection...");
	
	@(negedge clk);
	cfg_wr_en = 0;
	cfg_addr  = ADDR_BIAS;
	input_bus = ~prev_bias; // Attempt to overwrite
	
	repeat(2) @(posedge clk); #1;
	
	assert(bias_out === prev_bias)
	else $error("FAIL: Wrote while Disabled!");
	
	$display("[PASS] Write Disable Protection");
endtask


endmodule