#######################################################################
## 1. Library & Block Management
#######################################################################
# Clean memory to avoid file locks
close_lib -purge -all
open_lib accelerator_synth.dlib

# Open the design block saved from the Placement stage
open_block accelerator_top/placement

puts "--- STARTING CLOCK TREE SYNTHESIS (CTS) STAGE ---"

#######################################################################
## 2. Reload SDC with Updated Constraints
#######################################################################
puts "-> Reloading SDC with updated design rule constraints..."
current_scenario FUNC_Fast
source /project/tsmc28mmwave/users/royfriedman/ws/ex_vlsi_9/accelerator_top.sdc

current_scenario FUNC_Slow
source /project/tsmc28mmwave/users/royfriedman/ws/ex_vlsi_9/accelerator_top.sdc

# Enable hold analysis on all scenarios
foreach_in_collection scen [all_scenarios] {
    set scen_name [get_attribute $scen name]
    set_scenario_status $scen_name -active true -setup true -hold true
}

#######################################################################
## 3. Create NDR (Non-Default Routing) Rule for Clocks
#######################################################################
puts "-> Defining NDR rules and shielding for clock nets..."
create_routing_rule CLK_NDR \
  -default_reference_rule \
  -multiplier_width 2 \
  -spacings {M2 0.052 M3 0.052 M4 0.08 M5 0.08} \
  -shield \
  -shield_spacings {M2 0.026 M3 0.026 M4 0.04 M5 0.04} \
  -snap_to_track

#######################################################################
## 4. Restrict Routing Layers
#######################################################################
# Limit clock routing to robust metal layers (M2 to M5)
set_clock_routing_rules -rules CLK_NDR \
  -min_routing_layer M2 \
  -max_routing_layer M5

#######################################################################
## 5. CTS Quality Settings
#######################################################################
# Tighter skew target (50ps instead of 100ps)
set_clock_tree_options -clocks [all_clocks] -target_skew 0.05

# Enable Concurrent Clock and Data optimization (critical for hold!)
set_app_options -name clock_opt.flow.enable_ccd -value true


#######################################################################
## 6. Run CTS Flow
#######################################################################
puts "-> Building clock tree..."
clock_opt -to build_clock

puts "-> Routing clock tree..."
clock_opt -from build_clock -to route_clock

puts "-> Final post-CTS optimization..."
clock_opt -to final_opto

#######################################################################
## 7. Switch to Propagated Clock + Realistic Uncertainty
#######################################################################
puts "-> Switching to propagated clock model..."
set_propagated_clock [all_clocks]

# After CTS, uncertainty can be reduced since real skew is now modeled
set_clock_uncertainty -hold 0.05 [all_clocks]
set_clock_uncertainty -setup 0.10 [all_clocks]

# Update timing with the new propagated clock model
update_timing -full

#######################################################################
## 8. Remove Global Routes and Add Shielding
#######################################################################
puts "-> Applying physical shielding to clock nets..."
remove_routes -global_route
set clock_nets [get_nets -hierarchical -filter "net_type == clock"]
create_shields -nets ${clock_nets} -with_ground VSS

#######################################################################
## 9. Reconnect Power Nets and Verification
#######################################################################
puts "-> Reconnecting PG nets for newly inserted CTS buffers..."
connect_pg_net -net VDD [get_pins -hierarchical */VDD]
connect_pg_net -net VSS [get_pins -hierarchical */VSS]

# Check that standard cells and CTS buffers are placed legally
check_legality

#######################################################################
## 10. Generate CTS Reports & Save Milestone
#######################################################################
file mkdir v1/reports

# Comprehensive CTS quality reports
report_qor                                  > v1/reports/cts_qor.log
report_clock_qor                            > v1/reports/cts_clock_qor.log
report_clock_timing -type summary           > v1/reports/cts_clock_summary.log
report_clock_timing -type skew -nworst 10   > v1/reports/cts_skew.log
report_timing -delay max -max_paths 10      > v1/reports/cts_setup_timing.log
report_timing -delay min -max_paths 10      > v1/reports/cts_hold_timing.log

# Save the milestone block for the final Routing stage
save_block -as accelerator_top/cts

puts "========================================================="
puts " STEP 6: CLOCK TREE SYNTHESIS COMPLETED SUCCESSFULLY! "
puts " Block saved as: accelerator_top/cts "
puts "========================================================="
exit
exit