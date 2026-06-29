`ifndef PROCESSING_ELEMENT_SEQUENCER_SVH
`define PROCESSING_ELEMENT_SEQUENCER_SVH

class processing_element_sequencer;
	
	mailbox #(processing_element_transaction) seq2drv;
	
	int file_handle; // Pointer hex file
	
	// Constructor
	function new(mailbox #(processing_element_transaction) seq2drv);
		this.seq2drv = seq2drv;
	endfunction
	
	task run();
		
		processing_element_transaction tr; // create a transaction
		
		// Open the file for reading
		file_handle = $fopen("processing_element_test_vectors.hex", "r");
		if (file_handle == 0) begin
			$fatal("[Sequencer] Could not open pe_test_vectors.hex! Check file path.");
		end
		
		$display("[Sequencer] @%t: Starting to read Python test vectors:", $time);
		
		
		// Loop through the file until the end (EOF)
		while (!$feof(file_handle)) begin
			tr = new();
			
			// Use $fscanf to map the hex values directly to transaction fields
			if ($fscanf(file_handle, "%h %h %h %h %h %h",
					tr.pixels,
					tr.weights,
					tr.bias,
					tr.threshold,
					tr.expected_sum,
					tr.expected_pixel_out) == 6) begin
				
				tr.valid = 1'b1;
				$display("[Sequencer] @%t: Read vector -> Expected Sum: %h, Expected Pixel: %d", $time, tr.expected_sum, tr.expected_pixel_out);
				
				// Push to driver mailbox
				seq2drv.put(tr);
			end
		end
		
		$fclose(file_handle);
		$display("[Sequencer] @%t: Finished processing all test vectors.", $time);
	endtask
	
endclass

`endif