from thermodynamic_objects import *
from CoolProp.CoolProp import get_global_param_string

#%matplotlib auto

'''
Define input data firstly and run file.

Note: This calculator provides estimates only. Results may not always be accurate.
Don’t rely on the results without verifying them first.
'''
# calculation mode
run_simulation = True

run_SEPR_calculation = False
mode_use_declared = False # use declared capacity and power values

show_report = True

# compressor and condeser data
data_source = r'components_data.xlsx'
compressor_model = 'Compressor_B'
#compressor_model = 'Compressor_A'
freq = 80 # operation frequency / max compressor frequency, Hz

condenser_model = 'Condenser_A'
fan_model = 'Fan_A'
#condenser_model = 'Condenser_B'
#fan_model = 'Fan_B'

#refrigerant - in accordance with CoolProp FluidsList
ref = 'R404A'
#ref = 'R134a'

# opearting temperatures
t0 = -20 # evaporation temp, degC
ta = 38 # ambient temp, degC
sh_0 = 5 # useful/evaporator superheating

# define additional heat exchangers - 0 if no HEX in the system, temp max: 20
sub = 3 # designed subcooling temperature (provided by condesnser or additional subcooler)
Q_sub = 0.2 # subcooler capacity, kW
rhx = 3 # designed recuperator subcooling
Q_rhx = 0.2 # recuperator capacity, kW
ihx = 3 # designed internal HEX subcooling
sh_ihx = 5 # internal HEX superheating
Q_ihx = 0.3 # internal HEX capacity, kW

# SEPR calculations mode
mode_compressor = 'inverter' # 'inverter' / 'fixed'
mode_range = 'MT' # 'MT / 'LT'
mode = [mode_compressor.lower(), mode_range.upper()]

# declared capacity and values at pointa A, B, C, D
Qa, Qb, Qc, Qd = (None,) * 4     # kW
Pa, Pb, Pc, Pd = (None,) * 4    # kW 

declared_points = [Qa, Qb, Qc, Qd, Pa, Pb, Pc, Pd]

class RefrigerationSimulator():
    def __init__(self, run_simulation, run_SEPR_calculation, mode_use_declared, show_report,\
                 data_source, compressor_model, freq, condenser_model, fan_model, ref,\
                     t0, ta, sh_0, sub, rhx, ihx, sh_ihx,\
                         Q_sub, Q_rhx, Q_ihx,\
                            mode, declared_points):
        
        for key, value in locals().items():
            if key != "self":
                setattr(self, key, value)
        
        self.HEX_names = ['Q0 ', 'Qc ', 'Qsub', 'Qrhx', 'Qihx'] # to print results
        self.styler = '\n---------------------------------------------------------'
        
    def validate_input(self):
        # load data
        try:
            df_comp= pd.read_excel(self.data_source, "Compressors")
            df_cond = pd.read_excel(self.data_source, "Condensers")
        except FileNotFoundError:
            raise FileNotFoundError(f"Data source not found: {self.data_source}")
        except Exception as e:
            raise RuntimeError(f"Error reading Excel file: {e}")
        
        # refrigerant
        fluids = get_global_param_string("FluidsList")
        if self.ref not in fluids:
            	raise ValueError(f"Invalid refrigerant name: {self.ref}")
        
        # modes
        mode_compressor, mode_range = self.mode
        if mode_compressor.lower() not in ["inverter", "fixed"]:
            raise ValueError(
                f"Invalid compressor mode: {mode_compressor}\n"
                "Enter 'inverter' or 'fixed'."
            )
        if mode_range.upper() not in ["MT", "LT"]:
            raise ValueError(
                f"Invalid range mode: {mode_range}\n"
                "Enter 'MT' or 'LT'."
            )
        
        # models   
        compressors_list = df_comp['Compressor'].unique()
        condensers_list = df_cond['Model'].unique()
        fans_list = df_cond['Fan'].unique()
        
        if self.compressor_model not in compressors_list:
            	raise ValueError(f"Compressor model not found: {self.compressor_model}")
        
        if self.condenser_model not in condensers_list:
            	raise ValueError(f"Condenser model not found: {self.condenser_model}")
                              
        if self.fan_model not in fans_list:
            	raise ValueError(f"Fan model not found: {self.fan_model}")
        
        # models for selected refrigerant
        df_comp_sel = df_comp.loc[
            (df_comp['Compressor'] == self.compressor_model) &
            (df_comp['Refrigerant'].str.lower() == self.ref.lower())
        ]
                              
        df_cond_sel = df_cond.loc[
            (df_cond['Model'] == self.condenser_model) &
            (df_cond['Fan'] == self.fan_model) &
            (df_cond['Refrigerant'].str.lower() == self.ref.lower())
        ]
    
        if df_comp_sel.empty:
            raise ValueError(
                f"No compressor data for {self.compressor_model} with refrigerant {self.ref}"
            )
        if df_cond_sel.empty:
            raise ValueError(
                f"No condenser data for {self.condenser_model}/{self.fan_model} "
                f"with refrigerant {self.ref}"
            )  
        
        # temperatures
        limits = (0, 30)
        temp_checks = {
            "sh_0": self.sh_0,
            "sub": self.sub,
            "rhx": self.rhx,
            "ihx": self.ihx,
            "sh_ihx": self.sh_ihx
        }
        
        for name, value in temp_checks.items():
            if not (limits[0] <= value <= limits[1]):
                raise ValueError(
                    f"Invalid temperature input '{name}': {value} °C "
                    f"(must be between {limits[0]} and {limits[1]} °C)"
                )
        
        # if temp difference in HEX = 0 then capacity = 0
        self.Q_sub = 0 if self.sub == 0 else self.Q_sub
        self.Q_rhx = 0 if self.rhx == 0 else self.Q_rhx
        self.Q_ihx = 0 if self.ihx == 0 else self.Q_ihx
                
        cap_checks = {
             "Q_sub": self.Q_sub,
             "Q_rhx": self.Q_rhx,
             "Q_ihx": self.Q_ihx,
        }
         
        for name, value in cap_checks.items():
            if not limits[0] <= value:
                raise ValueError(
                    f"Invalid capacity input '{name}': {value} kW "
                    f"(must be above {limits[0]})"
                )
        
    def simulate_cycle(self, show_tips):
        ref = self.ref
        tc = self.ta + 15  # assumption for first iteration
        if tc < 20:
            tc = 20 #assumption of minimal condensation temperature
        
        pt13 = ThermodynamicPoint(ref, None, None, self.t0, 1) # evaporation at saturation = 1 pt13
        pt4 = ThermodynamicPoint(ref, None, None, tc, 0) # condensation at saturation = 0 pt4
        
        # calculation of capacity and power of compressor according to datasheet at required operating temperatures
        compressor_unit = CompressorSimulator(self.data_source, self.compressor_model, ref, self.t0, tc, self.freq)
        if self.mode[0] == "inverter":
            Q0, P = compressor_unit.get_QP_by_freq_approximation()
        elif self.mode[0] == "fixed":
            Q0, P = compressor_unit.get_QP_for_fixed_speed()
    
        # designation of volumetric efficiency of compressor for reference cycle according to datasheet
        # w/o any additional HEX, tsh_0 = 10, sub = 3
        compressor_cycle_sim = CycleSimulator(ref, pt13, pt4, None, None, P,\
                                              Q0, 10, None, 3, None, None, None, None, None)
        
        compressor_cycle_sim.simulate_datasheet_cycle()
        V = compressor_cycle_sim.V
        
        # simulation of designed cycle including additional exchangers and temperature parameters
        designed_cycle_sim = CycleSimulator(ref, pt13, pt4, None, V, P,\
                                            None, self.sh_0, self.Q_sub, self.sub, self.Q_rhx, self.rhx, self.Q_ihx, self.ihx, self.sh_ihx)
        
        designed_cycle_sim.simulate_cycle_by_temp()
        
        if show_tips:
            print("\nIf you simulate cycle and your iterations don't converge, consider coherence of the declared HEX capacities and the designed subcooling temperatures.")
            print("\nHEX Capacities calculated for first iteration:")
            initial_HEX_capacities = designed_cycle_sim.get_HEX_capacities()
    
            for name, capacity in zip(self.HEX_names, initial_HEX_capacities):
                print(f"{name:<5}{capacity:>8.2f} kW")
        
        # designate condensation temperarure for selected condenser
        tolerance, max_iter = 0.01, 100
        iteration = 0
        tc_prev = 0.9 * tc # assumption for first iteration 
    
        while abs(tc - tc_prev) > tolerance and iteration < max_iter:
            iteration += 1
            tc_prev = tc
            
            pt4 = ThermodynamicPoint(ref, None, None, tc, 0)
            
            compressor_unit = CompressorSimulator(self.data_source, self.compressor_model, ref, self.t0, tc, self.freq)
    
            if self.mode[0] == "inveretr":
                Q0, P = compressor_unit.get_QP_by_freq_approximation()
            elif self.mode[0] == "fixed":
                Q0, P = compressor_unit.get_QP_for_fixed_speed()
            
            # designation of volumetric efficiency
            compressor_cycle_sim = CycleSimulator(ref, pt13, pt4, None, None, P,\
                                                  Q0, 10, None, 3, None, None, None, None, None)
            
            compressor_cycle_sim.simulate_datasheet_cycle()
            V = compressor_cycle_sim.V
            
            # simulation of designed cycle
            designed_cycle_sim = CycleSimulator(ref, pt13, pt4, None, V, P,\
                                                None, self.sh_0, self.Q_sub, self.sub, self.Q_rhx, self.rhx, self.Q_ihx, self.ihx, self.sh_ihx)
    
            designed_cycle_sim.simulate_cycle_by_temp()
            
            # get suction side point for simulated cycle, density of pt1 involves mass flux for the compressor m=V*d
            pt1 = designed_cycle_sim.pt1
            
            # simulation of designed cycle as build unit including  components (HEX) declared capacities for simulated operating parameters
            designed_cycle_unit = CycleSimulator(ref, pt13, pt4, pt1, V, P,\
                         Q0, self.sh_0, self.Q_sub, self.sub, self.Q_rhx, self.rhx, self.Q_ihx, self.ihx, self.sh_ihx)
            
            designed_cycle_unit.simulate_cycle_by_capacity()
            
            # calculated condenser capaity for simulated cycle of build unit
            Qc = designed_cycle_unit.Qc
            condenser_sim = CondenserSimulator(self.data_source, self.condenser_model, self.fan_model, ref, self.t0, self.ta, Qc)
            tc = condenser_sim.calculate_condensation_temp()
              
            if iteration >= max_iter:
                raise RuntimeError("Condensation temperature did not converge after maximum iterations")
        
        designed_cycle_unit.tc = tc   
        return designed_cycle_unit
    
    def generate_report(self, simulation):
        cycle_points_unit = simulation.get_points()
        cycle_representation_unit = CycleRepresentation(self.ref, self.sub, self.rhx, self.ihx, cycle_points_unit)
        
        HEX_capacities = simulation.get_HEX_capacities()
        HEX_subcooling = simulation.get_subcooling()
        
        print("\nCalculated HEX capacities:")
        for name, capacity in zip(self.HEX_names, HEX_capacities):
            print(f"{name:<5}{capacity:>8.2f} kW")
            
        print("\nDesigned system sucooling:\n(sub -- rhx -- ihx)") 
        print(tuple(round(x, 2) for x in HEX_subcooling))
        
        print("\nDischarge temp t_dis:\n", round(simulation.pt2.t, 2), "°C")
        print("Condensation temp t_c:\n", round(simulation.tc, 2), "°C")
         
        cycle_representation_unit.generate_table()
        cycle_representation_unit.generate_plot()
    
    def calculate_SEPR(self):
        sepr = CoefficientSEPR(self.data_source, self.mode, self.declared_points)
        
        # get evaporation and ambient temperatures for declared mode
        self.t0 = sepr.df_cop.at[0, 't0']
        ambient_temp = sepr.df_cop['ambient'].tolist()
        
        if self.mode_use_declared:
            coeff_sepr = sepr.calculate_coefficient()
        else:
            if self.mode[0] == "inverter":
                freq_min = 20 # assumed minimal compressor frequency, Hz
                
                self.ta = ambient_temp[0]
                part_loads = sepr.df_cop['part load'].tolist()
                points = sepr.df_cop['point'].tolist()
                
                sepr_simulation = self.simulate_cycle(show_tips = False)
                self.Qa, self.Pa = sepr_simulation.Q0, sepr_simulation.P * 1e-3
                calculated_points = [self.Qa, self.Pa]
                frequencies = [self.freq]
                
                if self.show_report:
                    print("\nPoint A")
                    print("Copmpressor max frequency - ", frequencies[0], "Hz", self.styler)
                    self.generate_report(sepr_simulation)
                            
                # iteration to find compressor freqency at desired capacity for points B, C, D
                for i, t in enumerate(ambient_temp[1:]):
                    self.ta = t
                    Q = self.Qa * part_loads[i+1]
                    self.freq -= 1
                    tolerance = 0.2
    
                    sepr_simulation = self.simulate_cycle(show_tips = False)
                    Qi, Pi = sepr_simulation.Q0, sepr_simulation.P * 1e-3
                    
                    while abs(Q - Qi) > tolerance:
                        self.freq -= 1
                        
                        if self.freq < freq_min:
                            raise ValueError("Frequency did not converge above minimum frequency value.")
                        
                        sepr_simulation = self.simulate_cycle(show_tips = False)
                        Qi, Pi = sepr_simulation.Q0, sepr_simulation.P * 1e-3                   
                    
                    calculated_points.extend([Qi, Pi])
                    frequencies.extend([self.freq])
                    
                    if self.show_report:
                        print("\nPoint", points[i+1])
                        print("Designated copmpressor frequency - ", frequencies[i+1], "Hz", self.styler)
                        self.generate_report(sepr_simulation)
              
            elif self.mode[0] == "fixed":
                calculated_points = []
                
                for t in ambient_temp:
                    self.ta = t
                    try:
                        sepr_simulation = self.simulate_cycle(show_tips = False)
                    except ValueError as e:
                        if "Compression ratio below 2" in str(e):
                            self.ta +=1
                        else:
                            raise
        
                    Qi, Pi =  sepr_simulation.Q0, sepr_simulation.P * 1e-3
                    calculated_points.extend([Qi, Pi])
                
            sepr.declared_points = calculated_points[0::2] + calculated_points[1::2]
            coeff_sepr = sepr.calculate_coefficient()
                
    
        if self.show_report:
            print('\nSummary', self.styler)
            print(sepr.df_cop[['point', 'ambient', 'Q', 'P', 'COP_DC', ]].round(2))
            print("\nCalculated SEPR value:", round(coeff_sepr, 2))
       
    
    def run_simulator(self):
        self.validate_input()

        if self.run_simulation:
            self.cycle_sim = self.simulate_cycle(show_tips = True)
            
            if self.show_report:
                self.generate_report(self.cycle_sim)
            
        if self.run_SEPR_calculation:
            self.calculate_SEPR()
if __name__ == "__main__":
    
    sim = RefrigerationSimulator(run_simulation, run_SEPR_calculation, mode_use_declared, show_report,\
                                 data_source, compressor_model, freq, condenser_model, fan_model, ref,\
                                     t0, ta, sh_0, sub, rhx, ihx, sh_ihx,\
                                         Q_sub, Q_rhx, Q_ihx,\
                                             mode, declared_points)
    sim.run_simulator()
                                        
