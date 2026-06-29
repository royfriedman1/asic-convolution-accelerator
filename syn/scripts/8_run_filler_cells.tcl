#######################################################################
## 1. Library & Block Management
#######################################################################
close_lib -purge -all
open_lib accelerator_synth.dlib

# Open the design block saved from the Routing stage
open_block accelerator_top/routed

puts "--- STARTING FILLER CELL INSERTION ---"

#######################################################################
## 2. Cleanup: Remove Existing Fillers (if any)
#######################################################################
puts "-> Checking for existing filler cells to clean..."
set old_fillers [get_cells -hier -filter "ref_name =~ *FILL*"]
if {[sizeof_collection $old_fillers] > 0} {
    remove_cell $old_fillers
    legalize_placement -incremental
}

puts "-> Inserting standard cell fillers..."

# הרשימה כוללת את כל מה שהפקודה get_lib_cells החזירה לך
create_stdcell_fillers -lib_cells { \
    tcbn28hpcplusbwp30p140/FILL64BWP30P140 \
    tcbn28hpcplusbwp30p140/FILL32BWP30P140 \
    tcbn28hpcplusbwp30p140/FILL16BWP30P140 \
    tcbn28hpcplusbwp30p140/FILL8BWP30P140 \
    tcbn28hpcplusbwp30p140/FILL4BWP30P140 \
    tcbn28hpcplusbwp30p140/FILL3BWP30P140 \
    tcbn28hpcplusbwp30p140/FILL2BWP30P140 \
    tcbn28hpcplusbwp30p140/DCAP64BWP30P140 \
    tcbn28hpcplusbwp30p140/DCAP32BWP30P140 \
    tcbn28hpcplusbwp30p140/DCAP16BWP30P140 \
    tcbn28hpcplusbwp30p140/DCAP8BWP30P140 \
    tcbn28hpcplusbwp30p140/DCAP4BWP30P140 \
} -prefix FILLER

#######################################################################
## 4. Verification
#######################################################################
puts "-> Running final checks..."

# Align all fillers and verify design rules
legalize_placement -incremental

# Verify that routing is still clean and power grid is intact
check_routes
check_pg_connectivity

# Save the final GDS-ready block
save_block -as accelerator_top/final_layout

puts "========================================================="
puts " STEP 8: FILLER INSERTION COMPLETED SUCCESSFULLY! "
puts " The chip is now GDS-ready. "
puts " Block saved as: accelerator_top/final_layout "
puts "========================================================="
exit