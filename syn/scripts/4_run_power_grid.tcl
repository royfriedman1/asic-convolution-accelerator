#######################################################################
## 1. Library & Block Management
#######################################################################
# Clean memory to avoid file locks
close_lib -purge -all
open_lib accelerator_synth.dlib

# Open the design block saved from the Tap and Boundary Cell stage
open_block accelerator_top/top_placed_with_tap_and_boundary

puts "--- STARTING POWER GRID (PG) NETWORK GENERATION ---"

#######################################################################
## 2. Execute Power Grid Setup Script
#######################################################################
# Source the external PG creation script (Option 2 from your manual)
# Adjust the path if create_pg_network.tcl is not in the current /syn directory.
source /project/tsmc28mmwave/users/royfriedman/ws/ex_vlsi_9/syn/create_pg_network.tcl

#######################################################################
## 3. Verify Power Grid Connectivity
#######################################################################
puts "-> Checking PG connectivity to ensure all cells have power..."

# Verify that there are no floating standard cells or missing VDD/VSS connections
check_pg_connectivity

# Output DRC check for Power Grid
file mkdir v1/reports
check_pg_drc > v1/reports/power_grid_drc.log

#######################################################################
## 4. Save Milestone Block
#######################################################################
# Save this milestone state before proceeding to standard cell placement
save_block -as accelerator_top/power_grid_done

puts "========================================================="
puts " STEP 4: POWER GRID MESH & RAILS CREATED SUCCESSFULLY! "
puts " Block saved as: accelerator_top/power_grid_done "
puts "========================================================="
exit
