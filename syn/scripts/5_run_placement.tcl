#######################################################################
## 1. Library & Block Management
#######################################################################
# Clean memory to avoid file locks
close_lib -purge -all
open_lib accelerator_synth.dlib

# Open the design block saved from the Power Grid stage
open_block accelerator_top/power_grid_done

puts "--- STARTING PLACEMENT & OPTIMIZATION STAGE ---"

#######################################################################
## 2. Application Setup for Placement
#######################################################################
# Allow flow to continue even if DFT (ScanDEF) is missing
set_app_options -name place.coarse.continue_on_missing_scandef -value true 

# Set high effort for better timing, area, and routability
set_app_options -name place_opt.final_place.effort -value high 
set_app_options -name place_opt.place.congestion_effort -value high 

# Add a prefix to all new cells (like buffers/inverters) inserted by the tool
set_app_options -name opt.common.user_instance_name_prefix -value place_opt 

#######################################################################
## 3. Core Placement & Optimization Execution
#######################################################################
puts "-> Running Placement Optimization (place_opt)..."

# This command performs coarse placement, timing-driven optimization, 
# buffering, and initial legalization all in one powerful step.
place_opt

#######################################################################
## 4. Legality Check & Incremental Legalization
#######################################################################
puts "-> Legalizing and generating placement reports..."

# Resolve any minor overlaps caused by the optimization engine
legalize_placement -incremental 

#######################################################################
## 5. Power and Ground Connectivity for New Cells
#######################################################################
puts "-> Connecting new optimization cells to Power Grid..."

# Critical step: tie any newly inserted buffers/inverters to VDD/VSS
connect_pg_net -net VDD [get_pins -hierarchical */VDD] 
connect_pg_net -net VSS [get_pins -hierarchical */VSS] 

#######################################################################
## 6. Final Checks, Reports, and Save
#######################################################################
file mkdir v1/reports

# Validate that the design is 100% legal and ready for routing/CTS
check_legality 
report_congestion > v1/reports/placement_congestion.log
report_utilization > v1/reports/placement_utilization.log

# Save the milestone block for Clock Tree Synthesis
save_block -as accelerator_top/placement

puts "========================================================="
puts " STEP 5: PLACEMENT & OPTIMIZATION COMPLETED SUCCESSFULLY! "
puts " Block saved as: accelerator_top/placement "
puts "========================================================="
exit
