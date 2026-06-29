#######################################################################
## Accelerator Top - Synopsys Design Constraints (SDC)
## Target: 400MHz, TSMC 28nm
#######################################################################

#######################################################################
## 1. Clock Definition (400MHz Target)
#######################################################################
# Period of 2.5ns = 400MHz
create_clock -name clk -period 2.5 [get_ports clk]

# Clock uncertainty (pre-CTS pessimism for skew estimation)
set_clock_uncertainty 0.2 [get_clocks clk]

# Expected clock transition time at sinks
set_clock_transition  0.1 [get_clocks clk]

#######################################################################
## 2. Input/Output Delays (I/O Constraints)
#######################################################################
# I/O delay budget set to 20% of the clock period (0.5ns)
set_input_delay  -max 0.5 -clock clk [remove_from_collection [all_inputs] [get_ports clk]]
set_output_delay -max 0.5 -clock clk [all_outputs]

#######################################################################
## 3. Design Environment
#######################################################################
# Output load capacitance
set_load 0.05 [all_outputs]

# Driving cell for inputs (models external driver strength)
set_driving_cell -lib_cell INVD2BWP30P140 [all_inputs]

#######################################################################
## 4. Design Rule Constraints (CRITICAL FOR CTS!)
#######################################################################
# Maximum transition time across the entire design (150ps)
# Prevents slow rise/fall times that hurt timing and signal integrity
set_max_transition 0.15 [current_design]

# Stricter transition constraint on clock paths (100ps)
# Forces CTS to insert sufficient buffers for clean clock edges
set_max_transition 0.10 -clock_path [get_clocks clk]

# Maximum capacitance on any net (150fF)
# Prevents excessive load that slows down signals
set_max_capacitance 0.15 [current_design]

# Maximum fanout limit
# Forces CTS to branch the clock tree properly instead of overloading buffers
set_max_fanout 32 [current_design]

#######################################################################
## 5. Optimization Constraints
#######################################################################
# Area optimization goal (0 means minimize as much as possible)
set_max_area 0
