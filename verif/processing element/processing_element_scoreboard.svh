`ifndef PROCESSING_ELEMENT_SCOREBOARD_SVH
`define PROCESSING_ELEMENT_SCOREBOARD_SVH

class processing_element_scoreboard;
	
	// Input from Monitor containing both Expected and Actual data
	mailbox #(processing_element_transaction) mon2scb;
	
	// Functional Coverage object to track test quality
	processing_element_coverage cov;
	
	// Result counters
	int pass_count = 0;
	int fail_count = 0;
	
	function new(mailbox #(processing_element_transaction) mon2scb);
		this.mon2scb = mon2scb;
		cov = new(); // Initialize coverage object
	endfunction
	
	task run();
		processing_element_transaction tr;
		
		$display("[Scoreboard] @%t: Scoreboard started", $time);
		
		forever begin
			// Wait and get the completed transaction from the monitor
			mon2scb.get(tr);
			
			// Compare RTL Actual output vs Golden Model Expected output
			if (tr.actual_sum === tr.expected_sum && tr.actual_pixel_out === tr.expected_pixel_out) begin
				
				pass_count++;
				$display("[Scoreboard] @%t: PASS! Sum=%h, Expected=%h | Actual Bit: %b, Expected Bit: %b",
						$time, tr.actual_sum, tr.expected_sum, tr.actual_pixel_out, tr.expected_pixel_out);
				
				// Sample functional coverage for successful transactions
				cov.sample(tr);
				
			end else begin
				
				fail_count++;
				// Report mismatch as an error in the simulation log
				$error("[SCB] @%t: ERROR Mismatch!", $time);
				$display("      Expected Sum: %h | Actual Sum: %h", tr.expected_sum, tr.actual_sum);
				$display("      Expected Bit: %b | Actual Bit: %b", tr.expected_pixel_out, tr.actual_pixel_out);
				
			end
		end
	endtask
	
	// Print the final summary of the simulation
	function void report();
		$display("\n--- FINAL SIMULATION REPORT ---");
		$display("Total Tests: %0d", pass_count + fail_count);
		$display("Passed:      %0d", pass_count);
		$display("Failed:      %0d", fail_count);
		if (fail_count == 0) $display("RESULT: SUCCESS!");
		else                $display("RESULT: FAILURE - Check the logs.");
		$display("-------------------------------\n");
	endfunction
	
endclass

`endif