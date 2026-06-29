package accelerator_pkg;
	
	// --- System Dimensions ---
	localparam int KERNEL_SIZE = 3;
	localparam int NUM_WEIGHTS = KERNEL_SIZE * KERNEL_SIZE;
	
	// --- Data Widths ---
	localparam int PIXEL_W  = 8;  // Unsigned 8-bit
	localparam int WEIGHT_W = 8;  // Signed 8-bit
	localparam int ACCUM_W  = 20; // 20-bit threshold
	localparam int CONFIG_W = 8;  // Programming bus width
	
	// --- Address Map ---
	typedef enum logic [3:0] {
		ADDR_WEIGHT_BASE = 4'h0, // 0-8: Weights
		ADDR_BIAS        = 4'h9, // 9: Bias
		ADDR_THRESH_BASE = 4'hA  // A-C: Threshold (3 cycles)
	} config_addr_e;
	
	// --- Derived Types ---
	typedef logic [PIXEL_W-1:0]  pixel_t;
	typedef logic [WEIGHT_W-1:0] weight_t;
	typedef logic [ACCUM_W-1:0] accum_t;
	typedef logic [CONFIG_W-1:0] config_t;
	
	// A packed array for the entire kernel weights
	typedef weight_t [NUM_WEIGHTS-1:0] kernel_weights_t;
	
	
	
	// 1. Frame Architecture Parameters
	localparam int IMG_WIDTH      = 256;          // Image width in pixels
	localparam int IMG_HEIGHT     = 256;          // Image height in pixels
	localparam int WINDOW_SIZE    = KERNEL_SIZE * KERNEL_SIZE; // 9 pixels
	
	// 2. Memory Hierarchy & Addressing
	// We use a 3-bank interleaved memory to allow parallel access to a 3x3 window
	localparam int NUM_BANKS      = 3;
	localparam int BANK_DEPTH     = (IMG_WIDTH / NUM_BANKS) + 1; // ~86 entries per bank
	
	// Physical Address Width: The actual bits needed to address a bank (7 bits)
	localparam int BANK_ADDR_W    = $clog2(BANK_DEPTH);
	
	// Logical Address Width: Width needed to count full row pixels (8 bits)
	localparam int ROW_COORD_W    = $clog2(IMG_WIDTH);
	
	// Configuration Memory (Weights/Biases)
	localparam int CFG_ADDR_W     = $clog2(NUM_WEIGHTS);
	
	// 3. Data Path Bit-Widths
	localparam int PIXEL_WIDTH    = 8;            // Input pixel (Uint8)
	localparam int WEIGHT_WIDTH   = 8;            // Signed weight (Int8)
	localparam int MULT_WIDTH     = PIXEL_WIDTH + WEIGHT_WIDTH; // 16 bits
	
	
	// Configuration bus width (matches pixel width for streaming)
	localparam int THRESH_STEPS   = (ACCUM_W + CONFIG_W - 1) / CONFIG_W;
	
	// Flattened 3x3 Window: A packed array of 9 pixels (72 bits total)
	typedef pixel_t [WINDOW_SIZE-1:0] window_t;
	
	// 5. Finite State Machine (FSM) States
	typedef enum logic [1:0] {
		ST_IDLE    = 2'b00, // Waiting for start
		ST_CONFIG  = 2'b01, // Loading Weights/Biases
		ST_WARM_UP = 2'b10, // Pre-filling Line Buffers (Rows 0 & 1)
		ST_EXECUTE = 2'b11  // Real-time processing & output
	} state_t;
	
endpackage : accelerator_pkg