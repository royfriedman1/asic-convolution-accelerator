import accelerator_pkg::*;

module control_unit_sva (
	input logic                   clk,
	input logic                   rst_n,
	
	input logic                   cfg_wr_en,
	input logic [1:0]             current_state,
	input logic [1:0]             next_state,
	input logic [7:0]             col_cnt,
	input logic [7:0]             row_cnt,
	input logic                   pixel_valid,
	
	input logic                   wr_en,
	input logic [BANK_ADDR_W-1:0] wr_addr,
	input logic [1:0]             wr_bank_sel,
	input logic                   window_valid 
);

// ASSUMPTIONS: Environment Constraints

// Assume: Pixel Stream Liveness Bounded to 20 cycles to keep proofs feasible.
property p_pixel_arrives;
	@(posedge clk) disable iff (!rst_n)
			(current_state == ST_WARM_UP || current_state == ST_EXECUTE) |-> ##[0:20] pixel_valid;
endproperty

assume_pixel_arrives: assume property (p_pixel_arrives);


// ASSERTIONS:

// Assert: Clean Initialization Verifies the Explicit Flush logic.
property p_clean_start;
	@(posedge clk) disable iff (!rst_n)
			(current_state == ST_IDLE && next_state == ST_WARM_UP) |-> (col_cnt == '0 && row_cnt == '0);
endproperty

assert_clean_start: assert property (p_clean_start)
		else $error("[SVA ERROR] Counters are NOT zero when leaving IDLE!");

// Assert: Memory Write Safety (Out-of-Bounds Protection)
property p_wr_addr_safe;
	@(posedge clk) disable iff (!rst_n)
			wr_en |-> (wr_addr < BANK_DEPTH);
endproperty

assert_wr_addr_safe: assert property (p_wr_addr_safe)
		else $fatal(1, "[SVA FATAL] Memory corruption risk! wr_addr exceeded BANK_DEPTH.");

// Assert: Power-Optimized Isolation. 'window_valid' drives the downstream PE multipliers. This assertion proves
property p_valid_isolation;
	@(posedge clk) disable iff (!rst_n)
			(current_state == ST_IDLE || current_state == ST_CONFIG) |-> !window_valid;
endproperty

assert_valid_isolation: assert property (p_valid_isolation)
		else $error("[SVA ERROR] Protocol Violation: window_valid is HIGH in an inactive state!");

// Assert: Geometric Window Integrity (Horizontal Padding). Validates that the system correctly calculates sliding window boundaries.
property p_window_fill_protection;
	@(posedge clk) disable iff (!rst_n)
			(col_cnt < (KERNEL_SIZE - 1)) |-> !window_valid;
endproperty

assert_window_fill_protection: assert property (p_window_fill_protection)
		else $error("[SVA ERROR] window_valid went HIGH before shift register filled!");

// Assert: Valid Memory Bank Selection
property p_valid_bank;
	@(posedge clk) disable iff (!rst_n)
			wr_en |-> (wr_bank_sel < NUM_BANKS);
endproperty

assert_valid_bank: assert property (p_valid_bank)
		else $error("[SVA ERROR] Tried to write to an invalid SRAM bank!");


// COVER POINTS: Reachability Analysis

// Cover: FSM Reachability
cover_reached_execute: cover property (
		@(posedge clk) disable iff (!rst_n)
		current_state == ST_EXECUTE
		);

// Cover: Row Completion
cover_row_done: cover property (
		@(posedge clk) disable iff (!rst_n)
		(current_state == ST_EXECUTE && col_cnt == (IMG_WIDTH - 1))
		);

cover property (@(posedge clk) (current_state == ST_CONFIG && next_state == ST_IDLE && col_cnt == THRESH_STEPS + NUM_WEIGHTS ));

endmodule

// Bind the SVA module to the RTL DUT
bind control_unit control_unit_sva sva_inst (.*);