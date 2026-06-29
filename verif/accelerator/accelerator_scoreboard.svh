`ifndef ACCELERATOR_SCOREBOARD_SVH
`define ACCELERATOR_SCOREBOARD_SVH

class accelerator_scoreboard;
	
	// Virtual interface to monitor hardware reset signals
	virtual accelerator_if.mon_mp vif;
	
	// Input from Monitor containing both Expected and Actual data
	mailbox #(accelerator_transaction) mon2scb; // (Actual)
	mailbox #(accelerator_transaction) gen2scb; // (Expected)
	
	accelerator_transaction expected_queue[$];
	
	// Functional Coverage
	accelerator_coverage cov;
	
	// Result counters
	int pass_count = 0;
	int fail_count = 0;
	
	// Constructor
	function new(virtual accelerator_if.mon_mp vif,
			mailbox #(accelerator_transaction) mon2scb,
			mailbox #(accelerator_transaction) gen2scb);
		this.vif = vif;
		this.mon2scb = mon2scb;
		this.gen2scb = gen2scb;
	endfunction
	
	task run();
		$display("[Scoreboard] @%0t: Scoreboard active:", $time);
		
		fork
			// Thread A: Continuously collects expected data from the Generator.
			forever begin
				accelerator_transaction tr_gen;
				gen2scb.get(tr_gen);
				expected_queue.push_back(tr_gen);
			end
			
			// Thread B: Continuously collects actual results from the Monitor and compares them.
			forever begin
				accelerator_transaction tr_mon;
				accelerator_transaction tr_queue;
				
				// Blocking call: wait until the Monitor captures an actual output
				mon2scb.get(tr_mon);
				
				if (expected_queue.size() > 0) begin
					// Retrieve the oldest expected transaction
					tr_queue = expected_queue.pop_front();
					
					// Core Comparison Logic
					if (tr_mon.actual_out === tr_queue.expected_out) begin
						pass_count++;
					end else begin
						fail_count++;
						$error("[SCB] @%0t: MISMATCH! Expected: %b | Actual: %b",
								$time, tr_queue.expected_out, tr_mon.actual_out);
					end
				end else begin
					$error("[SCB] @%0t: Unexpected Output! Monitor captured data but Expected Queue is empty.", $time);
				end
			end
			
			// Thread C: Reset Handler, flushes BOTH queues when the Generator triggers a new frame reset
			forever begin
				wait(vif.rst_n === 1'b0);
				if (expected_queue.size() > 0) begin
					$display("[Scoreboard] @%0t: Hardware reset detected. Flushing expected queue.", $time);
					expected_queue.delete();
				end
				
				begin
					accelerator_transaction dummy;
					while (mon2scb.try_get(dummy));
				end
				
				wait(vif.rst_n === 1'b1);
			end
		join
	endtask
	
	// Print the final summary of the simulation
	function void report();
		$display("\n--- FINAL SIMULATION REPORT ---");
		$display("Total Tests: %0d", pass_count + fail_count);
		$display("Passed:      %0d", pass_count);
		$display("Failed:      %0d", fail_count);
		if (fail_count == 0 && pass_count > 0) $display("RESULT: SUCCESS!");
		else $display("RESULT: FAILURE - Check the logs.");
		$display("-------------------------------\n");
	endfunction
	
endclass

`endif