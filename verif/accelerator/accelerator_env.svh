`ifndef ACCELERATOR_ENV_SVH
`define ACCELERATOR_ENV_SVH

class accelerator_env;
	
	// Sub-components of the environment
	accelerator_agent      agent;
	accelerator_scoreboard scb;
	accelerator_coverage   cov; 
	
	// Communication bridge between Monitor and Generator to Scoreboard
	mailbox #(accelerator_transaction) gen2scb;
	mailbox #(accelerator_transaction) mon2scb;
	
	// Virtual Interface to the physical world
	virtual accelerator_if vif;
	
	// Constructor: Instantiates and connects all components
	function new(virtual accelerator_if vif);
		this.vif = vif;
		gen2scb = new();
		mon2scb = new();
		agent = new(vif, gen2scb, mon2scb);
		scb = new(vif, mon2scb, gen2scb);
		cov = new(vif); 
	endfunction
	
	// Execution Task
	task run();
		$display("[Environment] @%0t: Starting Environment:", $time);
		
		// Start Scoreboard and Agent concurrently
		fork
			scb.run();
			agent.run();
		join_any // Wait for the Generator (inside Agent) to finish processing all images
		
		// Allow time for the final transactions to drain from the pipeline
		#100;
		
		// Print the final pass/fail summary
		scb.report();
	endtask
	
endclass

`endif