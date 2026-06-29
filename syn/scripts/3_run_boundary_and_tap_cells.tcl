#######################################################################
## 1. Library & Block Management
#######################################################################
# Clean memory to avoid file locks if running in an open shell
close_lib -purge -all
open_lib accelerator_synth.dlib

# Open the design block saved from the successful floorplan milestone
open_block accelerator_top/floorplan

puts "--- STARTING BOUNDARY AND TAP CELL INSERTION STAGE ---"

#######################################################################
## 2. Insert Boundary Cells
#######################################################################
puts "-> Inserting left and right boundary termination cells..."

# Add physical-only edge cells to protect edge transistors and ensure well/rail continuity
create_boundary_cells \
    -left_boundary_cell  tcbn28hpcplusbwp30p140/BOUNDARY_LEFTBWP30P140 \
    -right_boundary_cell tcbn28hpcplusbwp30p140/BOUNDARY_RIGHTBWP30P140 \
    -prefix BOUND

#######################################################################
## 3. Insert Tap Cells
#######################################################################
puts "-> Inserting substrate tap cells (TSMC 28nm spacing max 60um)..."

# Insert TAP cells to tie wells/substrate to VDD/VSS and prevent latch-up
create_tap_cells \
    -lib_cell tcbn28hpcplusbwp30p140/TAPCELLBWP30P140 \
    -distance 60 \
    -pattern stagger \
    -skip_fixed_cells

#######################################################################
## 4. Legalize Placement & Verify Legality
#######################################################################
puts "-> Legalizing placement and running checks..."

# Align the newly inserted cells cleanly to the standard cell rows and fix overlaps
legalize_placement -incremental

# Verify that all placement rules are fully satisfied
check_legality

#######################################################################
## 5. Verification & Reporting
#######################################################################
# Ensure output report directories exist safely
file mkdir v1/reports

# Query and count the total number of inserted boundary cells
set bnd_cells [get_cells -hierarchical -filter "name =~ BOUND*"]
puts "Boundary count = [sizeof_collection $bnd_cells]"

# Run signoff Design Rule Checking to ensure a clean layout database
signoff_check_drc > v1/reports/boundary_tap_drc.log

#######################################################################
## 6. Save Milestone Block
#######################################################################
# Save this milestone state before proceeding to the power grid (PG) definition
save_block -as accelerator_top/top_placed_with_tap_and_boundary

puts "========================================================="
puts " STEP 3: BOUNDARY & TAP CELLS INSTANTIATED SUCCESSFULLY! "
puts " Block saved as: accelerator_top/top_placed_with_tap_and_boundary "
puts "========================================================="
exit
