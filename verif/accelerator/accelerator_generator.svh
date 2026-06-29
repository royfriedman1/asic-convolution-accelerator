`ifndef ACCELERATOR_GENERATOR_SVH
`define ACCELERATOR_GENERATOR_SVH

import accelerator_pkg::*;

class accelerator_generator;
	
	virtual accelerator_if vif;
	
	// Mailboxes
	mailbox #(accelerator_transaction) gen2drv; // To Driver
	mailbox #(accelerator_transaction) gen2scb; // To Scoreboard
	
	// File Descriptors
	int fd_in;
	int fd_exp;
	
	int num_config_words = 13; // 9 weights + 1 bias + 3 threshold
	
	// Constructor
	function new(mailbox #(accelerator_transaction) gen2drv,
				 mailbox #(accelerator_transaction) gen2scb,
				 virtual accelerator_if             vif);
		this.gen2drv = gen2drv;
		this.gen2scb = gen2scb;
		this.vif     = vif; 
	endfunction
	
	task run();
		string input_file, expected_file;
		int image_idx = 0;
		
		$display("[Generator] @%0t: Starting Regression", $time);
		
		forever begin
			input_file    = $sformatf("stimulus/input_%0d.hex", image_idx);
			expected_file = $sformatf("golden/expected_%0d.txt", image_idx);
			
			fd_in = $fopen(input_file, "r");
			if (fd_in == 0) begin
				$display("[Generator] @%0t: No more input files found: Closing.", $time);
				break;
			end
			
			fd_exp = $fopen(expected_file, "r");
			if (fd_exp == 0) begin
				$fatal(1, "[Generator] Missing expected file for image %0d", image_idx);
			end
			
			$display("[Generator] @%0t: --- Processing Image #%0d ---", $time, image_idx);
			
			apply_reset();
			
			process_single_image();
			
			$fclose(fd_in);
			$fclose(fd_exp);
			
			wait_for_pipeline_empty();
			image_idx++;
		end
		$display("[Generator] @%0t: Regression Finished Successfully.", $time);
	endtask
	
	// Task to ensure both TB mailboxes and hardware are clean
	task apply_reset();
		accelerator_transaction dummy;
		$display("[Generator] @%0t: Flushing queues and applying hardware reset...", $time);
		
		// Flush Testbench Mailboxes (removes leftovers from previous image)
		while (gen2drv.try_get(dummy));
		while (gen2scb.try_get(dummy));
		
		// Trigger physical hardware reset via the Interface proxy task
		vif.manual_reset();
	endtask
	
	task process_single_image();
		accelerator_transaction tr, scb_clone;
		bit [PIXEL_W-1:0] tmp_data;
		bit               tmp_exp;
		int               config_count = 0;
		
		// --- Phase 1: Configuration ---
		while (config_count < num_config_words && !$feof(fd_in)) begin
			if ($fscanf(fd_in, "%h", tmp_data) == 1) begin
				tr = new();
				void'(tr.randomize()); // Randomize delays
				tr.input_bus      = tmp_data;
				tr.cfg_wr_en      = 1'b1;
				tr.pixel_valid_in = 1'b0;
				gen2drv.put(tr);
				config_count++;
			end
		end
		
		// --- Phase 2: Pixel Streaming ---
		for (int r = 0; r < IMG_HEIGHT; r++) begin
			for (int c = 0; c < IMG_WIDTH; c++) begin
				
				if ($fscanf(fd_in, "%h", tmp_data) != 1) begin
					$error("[Generator] Unexpected EOF in input file at Row:%0d Col:%0d", r, c);
					break;
				end
				
				tr = new();
				if (!tr.randomize()) $error("Randomization failed!");
				
				tr.input_bus      = tmp_data;
				tr.cfg_wr_en      = 1'b0;
				tr.pixel_valid_in = 1'b1;
				
				// deliver only expected output to scoreboard
				if (r >= 2 && c >= 2) begin
					if ($fscanf(fd_exp, "%b", tmp_exp) == 1) begin
						tr.expected_out = tmp_exp;
						scb_clone = new(); // Ensure object exists before copying
						tr.copy(scb_clone);
						gen2scb.put(scb_clone);
					end else begin
						$error("[Generator] Expected file ended prematurely at R:%0d C:%0d", r, c);
					end
				end
				
				gen2drv.put(tr);
			end
		end
		
		$display("[Generator] @%0t: Image Injection Complete. Initiating Pipeline Flush", $time);

		// --- Phase 3: Pipeline Flush
		// Push 15 cycles of IDLE to allow the Accelerator's MAC tree to drain
		// the last pixels, and to allow the FSM to gracefully return to the CONFIG state.
		for (int i = 0; i < 15; i++) begin
			tr = new();
			tr.cfg_wr_en      = 1'b0;
			tr.pixel_valid_in = 1'b0;
			tr.input_bus      = 8'h00;
			tr.injection_delay = 0; 
			gen2drv.put(tr);
		end

	endtask
	
	task wait_for_pipeline_empty();
		// Increased delay to 100 to ensure the DUT pipeline is 100% drained before we apply the reset for the next image.
		repeat(100) @(vif.drv_cb);
	endtask
	
endclass

`endif