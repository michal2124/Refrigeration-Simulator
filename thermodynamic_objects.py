import numpy as np
import pandas as pd
import CoolProp.CoolProp as CP
import matplotlib.pyplot as plt 
from matplotlib.ticker import MultipleLocator

class ThermodynamicPoint:
    def __init__(self, ref, h, p, t, Q):
        self.ref = ref
        self.h = h #kJ
        self.p = p #bar (absolute)
        self.t = t #degC
        self.Q = Q #0-1
        
    def convert_p(self, value, from_unit = "bar", to_unit = "pa"): 
        conversions = {
            ("bar", "pa"): value * 10**5,
            ("pa", "bar"): value / 10**5,
        }
        return conversions.get((from_unit.lower(), to_unit.lower()), None)

    def convert_h(self, value, from_unit = "kJ", to_unit = "J"):
        conversions = {
            ("kJ", "J"): value * 10**3,
            ("J", "kJ"): value / 10**3,
        }
        return conversions.get((from_unit, to_unit), None)
    
    def convert_t(self, value, from_unit = "C", to_unit = "K"):
        conversions = {
            ("C", "K"): value + 273.15,
            ("K", "C"): value - 273.15,
        }
        return conversions.get((from_unit, to_unit), None) 

    def get_h_by_tQ(self):
        h = CP.PropsSI('H', 'T', self.convert_t(self.t), 'Q', self.Q, self.ref)
        self.h = self.convert_h(h, 'J', 'kJ')
        
    def get_h_by_pt(self):
        h = CP.PropsSI('H', 'P', self.convert_p(self.p), 'T', self.convert_t(self.t), self.ref)
        self.h = self.convert_h(h, 'J', 'kJ')
        
    def get_h_by_pQ(self):
        h = CP.PropsSI('H', 'P', self.convert_p(self.p), 'Q', self.Q, self.ref)
        self.h = self.convert_h(h, 'J', 'kJ')
        
    def get_p_by_tQ(self):
        p = CP.PropsSI('P', 'T', self.convert_t(self.t), 'Q', self.Q, self.ref)
        self.p = self.convert_p(p, 'pa', 'bar')
        
    def get_t_by_hp(self):
        t = CP.PropsSI('T', 'H', self.convert_h(self.h), 'P', self.convert_p(self.p), self.ref)
        self.t = self.convert_t(t, 'K', 'C')
        
    def get_t_by_pQ(self):
        t = CP.PropsSI('T', 'P', self.convert_p(self.p), 'Q', self.Q, self.ref)
        self.t = self.convert_t(t, 'K', 'C')
        
    def get_d_by_pt(self):
        self.d = CP.PropsSI('D', 'P', self.convert_p(self.p), 'T', self.convert_t(self.t), self.ref)

class CompressorSimulator():
    '''
    A class based on selected compressor and required operating paramters.
    Calculates Capacity and Power for fixed speed compressors according to polynomials provided by data source.
    For inverter compressors generates Capacity and Power models according to the polynomials.
    Models enable to approximate Capacity and Power  for required frequency.
    '''
    def __init__(self, data_source, name, ref, t0, tc, freq):
        self._t0 = t0
        self._tc = tc
        self._freq = freq # Compressor calculated frequency, not required for fixed speed compressors
        
        df = pd.read_excel(data_source, "Compressors")
        df = df.loc[
            (df['Compressor'] == name) &
            (df['Refrigerant'].str.lower() == ref.lower())
        ]
        self._df_comp = df
        

    def create_model(self):
        df_comp = self._df_comp
        
        freq_list = df_comp.loc[df_comp['Capacity/Power'] == "Q", 'Frequency'].tolist()
        Q_list, P_list = [], []
        e, c = self._t0, self._tc
        
        X_cols = [f"X{i}" for i in range(1, 11)] # polynomials columns names
        
        grouped = df_comp.groupby(["Frequency", "Capacity/Power"])
        
        for freq in freq_list:
            try:
                Xq = grouped.get_group((freq, "Q"))[X_cols].iloc[0]
                Xp = grouped.get_group((freq, "P"))[X_cols].iloc[0]
            except KeyError:
                # Skip if frequency or group doesn't exist
                continue
            
            Q = (
                Xq["X1"]
                + Xq["X2"] * e
                + Xq["X3"] * c
                + Xq["X4"] * e**2
                + Xq["X5"] * e * c
                + Xq["X6"] * c**2
                + Xq["X7"] * e**3
                + Xq["X8"] * c * e**2
                + Xq["X9"] * e * c**2
                + Xq["X10"] * c**3
            )
    
            P = (
                Xp["X1"]
                + Xp["X2"] * e
                + Xp["X3"] * c
                + Xp["X4"] * e**2
                + Xp["X5"] * e * c
                + Xp["X6"] * c**2
                + Xp["X7"] * e**3
                + Xp["X8"] * c * e**2
                + Xp["X9"] * e * c**2
                + Xp["X10"] * c**3
            )
    
            Q_list.append(Q)
            P_list.append(P)
        
        power_of = 2
        
        self._Q_model = np.poly1d(np.polyfit(freq_list, Q_list, power_of))
        self._P_model = np.poly1d(np.polyfit(freq_list, P_list, power_of))
    
    def get_QP_by_freq_approximation(self):
        self.create_model()
        
        Q = self._Q_model(self._freq)
        P = self._P_model(self._freq)

        return Q, P
    
    def get_QP_for_fixed_speed(self):
        df_comp = self._df_comp
        
        match = df_comp.loc[df_comp['Capacity/Power'] == "Q", 'Frequency']
        if not match.empty:
            freq = match.iloc[0]
        else:
            raise ValueError("Invalid input data. Check compressor frequency.")
        
        e, c = self._t0, self._tc
        
        X_cols = [f"X{i}" for i in range(1, 11)] # polynomials columns names
        grouped = df_comp.groupby(["Frequency", "Capacity/Power"])
        
        Xq = grouped.get_group((freq, "Q"))[X_cols].iloc[0]
        Xp = grouped.get_group((freq, "P"))[X_cols].iloc[0]

        Q = (
            Xq["X1"]
            + Xq["X2"] * e
            + Xq["X3"] * c
            + Xq["X4"] * e**2
            + Xq["X5"] * e * c
            + Xq["X6"] * c**2
            + Xq["X7"] * e**3
            + Xq["X8"] * c * e**2
            + Xq["X9"] * e * c**2
            + Xq["X10"] * c**3
        )
        P = (
            Xp["X1"]
            + Xp["X2"] * e
            + Xp["X3"] * c
            + Xp["X4"] * e**2
            + Xp["X5"] * e * c
            + Xp["X6"] * c**2
            + Xp["X7"] * e**3
            + Xp["X8"] * c * e**2
            + Xp["X9"] * e * c**2
            + Xp["X10"] * c**3
        )
        
        return Q, P

class CondenserSimulator():
    '''
    A class based on selected condenser and required operating paramters.
    Calculates condensation temperature according to capacity and temperature difference provided by data source (condenser datasheet).
    '''
    def __init__(self, data_source, name, fan_option, ref, t0, ta, Q):
        self._ref = ref
        self._t0 = t0
        self._ta = ta
        self._Q = Q # Condenser capacity
        self._tc_min = 20 # Minimum condensation temperature
        
        df = pd.read_excel(data_source, "Condensers")
        df = df.loc[
            (df['Model'] == name) &
            (df['Fan'] == fan_option) &
            (df['Refrigerant'].str.lower() == ref.lower())
        ]
        self._df_cond = df
        
    def calculate_condensation_temp(self):
        Q_ref = self._df_cond.iloc[0]['Capacity'] * 1e-3 # get condenser capacity from data source, converted to kW
        dt_ref = self._df_cond.iloc[0]['Tc'] - self._df_cond.iloc[0]['Ta'] # get temp difference for reference capacity
        
        tc = self._Q/Q_ref * dt_ref + self._ta #Q=kAdt => Q_ref/dt_ref = Q/(tc - ta)
        
        pt0 = ThermodynamicPoint(self._ref, None, None, self._t0, 1) # evaporation pressure point
        ptc = ThermodynamicPoint(self._ref, None, None, tc, 0) # condensation pressure point
        
        pt0.get_p_by_tQ()
        ptc.get_p_by_tQ()
        ratio = ptc.p/pt0.p
        
        if ratio < 2: # condensation pressure increase to provide compression ratio above 2
            pc_min = pt0.p*2
            ptc_min = ThermodynamicPoint(self._ref, None, pc_min, None, 0)
            ptc_min.get_t_by_pQ()
            tc = ptc_min.t
        if tc < self._tc_min: # condensation pressure increase to provide correct operation
            tc = self._tc_min
        self.tc = tc
        return tc

class CycleSimulator():
    '''
    A class represents refrigeration cycle according to declared input values.
    A class can represents:
    - compressor reference cycle according to datasheet operating conditions (used to calculate compressor efficiency V)
    - defined cycle according to declared temperatures for heat exchangers (used to designate compressor suction side point)
    - defined cycle according to declared capacities of heat exchangers (used to designate heat exchangers capacities)
    Compressor reference cycle is calculated according to superheating and subcooling temperatures, with no additional HEX.
    '''
    def __init__(self, ref, pt0, ptc, ptss, V, P,\
                 Q0, sh_0, Qsub, sub, Qrhx, rhx, Qihx, ihx, sh_ihx):
        for key, value in locals().items():
            if key != "self":
                setattr(self, key, value)
                
        self.pt13 = self.pt0
        self.pt4 = self.ptc
        self.t_dis_max = 110 # max allowable discharge temperature        
    
    def simulate_datasheet_cycle(self):
        self.pt13.get_p_by_tQ() # evaporation at saturation = 1 pt13
        self.pt13.get_h_by_tQ()
        self.pt4.get_p_by_tQ() # condensation at saturation = 0 pt4
        self.pt4.get_h_by_tQ()
        
        if self.pt13.p < 1:
            raise ValueError('Evaporation pressure below 1 bar(atm):', self.pt13.p)

        ratio = self.pt4.p/self.pt13.p
        if ratio < 2:
            raise ValueError('Compression ratio below 2:', ratio)
            
        # subcooler pt4, pt5
        if self.sub != 0:
            t5 = self.pt4.t - self.sub
            self.pt5 = ThermodynamicPoint(self.ref, None, self.pt4.p, t5, None)
            self.pt5.get_h_by_pt()
        else:
            self.pt5 = self.pt4
            
        # throttling pt12, assumption that reference cycle has neither Internal HEX nor Recuperator  
        self.pt12 = ThermodynamicPoint(self.ref, self.pt5.h, self.pt13.p, None, None)
        self.pt12.get_t_by_hp()
        
        # compressor suction side, pt1, assumption that suction side equals evaporator superheating
        tss = self.pt13.t + self.sh_0
        self.pt1 = ThermodynamicPoint(self.ref, None, self.pt13.p, tss, None)
        self.pt1.get_h_by_pt()
        self.pt1.get_d_by_pt()
        dss = self.pt1.d
        
        # evaporator capacity
        q0 = self.pt1.h-self.pt12.h
        m = self.Q0/q0 * 1e-3 # Q0 converted to kW
        
        # compressor efficiency
        l = self.P/m # J/kg
        self.V = (m/dss) * 3600 # converted to m3/h
        
        # compressor discharge pt2
        h2 = self.pt1.h + l*1e-3
        self.pt2 = ThermodynamicPoint(self.ref, h2, self.pt4.p, None, None)
        self.pt2.get_t_by_hp()
        
        if self.pt2.t > self.t_dis_max:
            raise ValueError("Discharge above 110'C:", self.pt2.t)
        
        # condensation at saturation = 1 pt3
        self.pt3 = ThermodynamicPoint(self.ref, None, self.pt4.p, None, 1)
        self.pt3.get_h_by_pQ()
        self.pt3.get_t_by_pQ()

    def simulate_cycle_by_temp(self):
        self.V = self.V / 3600 # converted to m3/s 
        self.pt13.get_p_by_tQ() # evaporation at saturation = 1 pt13
        self.pt13.get_h_by_tQ()
        self.pt4.get_p_by_tQ() # condensation at saturation = 0 pt4
        self.pt4.get_h_by_tQ()
        
        if self.pt13.p < 1:
            raise ValueError('Evaporation pressure below 1 bar(atm):', self.pt13.p)
            
        ratio = self.pt4.p/self.pt13.p
        if ratio < 2:
            raise ValueError('Compression ratio below 2:', ratio)
        
        # subcooler pt4, pt5
        if self.sub != 0:
            t5 = self.pt4.t - self.sub
            self.pt5 = ThermodynamicPoint(self.ref, None, self.pt4.p, t5, None)
            self.pt5.get_h_by_pt()
        else:
            self.pt5 = self.pt4
            
        # internal HEX primary side pt10
        if self.ihx != 0:
            t10 = self.pt5.t - self.ihx
            self.pt10 = ThermodynamicPoint(self.ref, None, self.pt4.p, t10, None)
            self.pt10.get_h_by_pt()
        else:
            self.pt10 = self.pt5
            
        # recuperator liquid side pt11
        if self.rhx != 0:
            t11 = self.pt10.t - self.rhx
            self.pt11 = ThermodynamicPoint(self.ref, None, self.pt4.p, t11, None)
            self.pt11.get_h_by_pt()
        else:
            self.pt11 = self.pt10

        # throttling, evaporator inlet pt12 
        self.pt12 = ThermodynamicPoint(self.ref, self.pt11.h, self.pt13.p, None, None)
        self.pt12.get_t_by_hp()
        
        # internal HEX secondary side pt6, pt7, pt8. pt9
        if self.ihx != 0:
            p6 = (self.pt13.p*self.pt4.p)**0.5
            self.pt6 = ThermodynamicPoint(self.ref, self.pt5.h, p6, None, None)
            self.pt6.get_t_by_hp()
            
            self.pt7 = ThermodynamicPoint(self.ref, None, p6, None, 1)
            self.pt7.get_h_by_pQ()
            self.pt7.get_t_by_pQ()
            
            t8 = self.pt7.t + self.sh_ihx
            self.pt8 = ThermodynamicPoint(self.ref, None, p6, t8, None)
            self.pt8.get_h_by_pt()
               
            self.pt9 = ThermodynamicPoint(self.ref, self.pt8.h, self.pt13.p, None, None)
            self.pt9.get_t_by_hp()
        
        # evaporator outlet pt14
        t14 = self.pt13.t + self.sh_0
        self.pt14 = ThermodynamicPoint(self.ref, None, self.pt13.p, t14, None)
        self.pt14.get_h_by_pt()
        
        # evaporator capacity
        self.q0 = self.pt14.h - self.pt12.h
        
        # compressor suction side pt1
        self.pt14.get_d_by_pt()
        
        self.calculate_suction_side_density()
        
        l = self.P/(self.V*self.pt1.d) #J/kg
            
        # compressor discharge pt2
        h2 = self.pt1.h + l*1e-3
        self.pt2 = ThermodynamicPoint(self.ref, h2, self.pt4.p, None, None)
        self.pt2.get_t_by_hp()
    
        if self.pt2.t > self.t_dis_max:
            raise ValueError("Discharge above 110'C:", self.pt2.t)
         
        # condensation at saturation = 1 pt3
        self.pt3 = ThermodynamicPoint(self.ref, None, self.pt4.p, None, 1)
        self.pt3.get_h_by_pQ()
        self.pt3.get_t_by_pQ()
                     
    def calculate_suction_side_density(self, tol=0.2, max_iter=100):
        dss_current = self.pt14.d
        dss_previous = 0.9 * dss_current
        iteration = 0
    
        while abs(dss_current - dss_previous) > tol and iteration < max_iter:
            iteration += 1
            dss_previous = dss_current
    
            self.calculate_mass_flow(dss_current)
    
            h1 = None
    
            if self.rhx != 0: # cycle includes recuperator
                h15 = (self.pt10.h - self.pt11.h) + self.pt14.h # enthalpy difference equals due to the same mass flow in both recuperator sides
                self.pt15 = ThermodynamicPoint(self.ref, h15, self.pt13.p, None, None)
                self.pt15.get_t_by_hp()
    
                if self.ihx != 0: # cycle has both recuperator and internal HEX
                    h1 = (self.m2 * self.pt9.h + self.m1 * self.pt14.h)/self.m # m1*h15 + m2*h9 = m*h1
                else: # recuperator only
                    self.pt1 = self.pt15
            else:
                if self.ihx != 0: # internal HEX only
                    h1 = (self.m2 * self.pt9.h + self.m1 * self.pt14.h) / self.m
                else: # no recuperator or internal HX
                    self.pt1 = self.pt14
    
            if h1 is not None:
                self.pt1 = ThermodynamicPoint(self.ref, h1, self.pt13.p, None, None)
    
            self.pt1.get_t_by_hp()
            self.pt1.get_d_by_pt()
    
            dss_current = self.pt1.d
    
        if iteration >= max_iter:
            raise RuntimeError("Cycle did not converge after maximum iterations")

    def calculate_mass_flow(self, dss, tol=0.002, max_iter=10000):
        mc = self.V * dss
            
        if self.ihx != 0:
            m1 = 0.7 * mc
            ratio = (self.pt6.h - self.pt10.h) / (self.pt8.h - self.pt6.h)
            m2 = m1 * ratio
            m_total = m1 + m2
        
            # iteratively adjust until total flow converges
            iteration = 0
            increment = 1e-4
            while abs(mc - m_total) > tol and iteration < max_iter:
                m1 *= (1 + increment)
                m2 = m1 * ratio
                m_total = m1 + m2
                iteration += 1
        
            if iteration == max_iter:
                raise RuntimeError("Cycle did not converge after maximum iterations")
        
            self.m = m_total
            self.m1 = m1
            self.m2 = m2
            self.Q0 = self.q0 * m1
        else:
            self.m = mc
            self.m1 = mc
            self.m2 = 0
            self.Q0 = self.q0 * self.m
                
    def simulate_cycle_by_capacity(self):
        self.V = self.V / 3600 # converted to m3/s 
        self.pt13.get_p_by_tQ() # evaporation at saturation = 1 pt13
        self.pt13.get_h_by_tQ()
        self.pt4.get_p_by_tQ() # condensation at saturation = 0 pt4
        self.pt4.get_h_by_tQ()
        
        if self.pt13.p < 1:
            raise ValueError('Evaporation pressure below 1 bar(atm):', self.pt13.p)
            
        self.m, self.m1, self.m2 = self.calculate_cycle_points() # calculation mass flux for evaporator and internal HEX
        
        l = self.P/(self.V * self.pt1.d) #J/kg
        
        # compressor discharge pt2
        h2 = self.pt1.h + l*1e-3
        self.pt2 = ThermodynamicPoint(self.ref, h2, self.pt4.p, None, None)
        self.pt2.get_t_by_hp()
    
        if self.pt2.t > self.t_dis_max:
            raise ValueError("Discharge above 110'C:", self.pt2.t)
         
        # condensation at saturation = 1 pt3
        self.pt3 = ThermodynamicPoint(self.ref, None, self.pt4.p, None, 1)
        self.pt3.get_h_by_pQ()
        self.pt3.get_t_by_pQ()
        
        qc = self.pt2.h - self.pt4.h
        self.Qc = self.m * qc
 
    def calculate_cycle_points(self, tol=0.01, max_iter=100):
        iteration = 0           
        dss_prev = 0.7 * self.ptss.d
        
        m = m1 = m2 = 0.0
        
        while abs(self.ptss.d - dss_prev) > tol and iteration < max_iter:
            iteration += 1
            dss_prev = self.ptss.d
            m = self.V * self.ptss.d
            
            # subcooler pt4, pt5
            h5 = self.pt4.h - self.Qsub/m
            self.pt5 = ThermodynamicPoint(self.ref, h5, self.pt4.p, None, None)
            self.pt5.get_t_by_hp()
            
            # internal HEX secondary side pt6, pt7, pt8, pt9
            if self.Qihx > 0:               
                p6 = (self.pt13.p * self.pt4.p)**0.5
                self.pt6 = ThermodynamicPoint(self.ref, self.pt5.h, p6, None, None)
                self.pt6.get_t_by_hp()
                
                self.pt7 = ThermodynamicPoint(self.ref, None, p6, None, 1)
                self.pt7.get_h_by_pQ()
                self.pt7.get_t_by_pQ()
                
                t8 = self.pt7.t + self.sh_ihx
                self.pt8 = ThermodynamicPoint(self.ref, None, p6, t8, None)
                self.pt8.get_h_by_pt()
                
                self.pt9 = ThermodynamicPoint(self.ref, self.pt8.h, self.pt13.p, None, None)
                self.pt9.get_t_by_hp()
                
                m2 = self.Qihx/(self.pt8.h - self.pt6.h) #Q = m * dh
            else:
                m2 = 0

            m1 = m - m2

            # internal HEX primary side pt10
            h10 = self.pt5.h - self.Qihx/m1  #Q = m * dh
            self.pt10 = ThermodynamicPoint(self.ref, h10, self.pt4.p, None, None)
            self.pt10.get_t_by_hp()
            
            # recuperator liquid side pt11
            h11 = self.pt10.h - self.Qrhx/m1 #Q = m * dh
            self.pt11 = ThermodynamicPoint(self.ref, h11, self.pt4.p, None, None)
            self.pt11.get_t_by_hp()
            
            # throttling, evaporator inlet pt12 
            self.pt12 = ThermodynamicPoint(self.ref, h11, self.pt13.p, None, None)
            self.pt12.get_t_by_hp()
            
            # evaporator outlet pt14
            t14 = self.pt13.t + self.sh_0
            self.pt14 = ThermodynamicPoint(self.ref, None, self.pt13.p, t14, None)
            self.pt14.get_h_by_pt()
            
            # evaporator capacity
            q0 = self.pt14.h-self.pt12.h
            self.Q0 = q0 * m1
            
            #evaporator outlet pt14
            h15 = self.pt14.h + self.Qrhx/m1 #Q = m * dh
            self.pt15 = ThermodynamicPoint(self.ref, h15, self.pt13.p, None, None)
            self.pt15.get_t_by_hp()
            
            if getattr(self, "pt9", None) is not None:
                h1 = (m1 * self.pt15.h + m2 * self.pt9.h)/m
                self.pt1 = ThermodynamicPoint(self.ref, h1, self.pt13.p, None, None)
            else:
                self.pt1 = self.pt15
            
            self.pt1.get_t_by_hp()
            self.pt1.get_d_by_pt()
            self.ptss.d = self.pt1.d
            
        if iteration >= max_iter:
            raise RuntimeError("Cycle did not converge after maximum iterations")

         
        return m, m1, m2
    
    def get_points(self):
        if getattr(self, "pt6", None) is None:
            self.pt6, self.pt7, self.pt8, self.pt9 = [None]*4
        if getattr(self, "pt15", None) is None:
            self.pt15 = None
      
        return self.pt1, self.pt2, self.pt3, self.pt4, self.pt5,\
                self.pt6, self.pt7, self.pt8, self.pt9, self.pt10,\
                self.pt11, self.pt12, self.pt13, self.pt14, self.pt15
                
    def get_HEX_capacities(self):
        self.Qc = self.m * (self.pt2.h - self.pt4.h)
        self.Qsub = self.m * (self.pt4.h - self.pt5.h)
        
        if not(self.ihx):
            self.m1 = self.m
            
        self.Qihx = self.m1 * (self.pt5.h - self.pt10.h)
        self.Qrhx = self.m1 * (self.pt10.h - self.pt11.h)
        
        return self.Q0, self.Qc, self.Qsub, self.Qrhx, self.Qihx
    
    def get_subcooling(self):
        self.sub = self.pt4.t - self.pt5.t
        
        if self.Qihx > 0:
            self.ihx = self.pt5.t - self.pt10.t
        else:
            self.ihx = 0
            self.pt10 = self.pt5

        self.rhx = self.pt10.t - self.pt11.t

        return self.sub, self.rhx, self.ihx

class CycleRepresentation():
    '''
    A class used to represent cycle points on a log p-h chart or as a tabular data with h,p,t parameters.
    '''
    def __init__(self, ref, sub, rhx, ihx, cycle_points):
        self.ref = ref
        self.sub = sub
        self.ihx = ihx
        self.rhx = rhx
        self.cycle_points = cycle_points
        
        if len(cycle_points) != 15:
            raise ValueError ("Invalid cycle points data. Provide 15 points.")
            
        for i, point in enumerate(cycle_points, start=1):
            setattr(self, f"pt{i}", point)

    def generate_table(self):
        points = self.cycle_points
        
        def safe_attr(obj, attr):
            return getattr(obj, attr, np.nan) if obj is not None else np.nan
    
        # Build DataFrame with safe attribute extraction
        data = {
            "Point": [str(i + 1) for i in range(len(points))],
            "Pressure [bar]": [safe_attr(p, "p") for p in points],
            "Temperature [°C]": [safe_attr(p, "t") for p in points],
            "Enthalpy [kJ/kg]": [safe_attr(p, "h") for p in points],
        }
        
        df_points = pd.DataFrame(data).set_index("Point").round(2)
    
        print("\nCycle operating points:")
        print(df_points)
    
        return df_points
    
    def generate_plot(self, p_min= 1.2*1e5):
        #plot saturation lines
        steps = 100      
        p_crit = CP.PropsSI(self.ref,'pcrit')    
        pressures = np.linspace(p_min, p_crit, steps)
        
        sat_liq = np.array([CP.PropsSI('H', 'Q', 0, 'P', p, self.ref) for p in pressures])
        sat_vap = np.array([CP.PropsSI('H', 'Q', 1, 'P', p, self.ref) for p in pressures])
        sat_liq /= 1000 # convert to kJ/kg
        sat_vap /= 1000
        pressures *= 1e-5 # convert to bar
        
        fig = plt.figure(figsize=(18, 10))
        ax = plt.subplot(1, 1, 1)
        ax.set_facecolor('#F0F0F0')
        fig.patch.set_facecolor('#FCFCFC')
        
        ax.plot(sat_liq, pressures, 'darkgreen', linewidth=0.75)
        ax.plot(sat_vap, pressures, 'darkgreen', linewidth=0.75)
        ax.set_yscale('log')
        
        # set ticks and labels
        ax.xaxis.set_major_locator(MultipleLocator(10))
        tick_values = list(np.arange(1, 20, 1)) + list(np.arange(20, 40, 2))
        ax.set_yticks(tick_values)
        ax.set_yticklabels(v for v in tick_values)
        plt.grid(which='both', linestyle='--', linewidth=0.5)
        
        plt.xlabel('Entalphy, kJ/kg', fontsize=12, horizontalalignment='right', x=1.0)
        plt.ylabel('Pressure, bar', fontsize=12, horizontalalignment='right', y=1.0)
        plt.title(self.ref, fontsize=24, loc='left')
        
        # cycle transformation lines
        self.plot_line(self.pt1.p, self.pt1.h, self.pt2.p, self.pt2.h) # compression
        self.plot_line(self.pt2.p, self.pt2.h, self.pt11.p, self.pt11.h) # condensation + subcooling
        self.plot_line(self.pt11.p, self.pt11.h, self.pt12.p, self.pt12.h) # throttling
        self.plot_line(self.pt12.p, self.pt12.h, self.pt1.p, self.pt1.h) # evaporation + superheating
        
        if self.ihx:
            self.plot_line(self.pt5.p, self.pt5.h, self.pt6.p, self.pt6.h) #  throttling
            self.plot_line(self.pt6.p, self.pt6.h, self.pt8.p, self.pt8.h) # evaporation + superheating
            self.plot_line(self.pt8.p, self.pt8.h, self.pt9.p, self.pt9.h) # evaporation + superheating
        
        # points annotations
        self.annotate(self.pt1.p, self.pt1.h, 'u', 1) # suction
        self.annotate(self.pt2.p, self.pt2.h, 'ru', 2) # discharge
        self.annotate(self.pt3.p, self.pt3.h, 'ru', 3) # condenser saturation 1
        self.annotate(self.pt4.p, self.pt4.h, 'rb', 4) #c ondenser saturation 0
  
        if self.sub or self.ihx or self.rhx:
            self.annotate(self.pt11.p, self.pt11.h, 'lu', 11) #rhx liquid outlet
            
        if self.sub and (self.ihx or self.rhx):
            self.annotate(self.pt5.p, self.pt5.h, 'u', 5) # subcooler
               
        if self.ihx:
            self.annotate(self.pt6.p, self.pt6.h, 'lb', 6) # ihx inlet
            self.annotate(self.pt7.p, self.pt7.h, 'lu', 7) # ihx saturation 1
            self.annotate(self.pt8.p, self.pt8.h, 'r', 8) # ihx outlet
            self.annotate(self.pt9.p, self.pt9.h, 'lu', 9) # ihx throttled to suction
        
        if self.rhx and self.ihx:
            self.annotate(self.pt15.p, self.pt15.h, 'b', 15) # rhx suction
            self.annotate(self.pt10.p, self.pt10.h, 'u', 10) # rhx liqid inlet
            
        self.annotate(self.pt12.p, self.pt12.h, 'lb', 12) # evaporator inlet
        self.annotate(self.pt13.p, self.pt13.h, 'lb', 13) # evaporator saturation 1
        self.annotate(self.pt14.p, self.pt14.h, 'b', 14) # evaporator outlet
        
        plt.savefig("generated_plot.png")
        plt.show()

        
    def plot_line(self, p1, h1, p2, h2):
        plt.plot([h1, h2], [p1, p2], 'k-', linewidth=0.75)
        
    def annotate(self, p, h, loc, label):
        plt.plot(h, p, linewidth=1, marker ='.', color='black')
        
        dx, dy = 1, 1
        if 'r' in loc:
            dx = 1.005
        elif 'l' in loc:
            dx = 0.995
        if 'u' in loc:
            dy = 1.05
        elif 'b' in loc:
            dy = 0.9
        
        plt.text(dx*h, dy*p, label, fontsize=10)    
            
class CoefficientSEPR():
    '''
    A class represents data frames used for calaculation of SEPR coefficient.
    Colculation bases on provided refrigeration unit capacity and power and indicated case: inverter / fixed speed compressor and MT / LT unit
    '''
    def __init__(self, data_source, mode, declared_points):
        self.declared_points = declared_points
        self._inverter_mode = mode[0] == "inverter"
        
        d = {'mode': ["MT"]*4 + ["LT"]*4,
             't0': [-10]*4 + [-35]*4,
             'point': ["A", "B", "C", "D"]*2,
             'ambient': [32, 25, 15, 5]*2,
             'part load': [1, 0.9, 0.75, 0.6, 1, 0.95, 0.88, 0.80]}
        
        df_cop = pd.DataFrame(data=d)
        df_cop = df_cop[df_cop['mode'] == mode[1]]
        df_cop = df_cop.reset_index(drop=True)
        self.df_cop = df_cop
        
        df_sepr = pd.read_excel(data_source, "SEPR", index_col='j')
        self.df_sepr = df_sepr

    def approx_values_between_two_points(self, points, column):
        a, b = points[0], points[1] 
        pa, pb = self.df_sepr.at[a, column], self.df_sepr.at[b, column]
        
        P = self.df_sepr.loc[a:b, "Tj"].to_numpy()
        
        x = [self.df_sepr.at[a, "Tj"], self.df_sepr.at[b, "Tj"]]
        y = [pa, pb]
        P_int = np.interp(P, x, y)
        
        self.df_sepr.loc[a:b, column] = P_int
 
    def calculate_coefficient(self):
        self.Qa = self.declared_points[0]
        self.df_cop["Q"] = self.declared_points[0:4] # declared values Q and P
        self.df_cop["P"] = self.declared_points[4:8]
        self.df_cop["COP_DC"] = self.df_cop.Q/self.df_cop.P # calculated capacity
        
        # df_cop includes data related to A, B, C, D operating points 
        self.df_cop["cooling demand"] = self.df_cop["part load"] * self.Qa
        
        deg_coeff = 0.25 # degradation coefficient
        if self._inverter_mode:
            self.df_cop["capacity ratio"] = 1 # capacity ratio = 1, inverter compressor adjust capacity to demand 
        else:
            self.df_cop["capacity ratio"] = self.df_cop["cooling demand"].div(self.df_cop["Q"])
        
        self.df_cop["COP_PL"] = self.df_cop["COP_DC"] * (1-deg_coeff*(1-self.df_cop['capacity ratio'])) # capacity in reference to part load
        
        # df_sepr is used to calulate SEPR coefficient according to data from df_cop
        self.df_sepr['Ref point'] = self.df_sepr['Tj'].map(dict(zip(self.df_cop['ambient'], self.df_cop['point'])))
        self.df_sepr['Part load'] = self.df_sepr['Ref point'].map(dict(zip(self.df_cop['point'], self.df_cop['part load'])))
        self.df_sepr['COP_PL'] = self.df_sepr['Ref point'].map(dict(zip(self.df_cop['point'], self.df_cop['COP_PL'])))
        
        points_id = self.df_sepr.index[self.df_sepr['Ref point'].isin(self.df_cop["point"])] # get reference points indexes

        for col in ['Part load', 'COP_PL']:
            self.df_sepr.loc[:points_id[0], col] = self.df_sepr.at[points_id[0], col] # conditions for ambient temperature below D point
            self.df_sepr.loc[points_id[3]:, col] = self.df_sepr.at[points_id[3], col] # conditions for ambient temperature above A point
        
        approx_bins = list(zip(points_id[:-1], points_id[1:])) #referenco for groups (A-B), (B-C), (C-D)
        for points in approx_bins: # linear approximation of Part load and COP_PL for gropus (A-B), (B-C), (C-D)
            for col in ['Part load', 'COP_PL']:
                self.approx_values_between_two_points(points, col)
                
        # calculation according to SEPR formula
        self.df_sepr["Cooling demand"] = self.df_sepr["Part load"] * self.Qa
        self.df_sepr['hj*P'] = self.df_sepr['Cooling demand']*self.df_sepr['hj']
        self.df_sepr['P/COP'] = self.df_sepr['hj*P'] / self.df_sepr['COP_PL']
        
        num = self.df_sepr['hj*P'].sum()
        denom = self.df_sepr['P/COP'].sum()
        self.coef_SEPR = num/denom
        return self.coef_SEPR
