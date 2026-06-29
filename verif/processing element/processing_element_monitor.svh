`ifndef PROCESSING_ELEMENT_MONITOR_SVH
`define PROCESSING_ELEMENT_MONITOR_SVH

class processing_element_monitor;
	
	virtual processing_element_if.MON vif;
	
	mailbox #(processing_element_transaction) mon2scb;
	mailbox #(processing_element_transaction) drv2mon;
	
	processing_element_transaction pipeline_q[$];
	
	// Constructor
	function new(virtual processing_element_if.MON    vif,
			mailbox #(processing_element_transaction) mon2scb,
			mailbox #(processing_element_transaction) drv2mon);
		this.vif = vif;
		this.mon2scb = mon2scb;
		this.drv2mon = drv2mon;
	endfunction
	
	// Main Monitoring Task
	task run();
		$display("[Monitor] @%t: Monitor started", $time);
		
		forever begin
			@(vif.cb);
			
			if (vif.window_valid_in === 1'b1) begin
				processing_element_transaction tr_in = new();
				drv2mon.get(tr_in);
				pipeline_q.push_back(tr_in);
			end
			
			// --- Output Stage ---
			// Check if the DUT has finished a calculation (3 cycles later)
			if (vif.cb.pixel_valid_out === 1'b1) begin
				if (pipeline_q.size() > 0) begin
					processing_element_transaction tr_out = pipeline_q.pop_front();
					
					tr_out.actual_sum       = vif.cb.sum;
					tr_out.actual_pixel_out = vif.cb.pixel_out;
					
					// Send the transaction (now containing inputs, expected, and actual results) to the Scoreboard
					mon2scb.put(tr_out);
					
					$display("[Monitor] @%t: Captured output. Actual Sum: %h", $time, tr_out.actual_sum);
				end else begin
					// Crucial Error: The hardware produced an output that wasn't triggered by an input
					$error("[Monitor] @%t: Unexpected Output! valid_out is high but pipeline is empty", $time);
				end
			end
		end
	endtask
	
endclass

`endif