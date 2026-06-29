#######################################################################
## 1. Library & Block Management
#######################################################################
close_lib -purge -all
open_lib accelerator_synth.dlib

# Load the block from the CTS stage (FIXED: was power_grid_done before)
open_block accelerator_top/cts

puts "--- STARTING ROUTING STAGE ---"

#######################################################################
## 2. Enable Hold Fixing in Routing
#######################################################################
# Make sure routing optimization fixes hold violations
set_app_options -name route_opt.flow.enable_ccd -value true

#######################################################################
## 3. Load Routing Rules & Execution
#######################################################################
source /project/tsmc28mmwave/users/royfriedman/ws/ex_vlsi_9/syn/routing_rules.tcl

puts "-> Starting routing flow..."
check_routability
route_global
route_track
route_detail -max_number_iterations 5

#######################################################################
## 4. Routing Optimization (Setup + Hold)
#######################################################################
puts "-> Running post-route optimization..."
route_opt

# Dedicated hold optimization pass
puts "-> Running dedicated hold optimization..."
route_opt
# Add redundant vias for reliability
add_redundant_vias

# ECO fixes
route_eco

#######################################################################
## 5. Verification and PG Connectivity
#######################################################################
puts "-> Running verification..."

# Validate Power/Ground and Connectivity
check_pg_drc
check_routes

# connect_pg_net acts as a final safeguard
connect_pg_net -net VDD [get_pins -hierarchical */VDD]
connect_pg_net -net VSS [get_pins -hierarchical */VSS]

#######################################################################
## 6. Final Analysis and Reports
#######################################################################
file mkdir v1/reports
check_legality

report_qor                              > v1/reports/routing_qor.log
report_congestion                       > v1/reports/routing_congestion.log
report_utilization                      > v1/reports/routing_utilization.log
report_timing -delay max -max_paths 10  > v1/reports/routing_setup_timing.log
report_timing -delay min -max_paths 10  > v1/reports/routing_hold_timing.log

#######################################################################
## 7. Save Final Routed Block
#######################################################################
save_block -as accelerator_top/routed

puts "========================================================="
puts " STEP 7: ROUTING COMPLETED SUCCESSFULLY! "
puts " Block saved as: accelerator_top/routed "
puts "========================================================="
exit