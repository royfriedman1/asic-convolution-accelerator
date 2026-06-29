`ifndef ACCELERATOR_MONITOR_SVH
`define ACCELERATOR_MONITOR_SVH

class accelerator_monitor;
	
	virtual accelerator_if.mon_mp vif;
	
	mailbox #(accelerator_transaction) mon2scb;

	// File Logging Variables
	int fd;
	int img_idx = 0;
	int pixel_count = 0;
	const int PIXELS_PER_IMG = 64516; // 254 * 254

	function new(virtual accelerator_if.mon_mp vif,
				 mailbox #(accelerator_transaction) mon2scb);
		this.vif = vif;
		this.mon2scb = mon2scb;
		void'($system("mkdir -p actual")); 		// Create directory for output files
	endfunction
	
	task run();
		$display("[Monitor] @%0t: Monitor started - Listening to Accelerator Output", $time);
		
		forever begin
			@(vif.mon_cb);
			
			if (vif.mon_cb.pixel_valid_out === 1'b1) begin
				accelerator_transaction actual_tr; 
				
				// create new results file
				if (pixel_count == 0) begin
					string filename = $sformatf("actual/output_%0d.txt", img_idx);
					fd = $fopen(filename, "w");
					if (fd == 0) $error("[Monitor] Failed to open %s", filename);
				end

				$fwrite(fd, "%b\n", vif.mon_cb.pixel_out);
				pixel_count++;

				// Handling end of input frame
				if (pixel_count == PIXELS_PER_IMG) begin
					$fclose(fd);
					$display("[Monitor] @%0t: Image #%0d exported to actual/output_%0d.txt", $time, img_idx, img_idx);
					img_idx++;
					pixel_count = 0; // new img
				end

				// sending transactions to Scoreboard
				actual_tr = new(); 
				actual_tr.actual_out = vif.mon_cb.pixel_out;
				mon2scb.put(actual_tr);
				
				$display("[Monitor] @%0t: Captured Actual Pixel: %h", $time, actual_tr.actual_out);
			end
		end
	endtask
	
endclass

`endif