import accelerator_pkg::*;

module control_unit (
	// System Interface
	input  logic                   clk,
	input  logic                   rst_n,
	input  logic                   cfg_wr_en,
	input  logic                   pixel_valid,
	
	// Configuration Interface
	output logic [CFG_ADDR_W-1:0]  cfg_addr,     // Address for loading weights/bias/thresh to the register bank
	
	// Line Buffer Write Controls
	output logic [BANK_ADDR_W-1:0] wr_addr,      // Physical write address inside the target mem bank
	output logic [1:0]             wr_bank_sel,  // Selects the interleaved bank (0, 1, or 2) for the incoming pixel
	output logic [1:0]             wr_row_sel,   // Selects the cyclic line buffer row (A, B, or C) to write into
	output logic                   wr_en,        // Global write enable for the line buffers
	
	// Line Buffer Read & Reordering Controls
	output logic [BANK_ADDR_W-1:0] rd_base_addr, // Physical read address of the window's left-most pixel
	output logic [1:0]             horiz_offset, // Controls horizontal MUXes (indicates which bank holds the left-most pixel)
	output logic [1:0]             vert_ptr,     // Controls vertical MUXes (points to the oldest row, acting as the 'Top' of the 3x3 window)
	output logic                   rd_en,        // Global read enable for the line buffers
	
	// Processing Element Interface
	output logic                   window_valid  // Indicates a full, geometrically correct 3x3 window is ready for convolution
);

// Local Parameters & Typedefs

// Total configuration cycles: Weights (9) + Bias (1) + Thresh (3) = 13
localparam int TOTAL_CFG_CYCLES = NUM_WEIGHTS + 1 + THRESH_STEPS;

state_t current_state, next_state;

// Internal Counters
logic [$clog2(IMG_WIDTH)-1:0]  col_cnt;
logic [$clog2(IMG_HEIGHT)-1:0] row_cnt;

// Control Flags
logic line_ended;
logic frame_ended;
logic global_en;
logic flush_counters;
logic is_row_valid;
logic is_col_valid;

// Delay Registers (Pipeline Alignment)
// When writing a new pixel to memory, it acts as the right-most pixel of the current window.
// Delay the write address and bank selectors by 2 cycles to "remember" the location of the left-most pixel.
logic [BANK_ADDR_W-1:0] wr_addr_d1, wr_addr_d2;
logic [1:0]             wr_bank_sel_d1, wr_bank_sel_d2;

// Combinational Logic & Flags

// Raster scan boundary detection
assign line_ended  = (col_cnt == (IMG_WIDTH - 1));
assign frame_ended = line_ended && (row_cnt == (IMG_HEIGHT - 1));

// Unified enable signal to allow synthesis tools to infer robust Clock Gating (ICG).
// Active only when processing valid pixels or during active configuration (Power Optimization).
assign global_en   = pixel_valid || (cfg_wr_en && (current_state == ST_CONFIG || current_state == ST_IDLE));

// Explicit Counter Flush Logic for Back-to-Back Safety
assign flush_counters = (current_state != ST_IDLE && next_state == ST_IDLE) ||
		(current_state == ST_IDLE && !global_en);

// Memory Routing Assignments

// Read routing: Point to the history records from 2 cycles ago (left-most pixel of the 3x3 window)
assign horiz_offset = wr_bank_sel_d2;
assign rd_base_addr = wr_addr_d2;

// Config routing: Reuse the lower bits of the main column counter
assign cfg_addr     = col_cnt[CFG_ADDR_W-1:0];

// Write enable is active when the system is globally enabled
assign wr_en        = global_en;

// Vertical Pointer (Cyclic Buffer Logic):
// The "Top" row of the 3x3 window is always the oldest row, which is the one right after the current write row.
assign vert_ptr     = (wr_row_sel == (KERNEL_SIZE - 1)) ? 2'd0 : wr_row_sel + 1'b1;

// Data Path: Counters & Memory Pointers
always_ff @(posedge clk or negedge rst_n) begin
	if (!rst_n) begin
		col_cnt        <= '0;
		wr_bank_sel    <= '0;
		wr_addr        <= '0;
		row_cnt        <= '0;
		wr_row_sel     <= '0;
		wr_addr_d1     <= '0; wr_addr_d2     <= '0;
		wr_bank_sel_d1 <= '0; wr_bank_sel_d2 <= '0;
	end
	else if (flush_counters) begin
		col_cnt        <= '0;
		wr_bank_sel    <= '0;
		wr_addr        <= '0;
		row_cnt        <= '0;
		wr_row_sel     <= '0;
		wr_addr_d1     <= '0; wr_addr_d2     <= '0;
		wr_bank_sel_d1 <= '0; wr_bank_sel_d2 <= '0;
	end
	else if (global_en) begin
		
		// CONFIG Phase
		if (current_state == ST_CONFIG || (current_state == ST_IDLE && cfg_wr_en)) begin
			col_cnt <= col_cnt + 1'b1;
			wr_bank_sel <= '0;
			wr_addr     <= '0;
		end
		
		// EXECUTE/WARM_UP Phase
		else begin
			col_cnt <= line_ended ? '0 : col_cnt + 1'b1;
			
			// Bank Selection (Modulo-3 equivalent)
			wr_bank_sel <= (line_ended || wr_bank_sel == (NUM_BANKS - 1)) ? '0 : wr_bank_sel + 1'b1;
			
			// Physical memory address increments only after filling a full cycle across all 3 banks
			if (line_ended)
				wr_addr <= '0;
			else if (wr_bank_sel == (NUM_BANKS - 1))
				wr_addr <= wr_addr + 1'b1;
			
			// Vertical Tracking. Advances to the next row at the end of each image line.
			if (line_ended && pixel_valid) begin
				row_cnt    <= (row_cnt == (IMG_HEIGHT - 1)) ? '0 : row_cnt + 1'b1;
				wr_row_sel <= (wr_row_sel == (KERNEL_SIZE - 1)) ? '0 : wr_row_sel + 1'b1;
			end
		end
		
		// Pipeline Delay for generating read coordinates (left-most pixel)
		wr_addr_d1 <= wr_addr;
		wr_addr_d2 <= wr_addr_d1;
		wr_bank_sel_d1 <= wr_bank_sel;
		wr_bank_sel_d2 <= wr_bank_sel_d1;
	end
end

// Window Valid Generation

// Pre-calculating physical boundaries dynamically
always_ff @(posedge clk or negedge rst_n) begin
	if (!rst_n) begin
		is_row_valid <= 1'b0;
		is_col_valid <= 1'b0;
	end else if (flush_counters) begin
		is_row_valid <= 1'b0;
		is_col_valid <= 1'b0;
	end else if (global_en) begin
		// A full 3x3 window requires at least 3 active rows (row_cnt >= 2)
		is_row_valid <= (row_cnt >= (KERNEL_SIZE - 1));
		is_col_valid <= (col_cnt >= (KERNEL_SIZE - 2)) && !line_ended;
	end
end

// Ensures calculations only happen on fully formed 3x3 geometric windows.
assign window_valid = (current_state == ST_EXECUTE || current_state == ST_WARM_UP) &&
		pixel_valid &&
		(row_cnt >= (KERNEL_SIZE - 1)) &&
		(col_cnt >= (KERNEL_SIZE - 1));


// Finite State Machine (FSM)
always_ff @(posedge clk or negedge rst_n) begin
	if (!rst_n) current_state <= ST_IDLE;
	else        current_state <= next_state;
end

always_comb begin
	next_state = current_state;
	unique case (current_state)
		ST_IDLE: begin
			if (cfg_wr_en)        next_state = ST_CONFIG;
			else if (pixel_valid) next_state = ST_WARM_UP;
		end
		
		ST_CONFIG: begin
			// Configuration finishes when the required number of parameters is loaded
			if (col_cnt == (TOTAL_CFG_CYCLES - 1) && cfg_wr_en)
				next_state = ST_IDLE;
		end
		
		ST_WARM_UP: begin
			// Transitions to EXECUTE once the buffer has (row_cnt == 2, col_cnt == 2).
			if (row_cnt == (KERNEL_SIZE - 1) && col_cnt == (KERNEL_SIZE - 1) && pixel_valid)
				next_state = ST_EXECUTE;
		end
		
		ST_EXECUTE: begin
			// Returns to IDLE safely once the final pixel of the frame has been processed
			if (frame_ended && pixel_valid)
				next_state = ST_IDLE;
		end
		default: next_state = ST_IDLE;
	endcase
end

// Read enable is active as soon as data starts flowing into the execution pipeline
assign rd_en = (current_state == ST_EXECUTE || current_state == ST_WARM_UP) && pixel_valid;

endmodule